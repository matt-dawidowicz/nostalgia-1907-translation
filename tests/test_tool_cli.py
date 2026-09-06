"""Source-only tests for the unified Nostalgia 1907 operator CLI."""

from __future__ import annotations

import ast
import hashlib
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import nostalgia1907

ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    """Verify project metadata remains synchronized with canonical inputs."""

    def test_manifest_matches_canonical_source_inventory(self) -> None:
        """Match declared chapter and record totals to the canonical index."""
        manifest = nostalgia1907.load_manifest(ROOT)
        index_path = ROOT / "work" / "clean_rebuild" / "sources" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        translation = manifest["translation"]
        self.assertEqual(index["chapter_count"], translation["chapter_count"])
        self.assertEqual(
            sum(item["record_count"] for item in index["chapters"]),
            translation["record_count"],
        )
        self.assertEqual(
            sum(item["translated_records"] for item in index["chapters"]),
            translation["translated_record_count"],
        )
        self.assertEqual(
            sum(item["preserved_records"] for item in index["chapters"]),
            translation["preserved_record_count"],
        )
        self.assertEqual(
            nostalgia1907.normalized_text_sha256(index_path),
            translation["source_index_text_sha256"],
        )

    def test_source_index_hash_is_independent_of_line_endings(self) -> None:
        """Keep manifest hashes stable across permitted text line endings."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lf = root / "lf.json"
            crlf = root / "crlf.json"
            lf.write_bytes(b'{\n  "chapter_count": 19\n}\n')
            crlf.write_bytes(b'{\r\n  "chapter_count": 19\r\n}\r\n')
            self.assertEqual(
                nostalgia1907.normalized_text_sha256(lf),
                nostalgia1907.normalized_text_sha256(crlf),
            )

    def test_repository_is_not_a_distribution_package(self) -> None:
        """Keep project versioning in the operator manifest, not package metadata."""
        manifest = nostalgia1907.load_manifest(ROOT)
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn("[project]", pyproject)
        self.assertNotIn("[build-system]", pyproject)
        self.assertRegex(
            manifest["tool"]["version"], r"^[0-9]+\.[0-9]+\.[0-9]+$"
        )

    def test_manifest_and_local_config_reject_duplicate_keys(self) -> None:
        """Reject last-key-wins ambiguity in root operator configuration."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / nostalgia1907.MANIFEST_NAME).write_text(
                '{"schema_version": 1, "schema_version": 2}\n',
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(
                nostalgia1907.ToolError, "duplicate JSON object key"
            ):
                nostalgia1907.load_manifest(root)

            (root / nostalgia1907.LOCAL_CONFIG_NAME).write_text(
                '{"track1": "a", "track1": "b"}\n',
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(
                nostalgia1907.ToolError, "duplicate JSON object key"
            ):
                nostalgia1907.load_local_config(root)

    def test_validated_baseline_and_retail_track2_share_exact_audio(
        self,
    ) -> None:
        """Require the validated build to retain the exact retail audio track."""
        manifest = nostalgia1907.load_manifest(ROOT)
        baseline = manifest["translation"]["validated_baseline"]
        built_track2 = manifest["validated_builds"][baseline]["track2"]
        retail_track2 = manifest["retail_inputs"]["track2"]
        self.assertEqual(built_track2["size"], retail_track2["size"])
        self.assertEqual(built_track2["sha256"], retail_track2["sha256"])


class CliContractTests(unittest.TestCase):
    """Verify command registration and side-effect safety for the operator CLI."""

    def test_all_operator_commands_are_registered(self) -> None:
        """Expose every supported operator command through the root parser."""
        tool_parser = nostalgia1907.parser()
        subparsers_action = next(
            action
            for action in tool_parser._actions
            if getattr(action, "choices", None)
        )
        self.assertEqual(
            set(subparsers_action.choices),
            {"doctor", "prepare", "edit", "compare", "validate", "build"},
        )

    def test_project_defaults_new_builds_to_north_america(self) -> None:
        """Keep North America as the implicit region for normal builds."""
        manifest = nostalgia1907.load_manifest(ROOT)
        self.assertEqual(manifest["build"]["default_region"], "north-america")
        args = nostalgia1907.parser().parse_args(["build"])
        self.assertIsNone(args.region)
        self.assertIsNone(args.name)

    def test_release_names_are_normalized_without_paths(self) -> None:
        """Reject path-like release labels before output construction."""
        self.assertEqual(
            nostalgia1907.release_basename(None),
            "Nostalgia1907_CleanRebuild",
        )
        self.assertEqual(
            nostalgia1907.release_basename("candidate"),
            "Nostalgia1907_CleanRebuild_candidate",
        )
        self.assertEqual(
            nostalgia1907.release_basename("Nostalgia1907_Custom"),
            "Nostalgia1907_Custom",
        )
        for invalid in (
            "../candidate",
            "candidate/test",
            "candidate test",
            "",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(nostalgia1907.ToolError):
                    nostalgia1907.release_basename(invalid)

    def test_file_guard_reports_hash_and_size_failures(self) -> None:
        """Report invalid required artifacts instead of accepting partial matches."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.bin"
            path.write_bytes(b"retail fixture")
            digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            passing = nostalgia1907.file_check(
                "fixture",
                path,
                {"size": path.stat().st_size, "sha256": digest},
                required=True,
            )
            self.assertEqual(passing["status"], "PASS")
            wrong_size = nostalgia1907.file_check(
                "fixture",
                path,
                {"size": 1, "sha256": digest},
                required=True,
            )
            self.assertEqual(wrong_size["status"], "FAIL")
            wrong_hash = nostalgia1907.file_check(
                "fixture",
                path,
                {"size": path.stat().st_size, "sha256": "0" * 64},
                required=True,
            )
            self.assertEqual(wrong_hash["status"], "FAIL")

    def test_missing_optional_file_is_skip(self) -> None:
        """Mark an absent optional dependency as skipped rather than failed."""
        result = nostalgia1907.file_check(
            "optional",
            ROOT / "does-not-exist.bin",
            {"sha256": "0" * 64},
            required=False,
        )
        self.assertEqual(result["status"], "SKIP")

    def test_validate_runs_every_source_gate_before_retail_gates(self) -> None:
        """Keep the documented complete validation sequence executable."""
        manifest = nostalgia1907.load_manifest(ROOT)
        events: list[str] = []

        def fake_run_script(
            _root: Path,
            script: str,
            *_args: str,
            **_kwargs: object,
        ) -> None:
            """Record one script stage by its stable repository path."""
            events.append(script)

        def fake_run_command(
            command: tuple[str, ...],
            *,
            root: Path,
            label: str,
        ) -> None:
            """Record one direct Python stage by its operator label."""
            del command, root
            events.append(label)

        with (
            patch.object(
                nostalgia1907, "load_manifest", return_value=manifest
            ),
            patch.object(
                nostalgia1907,
                "require_retail_reference",
                side_effect=lambda *_args: (
                    events.append("retail") or Path("retail")
                ),
            ),
            patch.object(
                nostalgia1907, "run_script", side_effect=fake_run_script
            ),
            patch.object(
                nostalgia1907, "run_command", side_effect=fake_run_command
            ),
            patch.object(
                nostalgia1907,
                "command_compare",
                side_effect=lambda *_args: events.append("comparison") or 0,
            ),
        ):
            self.assertEqual(
                nostalgia1907.command_validate(
                    ROOT, Namespace(skip_comparison=False)
                ),
                0,
            )

        self.assertEqual(
            events,
            [
                "tools/source_checks.py",
                "retail",
                "work/clean_rebuild/translation_formatter.py",
                "comparison",
                "work/clean_rebuild/translation_validation.py",
            ],
        )

    def test_edit_rejects_ambiguous_batch_arguments(self) -> None:
        """Reject a request that mixes batch edits with a single-record edit."""
        with self.assertRaises(nostalgia1907.ToolError):
            nostalgia1907.validate_edit_request(
                Namespace(
                    changes=Path("changes.json"),
                    record="PART1A:003",
                    text="replacement",
                    apply=True,
                )
            )

    def test_build_directory_state_and_collision_guard(self) -> None:
        """Allow only absent or empty build roots before a new run begins."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            absent = root / "absent"
            empty = root / "empty"
            occupied = root / "occupied"
            empty.mkdir()
            occupied.mkdir()
            (occupied / "artifact.bin").write_bytes(b"fixture")
            self.assertEqual(nostalgia1907.directory_state(absent), "absent")
            self.assertEqual(nostalgia1907.directory_state(empty), "empty")
            self.assertEqual(
                nostalgia1907.directory_state(occupied), "non-empty"
            )
            nostalgia1907.require_fresh_build_directory("test", absent)
            nostalgia1907.require_fresh_build_directory("test", empty)
            with self.assertRaises(nostalgia1907.ToolError):
                nostalgia1907.require_fresh_build_directory("test", occupied)

    def test_build_roots_must_not_overlap(self) -> None:
        """Reject nested or identical run and delivery roots."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nostalgia1907.require_separate_build_directories(
                root / "runs",
                root / "delivery",
            )
            for runs, delivery in (
                (root / "same", root / "same"),
                (root / "runs", root / "runs" / "delivery"),
                (root / "delivery" / "runs", root / "delivery"),
            ):
                with self.subTest(runs=runs, delivery=delivery):
                    with self.assertRaises(nostalgia1907.ToolError):
                        nostalgia1907.require_separate_build_directories(
                            runs, delivery
                        )

    def test_normal_build_runs_full_validation_before_builder(self) -> None:
        """Require validation to finish before any normal build subprocess starts."""
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            args = Namespace(
                name="test",
                track1=temporary_root / "track1.bin",
                track2=temporary_root / "track2.bin",
                region="japan",
                us_bios=None,
                runs_root=temporary_root / "runs",
                output=temporary_root / "delivery",
                dry_run=False,
            )
            events: list[str] = []
            with (
                patch.object(nostalgia1907, "require_file"),
                patch.object(
                    nostalgia1907,
                    "command_validate",
                    side_effect=lambda *_args: events.append("validate") or 0,
                ),
                patch.object(
                    nostalgia1907,
                    "run_script",
                    side_effect=lambda *_args, **_kwargs: events.append(
                        "build"
                    ),
                ),
            ):
                self.assertEqual(nostalgia1907.command_build(ROOT, args), 0)
            self.assertEqual(events, ["validate", "build"])

    def test_north_american_build_wraps_only_a_proven_clean_stage(
        self,
    ) -> None:
        """Pass only a hash-proven clean stage into the U.S. wrapper."""
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            args = Namespace(
                name="test",
                track1=temporary_root / "track1.bin",
                track2=temporary_root / "track2.bin",
                region="north-america",
                us_bios=temporary_root / "bios.bin",
                runs_root=temporary_root / "runs",
                output=temporary_root / "delivery",
                dry_run=False,
            )
            events: list[str] = []
            scripts: list[tuple[str, tuple[str, ...]]] = []

            def fake_run_script(
                _root: Path,
                script: str,
                *script_args: str,
                **_kwargs: object,
            ) -> None:
                """Simulate clean and region builders while recording invocation order."""
                scripts.append((script, script_args))
                if script.endswith("clean_rebuild/rebuild.py"):
                    events.append("clean")
                    delivery_index = script_args.index("--delivery-root") + 1
                    basename_index = script_args.index("--basename") + 1
                    clean_delivery = Path(script_args[delivery_index])
                    clean_basename = script_args[basename_index]
                    clean_delivery.mkdir(parents=True)
                    (
                        clean_delivery / f"{clean_basename}_Track1.bin"
                    ).write_bytes(b"clean track 1")
                    (
                        clean_delivery / f"{clean_basename}_Track2.bin"
                    ).write_bytes(b"clean track 2")
                else:
                    events.append("region")

            with (
                patch.object(nostalgia1907, "require_file"),
                patch.object(
                    nostalgia1907,
                    "command_validate",
                    side_effect=lambda *_args: events.append("validate") or 0,
                ),
                patch.object(
                    nostalgia1907, "run_script", side_effect=fake_run_script
                ),
            ):
                self.assertEqual(nostalgia1907.command_build(ROOT, args), 0)

            self.assertEqual(events, ["validate", "clean", "region"])
            self.assertEqual(
                scripts[0][0],
                "work/clean_rebuild/rebuild.py",
            )
            self.assertEqual(
                scripts[1][0],
                "work/region_variant/build_us_bios_test.py",
            )
            region_args = scripts[1][1]
            expected_hash = (
                hashlib.sha256(b"clean track 1").hexdigest().upper()
            )
            self.assertEqual(
                region_args[region_args.index("--expected-track1-sha256") + 1],
                expected_hash,
            )
            self.assertIn(
                "Nostalgia1907_CleanRebuild_test_NorthAmerica", region_args
            )


class RepositoryPolicyTests(unittest.TestCase):
    """Protect production modules and manifests from local-machine assumptions."""

    def test_production_modules_do_not_reference_historical_workspaces(
        self,
    ) -> None:
        """Reject hard-coded paths to retired forensic workspaces."""
        clean = ROOT / "work" / "clean_rebuild"
        rebuild_path = clean / "rebuild.py"
        tree = ast.parse(rebuild_path.read_text(encoding="utf-8"))
        production_modules: tuple[str, ...] | None = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name)
                and target.id == "PRODUCTION_MODULES"
                for target in node.targets
            ):
                production_modules = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(production_modules)
        # rebuild.py performs the same authoritative check at runtime.
        for name in production_modules or ():
            path = clean / name
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(r"C:\Users\thema", text)
            self.assertNotIn(r"D:\Sega CD Games", text)

    def test_project_manifest_contains_no_machine_specific_paths(self) -> None:
        """Keep the committed project manifest portable across developer machines."""
        text = (ROOT / nostalgia1907.MANIFEST_NAME).read_text(encoding="utf-8")
        self.assertNotIn(r"C:\\Users", text)
        self.assertNotIn(r"D:\\", text)

    def test_canonical_provenance_contains_no_machine_specific_paths(
        self,
    ) -> None:
        """Represent historical text provenance with portable labels only."""
        sources = ROOT / "work" / "clean_rebuild" / "sources"
        index = json.loads(
            (sources / "index.json").read_text(encoding="utf-8")
        )
        for item in index["chapters"]:
            canonical = json.loads(
                (sources / item["source"]).read_text(encoding="utf-8")
            )
            for provenance in canonical.get("text_sources", []):
                with self.subTest(
                    chapter=canonical["chapter"], value=provenance
                ):
                    self.assertNotRegex(provenance, r"(?i)^[A-Z]:[\\/]")
                    self.assertFalse(
                        provenance.startswith(("/Users/", "/home/"))
                    )


class ModuleExecutionTests(unittest.TestCase):
    """Keep lower-level execution on importable package module paths."""

    def test_run_script_uses_module_mode(self) -> None:
        """Invoke maintained lower-level code through ``python -m``."""
        with patch.object(nostalgia1907, "run_command") as run_command:
            nostalgia1907.run_script(
                ROOT,
                "work/clean_rebuild/source_json.py",
                "--help",
                label="source-json fixture",
            )
        command = run_command.call_args.args[0]
        self.assertEqual(
            command[1:4],
            ("-m", "work.clean_rebuild.source_json", "--help"),
        )
        self.assertEqual(run_command.call_args.kwargs["root"], ROOT)

    def test_run_script_rejects_path_escape(self) -> None:
        """Reject traversal before converting a path into a module name."""
        with self.assertRaises(nostalgia1907.ToolError):
            nostalgia1907.run_script(
                ROOT,
                "../escape.py",
                label="escape fixture",
            )


if __name__ == "__main__":
    unittest.main()

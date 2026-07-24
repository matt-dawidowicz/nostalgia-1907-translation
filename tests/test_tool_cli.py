"""Source-only tests for the unified Nostalgia 1907 operator CLI."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import nostalgia1907


ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_manifest_matches_canonical_source_inventory(self) -> None:
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

    def test_package_and_manifest_versions_match(self) -> None:
        manifest = nostalgia1907.load_manifest(ROOT)
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), manifest["tool"]["version"])

    def test_validated_baseline_and_retail_track2_share_exact_audio(self) -> None:
        manifest = nostalgia1907.load_manifest(ROOT)
        baseline = manifest["translation"]["validated_baseline"]
        built_track2 = manifest["validated_builds"][baseline]["track2"]
        retail_track2 = manifest["retail_inputs"]["track2"]
        self.assertEqual(built_track2["size"], retail_track2["size"])
        self.assertEqual(built_track2["sha256"], retail_track2["sha256"])


class CliContractTests(unittest.TestCase):
    def test_all_operator_commands_are_registered(self) -> None:
        tool_parser = nostalgia1907.parser()
        subparsers_action = next(
            action
            for action in tool_parser._actions
            if getattr(action, "choices", None)
        )
        self.assertEqual(
            set(subparsers_action.choices),
            {"doctor", "prepare", "edit", "compare", "validate", "build", "build-us"},
        )

    def test_release_names_are_normalized_without_paths(self) -> None:
        self.assertEqual(
            nostalgia1907.release_basename("v8"),
            "Nostalgia1907_CleanRebuild_v8",
        )
        self.assertEqual(
            nostalgia1907.release_basename("Nostalgia1907_Custom"),
            "Nostalgia1907_Custom",
        )
        for invalid in ("../v8", "v8/test", "v8 test", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(nostalgia1907.ToolError):
                    nostalgia1907.release_basename(invalid)

    def test_file_guard_reports_hash_and_size_failures(self) -> None:
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
        result = nostalgia1907.file_check(
            "optional",
            ROOT / "does-not-exist.bin",
            {"sha256": "0" * 64},
            required=False,
        )
        self.assertEqual(result["status"], "SKIP")

    def test_static_source_inventory_excludes_vendored_runtimes(self) -> None:
        manifest = nostalgia1907.load_manifest(ROOT)
        sources = nostalgia1907.operator_python_sources(ROOT, manifest)
        self.assertIn(ROOT / "nostalgia1907.py", sources)
        self.assertIn(
            ROOT / "work" / "audio_localization" / "audio_localization.py",
            sources,
        )
        self.assertTrue(all(".runtime" not in path.parts for path in sources))
        self.assertTrue(all(".kokoro_runtime" not in path.parts for path in sources))

    def test_edit_rejects_ambiguous_batch_arguments(self) -> None:
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
            self.assertEqual(nostalgia1907.directory_state(occupied), "non-empty")
            nostalgia1907.require_fresh_build_directory("test", absent)
            nostalgia1907.require_fresh_build_directory("test", empty)
            with self.assertRaises(nostalgia1907.ToolError):
                nostalgia1907.require_fresh_build_directory("test", occupied)

    def test_build_roots_must_not_overlap(self) -> None:
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
                        nostalgia1907.require_separate_build_directories(runs, delivery)

    def test_normal_build_runs_full_validation_before_builder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            args = Namespace(
                name="test",
                track1=temporary_root / "track1.bin",
                track2=temporary_root / "track2.bin",
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
                    side_effect=lambda *_args, **_kwargs: events.append("build"),
                ),
            ):
                self.assertEqual(nostalgia1907.command_build(ROOT, args), 0)
            self.assertEqual(events, ["validate", "build"])


class RepositoryPolicyTests(unittest.TestCase):
    def test_production_modules_do_not_reference_historical_workspaces(self) -> None:
        clean = ROOT / "work" / "clean_rebuild"
        rebuild_path = clean / "rebuild.py"
        tree = ast.parse(rebuild_path.read_text(encoding="utf-8"))
        production_modules: tuple[str, ...] | None = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "PRODUCTION_MODULES"
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
        text = (ROOT / nostalgia1907.MANIFEST_NAME).read_text(encoding="utf-8")
        self.assertNotIn(r"C:\\Users", text)
        self.assertNotIn(r"D:\\", text)


if __name__ == "__main__":
    unittest.main()

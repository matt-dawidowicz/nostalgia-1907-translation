"""Regression tests for the media-free source-health audit."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "source_health.py"
SPEC = importlib.util.spec_from_file_location("source_health", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
source_health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_health)


class SourceHealthTests(unittest.TestCase):
    """Keep development and public-release source inventories fail-closed."""

    def test_repository_has_no_runtime_package_metadata(self) -> None:
        """Keep the directly executed production toolchain dependency-free."""
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertNotIn("project", project)
        self.assertNotIn("build-system", project)
        requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("ruff==", requirements)
        self.assertIn("mypy==", requirements)

    def test_clean_source_tree_passes(self) -> None:
        """Accept valid UTF-8 Python, JSON, and TOML source files."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "module.py").write_text(
                '"""Example."""\n', encoding="utf-8", newline="\n"
            )
            (root / "data.json").write_text(
                '{"value": 1}\n', encoding="utf-8", newline="\n"
            )
            (root / "pyproject.toml").write_text(
                '[project]\nname = "x"\n', encoding="utf-8", newline="\n"
            )
            report = source_health.audit(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["failure_count"], 0)

    def test_repository_root_passes(self) -> None:
        """Cover development mode and a clean package-shaped source inventory."""
        report = source_health.audit(ROOT)
        self.assertEqual(report["status"], "PASS", report["failures"])
        if (ROOT / ".git").exists():
            strict_report = source_health.audit(ROOT, strict_release=True)
        else:
            with tempfile.TemporaryDirectory() as temporary:
                clean_root = Path(temporary)
                for source in source_health.iter_source_files(ROOT):
                    relative = source.relative_to(ROOT)
                    target = clean_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                strict_report = source_health.audit(clean_root, strict_release=True)
        self.assertEqual(
            strict_report["status"], "PASS", strict_report["failures"]
        )

    def test_duplicate_json_and_forbidden_media_fail(self) -> None:
        """Reject duplicate keys and game media in a source checkout."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bad.json").write_text(
                '{"x": 1, "x": 2}\n', encoding="utf-8", newline="\n"
            )
            (root / "disc.bin").write_bytes(b"not a real disc")
            report = source_health.audit(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["forbidden_media_count"], 1)
            self.assertTrue(any("duplicate key" in item for item in report["failures"]))

    def test_dotfile_text_hygiene_is_checked(self) -> None:
        """Do not let suffixless Git control files bypass text validation."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".gitignore").write_bytes(b"build/  \n")
            report = source_health.audit(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["text_files_checked"], 1)
            self.assertTrue(
                any(
                    ".gitignore:1: trailing whitespace" in item
                    for item in report["failures"]
                )
            )

    def test_mixed_powershell_line_endings_fail(self) -> None:
        """Reject lone CR or LF bytes mixed into otherwise valid CRLF source."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "mixed.ps1"
            for data in (b"one\r\ntwo\rthree\r\n", b"one\r\ntwo\nthree\r\n"):
                with self.subTest(data=data):
                    script.write_bytes(data)
                    report = source_health.audit(root)
                    self.assertEqual(report["status"], "FAIL")
                    self.assertTrue(
                        any(
                            "PowerShell source must use consistent CRLF endings"
                            in item
                            for item in report["failures"]
                        )
                    )

    def test_retired_recovery_outputs_fail(self) -> None:
        """Keep historical generated recovery reports out of source releases."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            retired = root / "work" / "clean_rebuild" / "recover_bonus_2.json"
            retired.parent.mkdir(parents=True)
            retired.write_text("{}\n", encoding="utf-8", newline="\n")
            report = source_health.audit(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any("retired generated recovery" in item for item in report["failures"])
            )

    def test_development_mode_ignores_documented_local_state(self) -> None:
        """Keep private fixtures usable without weakening publication checks."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ignored = root / "work" / "clean_rebuild" / "retail_reference"
            ignored.mkdir(parents=True)
            (ignored / "retail.iso").write_bytes(b"local-only")
            metadata = root / "nostalgia1907_tools.egg-info"
            metadata.mkdir()
            (metadata / "generated.bin").write_bytes(b"setuptools metadata")
            (root / "nostalgia1907.local.json").write_text(
                "{}\n", encoding="utf-8", newline="\n"
            )
            (root / "ok.py").write_text(
                '"""Example."""\n', encoding="utf-8", newline="\n"
            )
            report = source_health.audit(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["forbidden_media_count"], 0)

    def test_strict_release_scans_normally_excluded_directories(self) -> None:
        """Reject retail media even when it uses a development-only directory."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            retail = root / "work" / "clean_rebuild" / "retail_reference"
            retail.mkdir(parents=True)
            (retail / "retail.iso").write_bytes(b"local-only")
            report = source_health.audit(root, strict_release=True)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["inventory_mode"], "package-members")
            self.assertTrue(any("retail.iso" in failure for failure in report["failures"]))

    def test_strict_release_rejects_local_config_images_and_states(self) -> None:
        """Cover the release-gate false negatives found during source review."""
        forbidden = (
            "nostalgia1907.local.json",
            "review.jpg",
            "comparison.webp",
            "state.state",
            "slot.ss0",
            "__pycache__/module.pyc",
            "runtime.dll",
            "model.onnx",
        )
        for filename in forbidden:
            with self.subTest(filename=filename):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    path = root / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.suffix == ".json":
                        path.write_text("{}\n", encoding="utf-8", newline="\n")
                    else:
                        path.write_bytes(b"fixture")
                    report = source_health.audit(root, strict_release=True)
                    self.assertEqual(report["status"], "FAIL")
                    self.assertTrue(any(filename in failure for failure in report["failures"]))

    def test_authoritative_source_gate_supports_strict_release(self) -> None:
        """Keep exact-inventory validation exposed by the unified source gate."""
        source_gate = ROOT / "tools" / "source_checks.py"
        text = source_gate.read_text(encoding="utf-8")
        self.assertIn('"--strict-release"', text)
        self.assertIn("strict_release=args.strict_release", text)


if __name__ == "__main__":
    unittest.main()

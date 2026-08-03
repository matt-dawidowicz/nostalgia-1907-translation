"""Regression tests for the media-free source-health audit."""

from __future__ import annotations

import importlib.util
import tempfile
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
    """Keep structural checks strict without inspecting ignored local state."""

    def test_clean_source_tree_passes(self) -> None:
        """Accept valid UTF-8 Python, JSON, and TOML source files."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "module.py").write_text('"""Example."""\n', encoding="utf-8", newline="\n")
            (root / "data.json").write_text('{"value": 1}\n', encoding="utf-8", newline="\n")
            (root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8", newline="\n")
            report = source_health.audit(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["failure_count"], 0)

    def test_duplicate_json_and_forbidden_media_fail(self) -> None:
        """Reject duplicate keys and game media in a source checkout."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bad.json").write_text('{"x": 1, "x": 2}\n', encoding="utf-8", newline="\n")
            (root / "disc.bin").write_bytes(b"not a real disc")
            report = source_health.audit(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["forbidden_media_count"], 1)
            self.assertTrue(any("duplicate key" in item for item in report["failures"]))

    def test_generated_and_retail_directories_are_ignored(self) -> None:
        """Do not treat excluded local state as tracked source content."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ignored = root / "work" / "clean_rebuild" / "retail_reference"
            ignored.mkdir(parents=True)
            (ignored / "retail.iso").write_bytes(b"local-only")
            (root / "ok.py").write_text('"""Example."""\n', encoding="utf-8", newline="\n")
            report = source_health.audit(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["forbidden_media_count"], 0)


if __name__ == "__main__":
    unittest.main()

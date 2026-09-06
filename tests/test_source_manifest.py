"""Regression tests for the source-only SHA-256 manifest."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "source_manifest.py"
SPEC = importlib.util.spec_from_file_location("source_manifest", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
source_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source_manifest)


class SourceManifestTests(unittest.TestCase):
    """Keep review-bundle inventory deterministic and fail-closed."""

    def test_package_inventory_is_sorted_and_excludes_manifest_itself(
        self,
    ) -> None:
        """Render every package member exactly once in portable path order."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "z.txt").write_text("z\n", encoding="utf-8")
            nested = root / "a"
            nested.mkdir()
            (nested / "b.txt").write_text("b\n", encoding="utf-8")
            (root / source_manifest.MANIFEST_NAME).write_text(
                "stale\n", encoding="utf-8"
            )
            files = source_manifest.manifest_files(root)
            self.assertEqual(
                [path.as_posix() for path in files],
                ["a/b.txt", "z.txt"],
            )

    def test_rendered_manifest_uses_uppercase_sha256(self) -> None:
        """Keep the checked-in review format stable across platforms."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "source.txt"
            path.write_bytes(b"source\n")
            rendered = source_manifest.render_manifest(root)
            expected_hash = source_manifest.sha256(path)
            self.assertIn(f"{expected_hash}  source.txt\n", rendered)
            self.assertEqual(expected_hash, expected_hash.upper())

    def test_text_hash_is_line_ending_independent(self) -> None:
        """Treat LF and CRLF materializations as the same reviewed text source."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lf = root / "lf.py"
            crlf = root / "crlf.py"
            lf.write_bytes(b'"""Source."""\nvalue = 1\n')
            crlf.write_bytes(b'"""Source."""\r\nvalue = 1\r\n')
            self.assertEqual(
                source_manifest.sha256(lf),
                source_manifest.sha256(crlf),
            )

    def test_makefile_and_sha256_text_hashes_normalize_line_endings(
        self,
    ) -> None:
        """Match source-health text policy for suffixless and checksum text files."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("Makefile", "checks.sha256"):
                with self.subTest(name=name):
                    path = root / name
                    path.write_bytes(b"first\nsecond\n")
                    lf_hash = source_manifest.sha256(path)
                    path.write_bytes(b"first\r\nsecond\r\n")
                    self.assertEqual(source_manifest.sha256(path), lf_hash)

    def test_check_manifest_detects_changed_source(self) -> None:
        """Reject a manifest after any represented source byte changes."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("first\n", encoding="utf-8")
            manifest = root / source_manifest.MANIFEST_NAME
            manifest.write_text(
                source_manifest.render_manifest(root),
                encoding="utf-8",
                newline="\n",
            )
            valid, differences = source_manifest.check_manifest(root)
            self.assertTrue(valid)
            self.assertEqual(differences, ())
            source.write_text("second\n", encoding="utf-8")
            valid, differences = source_manifest.check_manifest(root)
            self.assertFalse(valid)
            self.assertTrue(any("changed" in item for item in differences))

    def test_manifest_diff_reports_duplicate_lines(self) -> None:
        """A duplicated hash line must produce an actionable stale-line diagnostic."""
        expected = source_manifest.HEADER + "A" * 64 + "  source.txt\n"
        actual = expected + "A" * 64 + "  source.txt\n"
        differences = source_manifest.manifest_diff(expected, actual)
        self.assertEqual(len(differences), 1)
        self.assertIn("unexpected or stale", differences[0])
        self.assertIn("source.txt", differences[0])

    def test_repository_manifest_matches_current_tree(self) -> None:
        """Keep the committed review manifest synchronized with source."""
        valid, differences = source_manifest.check_manifest(ROOT)
        self.assertTrue(valid, differences)


if __name__ == "__main__":
    unittest.main()

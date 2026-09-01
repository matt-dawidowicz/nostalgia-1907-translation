"""Regression tests for clean comparison staging and byte determinism."""

from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"

from work.clean_rebuild import export_bilingual_comparison as comparison  # noqa: E402


class ComparisonExportTests(unittest.TestCase):
    """Protect package freshness, exact inventory, and byte identity."""

    def _fixture(self, root: Path) -> tuple[Path, Path]:
        """Create a two-record synthetic retail/canonical fixture."""
        sources = root / "sources"
        retail = root / "retail"
        sources.mkdir(parents=True)
        (retail / "retail_files").mkdir(parents=True)
        (retail / "retail_unpacked" / "TEST").mkdir(parents=True)
        fixed = b"\0" * comparison.GLYPH_BYTES
        fixed_path = retail / "retail_files" / "FIX_CODE.FNT"
        fixed_path.write_bytes(fixed)
        mes_path = retail / "retail_unpacked" / "TEST" / "TEST.MES"
        mes_path.write_bytes(b"synthetic MES fixture")
        records = [
            {
                "index": 0,
                "policy": "translate",
                "text": "First line.",
                "layout_policy": "fixed",
            },
            {
                "index": 1,
                "policy": "preserve",
                "text": None,
            },
        ]
        chapter = {
            "chapter": "TEST",
            "record_count": 2,
            "retail_mes": {
                "size": mes_path.stat().st_size,
                "sha256": comparison.sha256(mes_path),
            },
            "records": records,
        }
        (sources / "TEST.json").write_text(
            json.dumps(chapter, indent=2) + "\n",
            encoding="utf-8",
        )
        index = {
            "chapter_count": 1,
            "chapters": [
                {
                    "chapter": "TEST",
                    "source": "TEST.json",
                    "record_count": 2,
                    "translated_records": 1,
                    "preserved_records": 1,
                }
            ],
        }
        (sources / "index.json").write_text(
            json.dumps(index, indent=2) + "\n",
            encoding="utf-8",
        )
        return sources, retail

    def _export(self, root: Path, output: Path) -> dict[str, object]:
        """Run the real exporter against the synthetic fixture."""
        sources, retail = self._fixture(root)
        fake_mes = SimpleNamespace(
            record_count=2,
            records=(b"\0", b"\0"),
            glyphs=(),
        )
        fixed_path = retail / "retail_files" / "FIX_CODE.FNT"
        with (
            patch.object(comparison, "SOURCES", sources),
            patch.object(comparison, "EXPECTED_CHAPTERS", 1),
            patch.object(comparison, "EXPECTED_RECORDS", 2),
            patch.object(comparison, "FIXED_FONT_SIZE", fixed_path.stat().st_size),
            patch.object(
                comparison, "FIXED_FONT_SHA256", comparison.sha256(fixed_path)
            ),
            patch.object(comparison, "read_mes", return_value=fake_mes),
        ):
            return comparison.export_comparison(retail, output)

    def test_stale_output_and_prior_staging_never_enter_archive(self) -> None:
        """Prove recognizable sentinels from prior runs cannot contaminate output."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "comparison"
            output.mkdir()
            stale_output = output / "STALE_OUTPUT_SENTINEL.txt"
            stale_output.write_text("stale output sentinel", encoding="utf-8")
            prior_staging = root / ".comparison.staging-prior"
            prior_staging.mkdir()
            stale_staging = prior_staging / "STALE_STAGING_SENTINEL.txt"
            stale_staging.write_text("stale staging sentinel", encoding="utf-8")

            result = self._export(root / "fixture", output)

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["previous_output_reused_file_count"], 0)
            self.assertIn(
                stale_output.name,
                result["previous_output_unexpected_files_discarded"],
            )
            self.assertIn(
                prior_staging.name,
                result["abandoned_staging_directories_ignored"],
            )
            self.assertTrue(
                any(
                    stale_staging.name in path
                    for path in result["abandoned_staging_files_ignored"]
                )
            )
            self.assertFalse(stale_output.exists())
            self.assertTrue(stale_staging.exists())
            with zipfile.ZipFile(output / comparison.ZIP_NAME) as archive:
                names = archive.namelist()
                self.assertNotIn(stale_output.name, names)
                self.assertNotIn(stale_staging.name, names)
                joined = b"\n".join(archive.read(name) for name in names)
                self.assertNotIn(b"stale output sentinel", joined)
                self.assertNotIn(b"stale staging sentinel", joined)
            validation = comparison.validate_comparison_package(output)
            self.assertEqual(validation["status"], "PASS")

    def test_independent_clean_exports_have_identical_archive_and_members(self) -> None:
        """Compare archive and member hashes from two independent clean roots."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first_result = self._export(root / "fixture-a", first)
            second_result = self._export(root / "fixture-b", second)
            self.assertEqual(first_result["zip_sha256"], second_result["zip_sha256"])
            self.assertEqual(
                (first / comparison.ZIP_NAME).read_bytes(),
                (second / comparison.ZIP_NAME).read_bytes(),
            )
            inventories: list[list[tuple[str, str]]] = []
            for output in (first, second):
                with zipfile.ZipFile(output / comparison.ZIP_NAME) as archive:
                    inventories.append(
                        [
                            (name, hashlib.sha256(archive.read(name)).hexdigest())
                            for name in archive.namelist()
                        ]
                    )
            self.assertEqual(inventories[0], inventories[1])

    def test_validator_rejects_unexpected_and_tampered_files(self) -> None:
        """Make full-package validation fail on extras and changed member bytes."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "comparison"
            self._export(root / "fixture", output)
            unexpected = output / "unexpected.txt"
            unexpected.write_text("unexpected", encoding="utf-8")
            validation = comparison.validate_comparison_package(output)
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(
                any("unexpected" in item for item in validation["failures"])
            )
            unexpected.unlink()
            (output / "README.md").write_text("tampered\n", encoding="utf-8")
            validation = comparison.validate_comparison_package(output)
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(
                any(
                    "size mismatch" in item or "hash mismatch" in item
                    for item in validation["failures"]
                )
            )

    def test_validator_rejects_manifest_archive_redirect(self) -> None:
        """Reject a sidecar that redirects validation outside the package root."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "comparison"
            self._export(root / "fixture", output)
            manifest_path = output / comparison.PACKAGE_MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["package"] = "../redirected.zip"
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            validation = comparison.validate_comparison_package(output)
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(
                any("unexpected archive" in item for item in validation["failures"])
            )

    def test_png_encoder_has_only_fixed_chunks_and_exact_scanlines(self) -> None:
        """Prove the in-module PNG has no metadata or encoder heuristics."""
        width, height = 8, 2
        raster = bytes((0b10101010, 0b01010101))
        payload = comparison._encode_monochrome_png(width, height, raster)
        self.assertTrue(payload.startswith(comparison.PNG_SIGNATURE))
        offset = len(comparison.PNG_SIGNATURE)
        chunks: list[tuple[bytes, bytes]] = []
        while offset < len(payload):
            size = struct.unpack(">I", payload[offset : offset + 4])[0]
            kind = payload[offset + 4 : offset + 8]
            data = payload[offset + 8 : offset + 8 + size]
            chunks.append((kind, data))
            offset += 12 + size
        self.assertEqual([kind for kind, _ in chunks], [b"IHDR", b"IDAT", b"IEND"])
        ihdr = chunks[0][1]
        self.assertEqual(struct.unpack(">IIBBBBB", ihdr), (8, 2, 1, 0, 0, 0, 0))
        scanlines = zlib.decompress(chunks[1][1])
        self.assertEqual(scanlines, b"\x00\xAA\x00\x55")

    def test_inventory_guard_reports_missing_and_unexpected_paths(self) -> None:
        """Report both sides of an exact staging inventory mismatch."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "unexpected.txt").write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "missing expected files:.*unexpected files:",
            ):
                comparison._validate_inventory(root, {"expected.txt"}, "test")


if __name__ == "__main__":
    unittest.main()

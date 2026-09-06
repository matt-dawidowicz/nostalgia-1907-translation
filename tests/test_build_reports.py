"""Regression tests for deterministic generated build reports."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"

from work.clean_rebuild import build_mes_set as mes_set  # noqa: E402
from work.clean_rebuild.font_render import GLYPH_BYTES  # noqa: E402
from work.clean_rebuild.mes_compiler import BuildResult  # noqa: E402


class BuildReportTests(unittest.TestCase):
    """Keep clean-run reports independent of temporary directory names."""

    def test_mes_report_uses_build_relative_paths(self) -> None:
        """Two separate roots must emit byte-identical MES reports."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources"
            sources.mkdir()
            (sources / "index.json").write_text(
                json.dumps(
                    {"chapters": [{"chapter": "TEST", "source": "TEST.json"}]}
                )
                + "\n",
                encoding="utf-8",
            )
            (sources / "TEST.json").write_text("{}\n", encoding="utf-8")

            def fake_compile_files(
                retail_mes: Path,
                retail_scn: Path,
                source: Path,
                output: Path,
                *,
                glyph_order: str,
            ) -> BuildResult:
                """Emit a deterministic in-memory compile result for this test."""
                self.assertTrue(retail_mes.is_file())
                self.assertTrue(retail_scn.is_file())
                self.assertEqual(source, sources / "TEST.json")
                self.assertEqual(glyph_order, "first-use")
                output.write_bytes(b"compiled\0")
                return BuildResult(
                    data=b"compiled\0",
                    record_count=1,
                    translated_records=1,
                    preserved_records=0,
                    split_offset=2,
                    dynamic_glyphs=1,
                    rendered_cells=1,
                    scn_layout_records=1,
                    fixed_spill_count=0,
                    fixed_spill_occurrences=0,
                    fixed_font_patches=(),
                    glyph_order="first-use",
                )

            reports = []
            report_bytes = []
            with (
                patch.object(mes_set, "SOURCES", sources),
                patch.object(mes_set, "compile_files", fake_compile_files),
            ):
                for name in ("independent_a", "independent_b"):
                    build = root / name
                    retail = build / "retail_unpacked" / "TEST"
                    retail.mkdir(parents=True)
                    (retail / "TEST.MES").write_bytes(b"retail mes")
                    (retail / "TEST.SCN").write_bytes(b"retail scn")
                    font = build / "retail_files" / "FIX_CODE.FNT"
                    font.parent.mkdir(parents=True)
                    font.write_bytes(b"\0" * GLYPH_BYTES)
                    reports.append(mes_set.build_mes_set(build))
                    report_bytes.append(
                        (build / "mes_report.json").read_bytes()
                    )

            self.assertEqual(reports[0], reports[1])
            self.assertEqual(report_bytes[0], report_bytes[1])
            self.assertEqual(reports[0]["fixed_font"]["path"], "FIX_CODE.FNT")
            self.assertEqual(reports[0]["chapters"][0]["path"], "mes/TEST.MES")

    def test_malformed_fixed_font_patch_is_rejected_before_font_write(
        self,
    ) -> None:
        """Never let a short patch resize and shift the fixed-font bytearray."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources"
            sources.mkdir()
            (sources / "index.json").write_text(
                json.dumps(
                    {"chapters": [{"chapter": "TEST", "source": "TEST.json"}]}
                )
                + "\n",
                encoding="utf-8",
            )
            (sources / "TEST.json").write_text("{}\n", encoding="utf-8")
            build = root / "build"
            retail = build / "retail_unpacked" / "TEST"
            retail.mkdir(parents=True)
            (retail / "TEST.MES").write_bytes(b"retail mes")
            (retail / "TEST.SCN").write_bytes(b"retail scn")
            retail_font = build / "retail_files" / "FIX_CODE.FNT"
            retail_font.parent.mkdir(parents=True)
            retail_font.write_bytes(b"\0" * (GLYPH_BYTES * 2))

            def fake_compile_files(
                _retail_mes: Path,
                _retail_scn: Path,
                _source: Path,
                output: Path,
                *,
                glyph_order: str,
            ) -> BuildResult:
                """Return one deliberately malformed fixed-font patch."""
                self.assertEqual(glyph_order, "first-use")
                output.write_bytes(b"compiled\0")
                return BuildResult(
                    data=b"compiled\0",
                    record_count=1,
                    translated_records=1,
                    preserved_records=0,
                    split_offset=2,
                    dynamic_glyphs=1,
                    rendered_cells=1,
                    scn_layout_records=1,
                    fixed_spill_count=1,
                    fixed_spill_occurrences=1,
                    fixed_font_patches=(
                        (1, (b"X" * (GLYPH_BYTES - 1)).hex()),
                    ),
                    glyph_order="first-use",
                )

            with (
                patch.object(mes_set, "SOURCES", sources),
                patch.object(mes_set, "compile_files", fake_compile_files),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    rf"fixed-font patch 0x01 is {GLYPH_BYTES - 1} bytes; expected {GLYPH_BYTES}",
                ):
                    mes_set.build_mes_set(build)

            self.assertFalse((build / "FIX_CODE.FNT").exists())
            self.assertEqual(
                retail_font.read_bytes(), b"\0" * (GLYPH_BYTES * 2)
            )


if __name__ == "__main__":
    unittest.main()

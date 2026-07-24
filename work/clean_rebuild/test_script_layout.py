#!/usr/bin/env python3
"""Regression tests for the role-aware script formatting contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import mes_compiler
from font_render import GLYPH_BYTES
from mes_compiler import compile_files
from mes_format import DYNAMIC_PREFIX_START, parse_mes
from scn_layout import (
    ROLE_CHOICE,
    ROLE_DIALOGUE,
    ROLE_LOCATION,
    ROLE_NARRATION,
    ROLE_PERSPECTIVE,
    ROLE_THOUGHT,
    infer_contracts,
)
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES
from translation_formatter import audit_layouts, format_preview


HERE = Path(__file__).resolve().parent


def source(chapter: str) -> dict[str, object]:
    return json.loads((SOURCES / f"{chapter}.json").read_text(encoding="utf-8"))


def contracts(chapter: str) -> dict[int, object]:
    canonical = source(chapter)
    scn = (
        DEFAULT_RETAIL_ROOT
        / "retail_unpacked"
        / chapter
        / f"{chapter}.SCN"
    ).read_bytes()
    translated = {
        record["index"]
        for record in canonical["records"]
        if record["policy"] == "translate"
    }
    return infer_contracts(
        scn,
        canonical["record_count"],
        translated,
        canonical.get("profile"),
    )


def patched_font(retail_font: bytes, patches: tuple[tuple[int, str], ...]) -> bytes:
    """Apply one build result's declared fixed-font changes."""
    output = bytearray(retail_font)
    for code, bitmap_hex in patches:
        start = (code - 1) * GLYPH_BYTES
        output[start : start + GLYPH_BYTES] = bytes.fromhex(bitmap_hex)
    return bytes(output)


def bitmap_records(mes_data: bytes, fixed_font: bytes) -> tuple[tuple[bytes, ...], ...]:
    """Decode each MES record to its exact displayed bitmap sequence."""
    mes = parse_mes(mes_data)
    output: list[tuple[bytes, ...]] = []
    for record in mes.records:
        bitmaps: list[bytes] = []
        offset = 0
        while offset < len(record):
            value = record[offset]
            if value == 0:
                break
            if value < DYNAMIC_PREFIX_START:
                start = (value - 1) * GLYPH_BYTES
                bitmaps.append(fixed_font[start : start + GLYPH_BYTES])
                offset += 1
                continue
            index = (value - DYNAMIC_PREFIX_START) * 0xFF + record[offset + 1] - 1
            bitmaps.append(mes.glyphs[index])
            offset += 2
        output.append(tuple(bitmaps))
    return tuple(output)


class ScriptLayoutTests(unittest.TestCase):
    def test_start_narration_contract_and_rows(self) -> None:
        canonical = source("START")
        contract = contracts("START")[0]
        self.assertEqual(contract.roles, frozenset((ROLE_NARRATION,)))
        self.assertEqual(
            (
                contract.layout.visible_first,
                contract.layout.visible_continuation,
                contract.layout.runtime_first,
                contract.layout.runtime_continuation,
            ),
            (16, 16, 16, 16),
        )
        self.assertEqual(contract.max_rows, 6)
        rows = format_preview(canonical["records"][0]["text"], contract)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(len(row) <= 32 for row in rows))
        self.assertEqual(" ".join(rows), canonical["records"][0]["text"])

    def test_part1a_scene_roles_and_no_split_words(self) -> None:
        canonical = source("PART1A")
        inferred = contracts("PART1A")
        self.assertIn(ROLE_LOCATION, inferred[0].roles)
        self.assertIn(ROLE_PERSPECTIVE, inferred[1].roles)
        self.assertIn(ROLE_DIALOGUE, inferred[3].roles)
        rows = format_preview(canonical["records"][3]["text"], inferred[3])
        self.assertEqual(
            rows,
            ["How about we switch", "games and play one", "more round?"],
        )
        self.assertEqual(" ".join(rows), canonical["records"][3]["text"])
        rows = format_preview(canonical["records"][6]["text"], inferred[6])
        self.assertEqual(rows, ["How about Indian poker?", "Know the rules?"])

    def test_prologue_dialogue_reflows_without_screenshot_splits(self) -> None:
        canonical = source("PART1A")
        inferred = contracts("PART1A")
        expected = {
            16: ["I know. I read your face", "when you see my card."],
            17: ["Hee hee, you may be", "tough. But I am lucky."],
            18: ["Women are usually liars.", "Let us begin."],
        }
        for index, rows in expected.items():
            with self.subTest(index=index):
                self.assertEqual(
                    format_preview(canonical["records"][index]["text"], inferred[index]),
                    rows,
                )

    def test_selector_and_standalone_window_continuation_are_classified(self) -> None:
        part1a = contracts("PART1A")
        self.assertIn(ROLE_CHOICE, part1a[39].roles)
        self.assertIn(ROLE_CHOICE, part1a[40].roles)
        self.assertEqual(part1a[40].layout.visible_first, 8)
        self.assertEqual(part1a[40].max_rows, 6)

        part1c = contracts("PART1C")
        self.assertIn(ROLE_THOUGHT, part1c[97].roles)
        self.assertEqual(part1c[97].layout.visible_first, 8)
        self.assertEqual(part1c[97].max_rows, 10)

    def test_whole_game_audit_requires_exhaustive_layout_policy(self) -> None:
        report = audit_layouts()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["adaptive_record_count"], 2759)
        self.assertEqual(report["classified_record_count"], 2759)
        self.assertEqual(report["fixed_record_count"], 123)
        self.assertEqual(report["undeclared_record_count"], 0)
        self.assertEqual(report["unmigrated_classified_count"], 0)
        self.assertEqual(report["failure_count"], 0)
        self.assertEqual(report["legacy_issue_count"], 0)

    def test_every_chapter_compiles_from_hash_locked_inputs(self) -> None:
        index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            for item in index["chapters"]:
                chapter = item["chapter"]
                retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
                result = compile_files(
                    retail / f"{chapter}.MES",
                    retail / f"{chapter}.SCN",
                    SOURCES / f"{chapter}.json",
                    output / f"{chapter}.MES",
                )
                self.assertEqual(result.record_count, source(chapter)["record_count"])
                self.assertLessEqual(result.dynamic_glyphs, 1020)

    def test_part3c_spill_compaction_is_bitmap_identical(self) -> None:
        retail_root = DEFAULT_RETAIL_ROOT
        retail_dir = retail_root / "retail_unpacked" / "PART3C"
        retail_mes = (retail_dir / "PART3C.MES").read_bytes()
        retail_scn = (retail_dir / "PART3C.SCN").read_bytes()
        canonical = source("PART3C")
        all_spills = mes_compiler.PART3C_FIXED_UNITS
        hard_limit = mes_compiler.PART3C_HARD_LIMIT
        try:
            mes_compiler.PART3C_FIXED_UNITS = all_spills[6:]
            mes_compiler.PART3C_HARD_LIMIT = 0xFFFF
            before = mes_compiler.compile_mes(retail_mes, retail_scn, canonical)
        finally:
            mes_compiler.PART3C_FIXED_UNITS = all_spills
            mes_compiler.PART3C_HARD_LIMIT = hard_limit
        after = mes_compiler.compile_mes(retail_mes, retail_scn, canonical)
        self.assertGreater(len(before.data), 0x3FFF)
        self.assertEqual(len(after.data), 0x3F89)
        self.assertLessEqual(len(after.data), 0x3FFF)

        retail_font = (retail_root / "retail_files" / "FIX_CODE.FNT").read_bytes()
        before_font = patched_font(retail_font, before.fixed_font_patches)
        after_font = patched_font(retail_font, after.fixed_font_patches)
        self.assertEqual(
            bitmap_records(before.data, before_font),
            bitmap_records(after.data, after_font),
        )


if __name__ == "__main__":
    unittest.main()

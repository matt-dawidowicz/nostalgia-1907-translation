#!/usr/bin/env python3
"""Regression tests for the role-aware script formatting contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from work.clean_rebuild import mes_compiler
from work.clean_rebuild.font_render import GLYPH_BYTES, stored_cell
from work.clean_rebuild.mes_compiler import compile_files
from work.clean_rebuild.mes_format import DYNAMIC_PREFIX_START, parse_mes
from work.clean_rebuild.renderer_format import measure_literal
from work.clean_rebuild.source_json import load_json_object
from work.clean_rebuild.scn_layout import (
    ROLE_CHOICE,
    ROLE_CONTINUATION,
    ROLE_DIALOGUE,
    ROLE_LOCATION,
    ROLE_NARRATION,
    ROLE_OVERLAY,
    ROLE_PERSPECTIVE,
    ROLE_THOUGHT,
    TEXT_BOX_LOWER_CONTINUATION,
    TEXT_BOX_LOWER_DIALOGUE,
    infer_contracts,
)
from work.clean_rebuild.translation_audit import DEFAULT_RETAIL_ROOT, SOURCES
from work.clean_rebuild.translation_formatter import (
    _renderer_boundary_failures,
    audit_layouts,
    format_preview,
)
from work.clean_rebuild.whole_game_test import build_plan, verify_runtime_log


HERE = Path(__file__).resolve().parent


def required_retail_layout_files(
    retail_root: Path = DEFAULT_RETAIL_ROOT,
) -> tuple[Path, ...]:
    """Return every retail MES/SCN/font fixture required by this test module."""
    index = load_json_object(SOURCES / "index.json")
    files = [retail_root / "retail_files" / "FIX_CODE.FNT"]
    for item in index["chapters"]:
        chapter = item["chapter"]
        chapter_root = retail_root / "retail_unpacked" / chapter
        files.extend(
            (
                chapter_root / f"{chapter}.MES",
                chapter_root / f"{chapter}.SCN",
            )
        )
    return tuple(files)


def require_retail_layout_fixtures(
    retail_root: Path = DEFAULT_RETAIL_ROOT,
) -> None:
    """Skip layout integration tests when prepared retail fixtures are absent."""
    missing = [
        path for path in required_retail_layout_files(retail_root) if not path.is_file()
    ]
    if not missing:
        return
    examples = ", ".join(str(path) for path in missing[:3])
    remainder = len(missing) - min(len(missing), 3)
    suffix = f" (and {remainder} more)" if remainder else ""
    raise unittest.SkipTest(
        "prepared retail MES/SCN/font fixtures are unavailable; "
        f"missing {examples}{suffix}. Run the supported prepare/validate workflow "
        "with the verified retail tracks to execute these integration tests."
    )


def source(chapter: str) -> dict[str, object]:
    """Load one canonical chapter object by its production identifier."""
    return load_json_object(SOURCES / f"{chapter}.json")


def contracts(chapter: str) -> dict[int, object]:
    """Infer renderer contracts from hash-locked SCN and MES evidence."""
    canonical = source(chapter)
    retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
    scn = (retail / f"{chapter}.SCN").read_bytes()
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
        retail_records=parse_mes((retail / f"{chapter}.MES").read_bytes()).records,
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


def expected_prose_bitmaps(
    record_index: int,
    text: str,
    layout: object,
) -> tuple[tuple[bytes, ...], tuple[int, ...]]:
    """Return compiled bitmaps and the one-time opening-anchor offsets.

    A normal lower-dialogue record begins with a native quote-gutter cell.
    English uses a blank in that one initial cell; the renderer preserves it
    while all continuation rows start one cell to the right.  The MES stream
    has no row delimiters, so retain the absolute anchor position as part of
    the byte-level contract.
    """
    working = mes_compiler.normalize_ellipsis_style(
        mes_compiler.normalize_semantic_text(text)
    )
    cells: list[bytes] = []
    anchor_offsets: list[int] = []
    for row_index, (prefix, line) in enumerate(
        mes_compiler._prose_rows(working, layout)
    ):
        if prefix:
            anchor_offsets.append(len(cells))
        cells.extend(
            stored_cell(*cell)
            for cell in mes_compiler._row_plan(record_index, line, prefix).cells()
        )
    return tuple(cells), tuple(anchor_offsets)


class ScriptLayoutTests(unittest.TestCase):
    """Protect shared renderer inference, wrapping, and compiler boundaries."""

    @classmethod
    def setUpClass(cls) -> None:
        """Require the complete retail-backed fixture set once for the class."""
        super().setUpClass()
        require_retail_layout_fixtures()

    def test_start_narration_contract_and_rows(self) -> None:
        """Keep full-screen START narration within its proven six-row box."""
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
        self.assertEqual(
            rows,
            [
                "The past slips into fantasy as",
                "easily as any future we imagine.",
                "I didn't notice the faint scar",
                "in her left eye then, not in",
                "that fleeting instant.",
            ],
        )
        self.assertLessEqual(len(rows), contract.max_rows)
        self.assertTrue(all(len(row) <= 32 for row in rows))
        self.assertEqual(" ".join(rows), canonical["records"][0]["text"])

    def test_part1a_scene_roles_and_no_split_words(self) -> None:
        """Keep prologue roles and general word wrapping source-derived."""
        canonical = source("PART1A")
        inferred = contracts("PART1A")
        self.assertIn(ROLE_LOCATION, inferred[0].roles)
        self.assertIn(ROLE_PERSPECTIVE, inferred[1].roles)
        self.assertIn(ROLE_DIALOGUE, inferred[3].roles)
        rows = format_preview(canonical["records"][3]["text"], inferred[3])
        self.assertEqual(
            rows,
            ["Want to switch games", "and play one more", "round?"],
        )
        self.assertEqual(" ".join(rows), canonical["records"][3]["text"])
        rows = format_preview(canonical["records"][6]["text"], inferred[6])
        self.assertEqual(
            rows,
            ["How about Indian", "poker? Know how to", "play?"],
        )

    def test_lower_dialogue_keeps_continuation_width_after_page_cycle(self) -> None:
        """Keep lower-dialogue page clears separate from X-coordinate geometry."""
        canonical = source("PART1A")
        contract = contracts("PART1A")[10]
        self.assertEqual(contract.layout.page_rows, 3)
        self.assertFalse(contract.layout.repeat_first_row_on_page)
        self.assertEqual(contract.layout.opening_anchor_cells, 1)
        self.assertEqual(contract.layout.text_box, TEXT_BOX_LOWER_DIALOGUE)
        self.assertEqual(contract.layout.visible_cadence(), (11, 11, 11))
        self.assertEqual(contract.layout.physical_cadence(), (12, 11, 11))
        self.assertEqual(
            [contract.layout.visible_cells(index) for index in range(7)],
            [11, 11, 11, 11, 11, 11, 11],
        )
        self.assertEqual(
            [contract.layout.physical_cells(index) for index in range(7)],
            [12, 11, 11, 11, 11, 11, 11],
        )
        row_specs = mes_compiler._prose_rows(
            canonical["records"][10]["text"], contract.layout
        )
        self.assertEqual(
            [len(prefix) for prefix, _line in row_specs],
            [1] + [0] * (len(row_specs) - 1),
        )
        self.assertEqual(row_specs[0][0], (mes_compiler.BLANK_CELL,))
        self.assertEqual(
            [
                len(prefix) + measure_literal(line)
                for prefix, line in row_specs
            ],
            [12] + [11] * (len(row_specs) - 1),
        )
        self.assertEqual(
            format_preview(canonical["records"][10]["text"], contract),
            [
                "We each draw one card",
                "and show it to the",
                "other person, without",
                "looking at our own.",
                "Then we bet based on",
                "what we see.",
            ],
        )

    def test_opening_anchor_follows_retail_byte_evidence_and_profile_geometry(
        self,
    ) -> None:
        """Anchor only quote-bearing dialogue without flattening its profile."""
        cases = (
            ("PART1D", 84, 0x01, (11, 11, 11, 11, 0)),
            ("PART2F", 119, 0x12, (12, 10, 12, 11, 0)),
            ("PART3B", 3, 0x10, (12, 10, 12, 11, 1)),
        )
        for chapter, index, opening_code, geometry in cases:
            with self.subTest(chapter=chapter, index=index):
                retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
                retail_records = parse_mes(
                    (retail / f"{chapter}.MES").read_bytes()
                ).records
                contract = contracts(chapter)[index]
                self.assertIn(ROLE_DIALOGUE, contract.roles)
                self.assertEqual(retail_records[index][0], opening_code)
                self.assertEqual(
                    (
                        contract.layout.visible_first,
                        contract.layout.visible_continuation,
                        contract.layout.runtime_first,
                        contract.layout.runtime_continuation,
                        contract.layout.opening_anchor_cells,
                    ),
                    geometry,
                )

    def test_other_prose_boxes_compile_with_their_own_geometry(self) -> None:
        """Compile narration, thought, overlay, and continuation box samples.

        These renderers do not share the lower dialogue box's geometry.  Keep
        their tested widths, row limits, and physical cell streams independent
        so a lower-dialogue fix cannot silently change a floating window.
        """
        cases = (
            (
                "START",
                0,
                ROLE_NARRATION,
                (16, 16, 16, 16),
                6,
            ),
            (
                "PART1A",
                29,
                ROLE_THOUGHT,
                (8, 8, 8, 8),
                6,
            ),
            (
                "PART2C",
                8,
                ROLE_OVERLAY,
                (8, 8, 8, 8),
                5,
            ),
            (
                "PART1A",
                20,
                ROLE_CONTINUATION,
                (11, 10, 11, 11),
                None,
            ),
        )
        compiled: dict[str, mes_compiler.BuildResult] = {}
        for chapter, index, role, geometry, max_rows in cases:
            with self.subTest(chapter=chapter, index=index, role=role):
                canonical = source(chapter)
                contract = contracts(chapter)[index]
                self.assertIn(role, contract.roles)
                self.assertEqual(
                    (
                        contract.layout.visible_first,
                        contract.layout.visible_continuation,
                        contract.layout.runtime_first,
                        contract.layout.runtime_continuation,
                    ),
                    geometry,
                )
                self.assertEqual(contract.max_rows, max_rows)

                text = canonical["records"][index]["text"]
                rows = format_preview(text, contract)
                self.assertEqual(_renderer_boundary_failures(text, rows, contract), [])
                if max_rows is not None:
                    self.assertLessEqual(len(rows), max_rows)

                row_specs = mes_compiler._prose_rows(text, contract.layout)
                self.assertEqual(len(row_specs), len(rows))
                self.assertTrue(all(not prefix for prefix, _line in row_specs))
                self.assertEqual(
                    [
                        measure_literal(line)
                        for _prefix, line in row_specs
                    ],
                    [contract.layout.runtime_cells(row) for row in range(len(rows))],
                )

                if chapter not in compiled:
                    retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
                    compiled[chapter] = mes_compiler.compile_mes(
                        (retail / f"{chapter}.MES").read_bytes(),
                        (retail / f"{chapter}.SCN").read_bytes(),
                        canonical,
                    )
                self.assertEqual(
                    parse_mes(compiled[chapter].data).record_count,
                    canonical["record_count"],
                )

    def test_floating_window_overflow_is_rejected_during_compilation(self) -> None:
        """Reject overflow in a side thought before a MES file can be written."""
        chapter = "PART1A"
        canonical = source(chapter)
        altered = json.loads(json.dumps(canonical))
        altered["records"][29]["text"] = " ".join(("overflow",) * 64)
        retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
        with self.assertRaisesRegex(
            mes_compiler.CompileError,
            r"PART1A:029 uses .* rows in a floating window with a 6-row limit",
        ):
            mes_compiler.compile_mes(
                (retail / f"{chapter}.MES").read_bytes(),
                (retail / f"{chapter}.SCN").read_bytes(),
                altered,
            )

    def test_compiled_lower_dialogue_keeps_only_the_initial_blank_anchor(self) -> None:
        """Verify native quote gutters are emitted once, never at page resets."""
        source_index = load_json_object(SOURCES / "index.json")
        retail_font = (
            DEFAULT_RETAIL_ROOT / "retail_files" / "FIX_CODE.FNT"
        ).read_bytes()
        checked_records = 0
        checked_anchor_cells = 0
        unanchored_dialogue = 0
        checked_dialogue = 0
        for item in source_index["chapters"]:
            chapter = item["chapter"]
            canonical = source(chapter)
            retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
            result = mes_compiler.compile_mes(
                (retail / f"{chapter}.MES").read_bytes(),
                (retail / f"{chapter}.SCN").read_bytes(),
                canonical,
            )
            rendered = bitmap_records(
                result.data,
                patched_font(retail_font, result.fixed_font_patches),
            )
            chapter_contracts = contracts(chapter)
            for record in canonical["records"]:
                record_index = record["index"]
                contract = chapter_contracts.get(record_index)
                if (
                    record["policy"] != "translate"
                    or record.get("layout_policy") == "anchor"
                    or contract is None
                    or contract.layout is None
                    or ROLE_DIALOGUE not in contract.roles
                ):
                    continue
                expected, anchor_offsets = expected_prose_bitmaps(
                    record_index,
                    record["text"],
                    contract.layout,
                )
                with self.subTest(chapter=chapter, index=record_index):
                    self.assertEqual(rendered[record_index], expected)
                    row_specs = mes_compiler._prose_rows(
                        record["text"], contract.layout
                    )
                    if contract.layout.opening_anchor_cells == 0:
                        self.assertEqual(anchor_offsets, ())
                        self.assertEqual(row_specs[0][0], ())
                        unanchored_dialogue += 1
                    else:
                        self.assertEqual(anchor_offsets, (0,))
                        self.assertEqual(
                            parse_mes(result.data).records[record_index][0],
                            mes_compiler.FIXED_BLANK_CELL_CODE,
                        )
                        self.assertTrue(
                            all(not prefix for prefix, _line in row_specs[1:])
                        )
                        checked_records += 1
                        checked_anchor_cells += len(anchor_offsets)
                checked_dialogue += 1
        self.assertEqual(checked_dialogue, 1926)
        self.assertEqual(checked_records, 1912)
        self.assertEqual(checked_anchor_cells, checked_records)
        self.assertEqual(unanchored_dialogue, 14)

    def test_prologue_dialogue_reflows_without_screenshot_splits(self) -> None:
        """Prevent stale screenshot-specific breaks in adaptive dialogue."""
        canonical = source("PART1A")
        inferred = contracts("PART1A")
        expected = {
            16: ["I get it. I read your", "face when you see my", "card."],
            17: ["Heh. You look tough.", "But I'm a liar."],
            18: ["Most women are liars", "anyway. Let's play."],
        }
        for index, rows in expected.items():
            with self.subTest(index=index):
                self.assertEqual(
                    format_preview(
                        canonical["records"][index]["text"], inferred[index]
                    ),
                    rows,
                )

    def test_renderer_boundary_audit_rejects_a_fragmented_word(self) -> None:
        """Reject a word whose letters cross a simulated renderer row edge."""
        contract = contracts("PART1A")[17]
        failures = _renderer_boundary_failures(
            "Hee hee, you may be tough. But I am lucky.",
            ["Hee hee, you may be t", "ugh. But I am lucky."],
            contract,
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("tough.", failures[0])

    def test_selector_and_standalone_window_continuation_are_classified(self) -> None:
        """Classify selector choices and standalone continuation windows."""
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
        """Require all adaptive records to fit and preserve whole source words."""
        report = audit_layouts()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["adaptive_record_count"], 2759)
        self.assertEqual(report["classified_record_count"], 2760)
        self.assertEqual(report["fixed_record_count"], 123)
        self.assertEqual(report["anchor_record_count"], 1)
        self.assertEqual(report["undeclared_record_count"], 0)
        self.assertEqual(report["unmigrated_classified_count"], 0)
        self.assertEqual(report["failure_count"], 0)
        self.assertEqual(report["legacy_issue_count"], 0)

    def test_whole_game_certification_plan_covers_static_and_runtime_scope(
        self,
    ) -> None:
        """Inventory every chapter while keeping runtime proof explicitly pending."""
        plan = build_plan()
        static = plan["static"]
        self.assertEqual(static["layout"]["status"], "PASS")
        self.assertEqual(static["emitted_renderer"]["status"], "pass")
        self.assertEqual(static["emitted_renderer"]["chapters"], 19)
        self.assertEqual(static["emitted_renderer"]["records"], 2905)
        self.assertEqual(static["emitted_renderer"]["renderer_contract_records"], 2490)
        self.assertEqual(len(plan["runtime"]["chapters"]), 19)
        self.assertEqual(len(plan["runtime"]["fixed_layout_record_ids"]), 123)
        runtime = verify_runtime_log(plan)
        self.assertEqual(runtime["status"], "PENDING_RUNTIME")
        self.assertGreater(runtime["pending_count"], 19)

    def test_every_chapter_compiles_from_hash_locked_inputs(self) -> None:
        """Compile all chapters while preserving record and glyph limits."""
        index = load_json_object(SOURCES / "index.json")
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

    def test_fixed_english_dictionary_is_bitmap_identical(self) -> None:
        """Prove shared fixed-cell compression preserves every PART3C bitmap."""
        retail_root = DEFAULT_RETAIL_ROOT
        retail_dir = retail_root / "retail_unpacked" / "PART3C"
        retail_mes = (retail_dir / "PART3C.MES").read_bytes()
        retail_scn = (retail_dir / "PART3C.SCN").read_bytes()
        canonical = source("PART3C")
        dictionary = mes_compiler.FIXED_ENGLISH_UNITS
        hard_limit = mes_compiler.PART3C_HARD_LIMIT
        try:
            mes_compiler.FIXED_ENGLISH_UNITS = ()
            mes_compiler.PART3C_HARD_LIMIT = 0xFFFF
            before = mes_compiler.compile_mes(retail_mes, retail_scn, canonical)
        finally:
            mes_compiler.FIXED_ENGLISH_UNITS = dictionary
            mes_compiler.PART3C_HARD_LIMIT = hard_limit
        after = mes_compiler.compile_mes(retail_mes, retail_scn, canonical)
        self.assertGreater(len(before.data), 0x3FFF)
        # This dictionary is an encoding choice, not a layout choice. It must
        # leave a meaningful safety margin rather than merely crossing the
        # hard boundary by a few bytes.
        self.assertLess(len(after.data), len(before.data))
        self.assertLessEqual(len(after.data), hard_limit - 0x100)

        retail_font = (retail_root / "retail_files" / "FIX_CODE.FNT").read_bytes()
        before_font = patched_font(retail_font, before.fixed_font_patches)
        after_font = patched_font(retail_font, after.fixed_font_patches)
        self.assertEqual(
            bitmap_records(before.data, before_font),
            bitmap_records(after.data, after_font),
        )

    def test_fixed_english_dictionary_excludes_native_row_edge_codes(self) -> None:
        """Never emit a generated fixed byte with special row-edge semantics."""
        dictionary_codes = {
            code for code, _style, _unit in mes_compiler.FIXED_ENGLISH_UNITS
        }
        self.assertFalse(
            dictionary_codes & mes_compiler.NATIVE_DIALOGUE_ROW_EDGE_RESERVED_CODES
        )

        chapter = "PART1A"
        retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
        canonical = source(chapter)
        result = mes_compiler.compile_mes(
            (retail / f"{chapter}.MES").read_bytes(),
            (retail / f"{chapter}.SCN").read_bytes(),
            canonical,
        )
        parsed = parse_mes(result.data)
        inferred = contracts(chapter)
        for index, contract in inferred.items():
            if contract.layout is None or contract.layout.text_box not in {
                TEXT_BOX_LOWER_DIALOGUE,
                TEXT_BOX_LOWER_CONTINUATION,
            }:
                continue
            text = canonical["records"][index].get("text")
            if not isinstance(text, str):
                continue
            row_specs = mes_compiler._prose_rows(text, contract.layout)
            logical_cells: list[bytes] = []
            record = parsed.records[index]
            offset = 0
            while record[offset]:
                size = 2 if record[offset] >= DYNAMIC_PREFIX_START else 1
                logical_cells.append(record[offset : offset + size])
                offset += size
            cell_offset = 0
            for row_index, (_prefix, _line) in enumerate(row_specs[:-1]):
                cell_offset += contract.layout.physical_cells(row_index)
                self.assertNotIn(
                    logical_cells[cell_offset][0],
                    mes_compiler.NATIVE_DIALOGUE_ROW_EDGE_RESERVED_CODES,
                    msg=f"{chapter}:{index:03d} row {row_index + 1}",
                )

        # The compiled-byte audit is independent from the dictionary's static
        # allowlist. Reintroducing a reserved fixed byte for ``lo`` must fail
        # because PART1A:020 begins its second native continuation row with it.
        dictionary = mes_compiler.FIXED_ENGLISH_UNITS
        try:
            mes_compiler.FIXED_ENGLISH_UNITS = dictionary + ((0x05, "literal", "lo"),)
            with self.assertRaisesRegex(
                mes_compiler.CompileError,
                r"PART1A:\d{3} emits native row-edge code 0x05",
            ):
                mes_compiler.compile_mes(
                    (retail / f"{chapter}.MES").read_bytes(),
                    (retail / f"{chapter}.SCN").read_bytes(),
                    canonical,
                )
        finally:
            mes_compiler.FIXED_ENGLISH_UNITS = dictionary

    def test_compact_display_labels_preserve_canonical_translation(self) -> None:
        """Render compact nameplate text without weakening glossary authority."""
        cases = (
            ("PART2D", 145, "Chief Engineer", "Chief Eng.", 5),
            ("PART2E", 47, "Chief Engineer", "Chief Eng.", 5),
            ("PART2E", 26, "Royal Suite B", "Royal Suite B", 7),
        )
        for chapter, record_index, canonical_text, display_text, cell_count in cases:
            with self.subTest(chapter=chapter, record=record_index):
                retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
                canonical = source(chapter)
                record = canonical["records"][record_index]
                self.assertEqual(record["text"], canonical_text)
                self.assertEqual(record["display_text"], display_text)
                result = mes_compiler.compile_mes(
                    (retail / f"{chapter}.MES").read_bytes(),
                    (retail / f"{chapter}.SCN").read_bytes(),
                    canonical,
                )
                font = patched_font(
                    (DEFAULT_RETAIL_ROOT / "retail_files" / "FIX_CODE.FNT").read_bytes(),
                    result.fixed_font_patches,
                )
                rendered = bitmap_records(result.data, font)[record_index]
                expected = tuple(
                    stored_cell(*cell)
                    for cell in mes_compiler._row_plan(
                        record_index,
                        display_text,
                        (),
                    ).cells()
                )
                self.assertEqual(rendered, expected)
                self.assertEqual(len(rendered), cell_count)

    def test_standalone_quote_fragment_compiles_to_one_blank_cell(self) -> None:
        """Replace the visible Japanese quote marker without changing record order."""
        chapter = "PART2E"
        record_index = 28
        retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
        canonical = source(chapter)
        record = canonical["records"][record_index]
        self.assertEqual(record["policy"], "translate")
        self.assertEqual(record["text"], "")
        self.assertEqual(record["display_text"], "  ")
        self.assertEqual(record["layout_policy"], "anchor")
        result = mes_compiler.compile_mes(
            (retail / f"{chapter}.MES").read_bytes(),
            (retail / f"{chapter}.SCN").read_bytes(),
            canonical,
        )
        font = patched_font(
            (DEFAULT_RETAIL_ROOT / "retail_files" / "FIX_CODE.FNT").read_bytes(),
            result.fixed_font_patches,
        )
        rendered = bitmap_records(result.data, font)[record_index]
        self.assertEqual(rendered, (stored_cell("literal", "  "),))


if __name__ == "__main__":
    unittest.main()

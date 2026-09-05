#!/usr/bin/env python3
"""Regression tests for exhaustive text-box layout certification."""

from __future__ import annotations

import unittest

from work.clean_rebuild.box_layout_audit import (
    SPECIAL_LINE_CELLS,
    _occurrences,
    _row_details,
)
from work.clean_rebuild.renderer_format import measure_literal
from work.clean_rebuild.source_json import load_json_object
from work.clean_rebuild.translation_audit import SOURCES


class BoxLayoutAuditTests(unittest.TestCase):
    """Protect geometry learned from the retail script and MAIN.BIN renderer."""

    def test_special_line_opcodes_have_eighteen_cell_contract(self) -> None:
        """SCN 0x20/0x22/0x23 records inherit the proven 18-cell line width."""
        for opcode in (0x20, 0x22, 0x23):
            with self.subTest(opcode=opcode):
                uses = _occurrences(bytes((opcode, 0x00, 0x01)), 1, None)
                self.assertEqual(len(uses[0]), 1)
                self.assertEqual(uses[0][0]["permitted_cells"], SPECIAL_LINE_CELLS)
                self.assertEqual(uses[0][0]["max_rows"], 1)

    def test_special_countdown_window_has_two_cell_contract(self) -> None:
        """The retail 0x24/.../0x28 countdown form is a two-cell window."""
        scn = bytes((0x24, 0x17, 0x07, 0x05, 0x0C, 0x28, 0x00, 0x01))
        uses = _occurrences(scn, 1, None)
        self.assertEqual(len(uses[0]), 1)
        self.assertEqual(uses[0][0]["command"], "0x24/0x28")
        self.assertEqual(uses[0][0]["permitted_cells"], 2)
        self.assertEqual(uses[0][0]["max_rows"], 1)

    def test_fixed_row_details_preserve_literal_padding(self) -> None:
        """Fixed-layout auditing must not normalize away alignment spaces."""
        rows = _row_details(
            {
                "id": "TEST:000",
                "layout_policy": "fixed",
                "layout": None,
                "display_text": "  AB  ",
            }
        )
        self.assertEqual(rows[0]["text"], "  AB  ")
        self.assertEqual(rows[0]["leading_spaces"], 2)
        self.assertEqual(rows[0]["trailing_spaces"], 2)
        self.assertEqual(rows[0]["used_cells"], 3)

    def test_staff_rows_match_native_eighteen_cell_canvas(self) -> None:
        """Every credit row must remain exactly 36 source chars / 18 cells."""
        staff = load_json_object(SOURCES / "STAFF.json")
        for record in staff["records"]:
            if record.get("policy") != "translate":
                continue
            text = record["text"]
            with self.subTest(index=record["index"]):
                self.assertEqual(len(text), 36)
                self.assertEqual(measure_literal(text), SPECIAL_LINE_CELLS)


if __name__ == "__main__":
    unittest.main()

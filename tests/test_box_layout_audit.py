#!/usr/bin/env python3
"""Regression tests for exhaustive text-box layout certification."""

from __future__ import annotations

import unittest

from work.clean_rebuild.box_layout_audit import _row_details
from work.clean_rebuild.renderer_format import measure_literal
from work.clean_rebuild.scn_layout import (
    SPECIAL_LINE_CELLS,
    display_occurrences,
)
from work.clean_rebuild.source_json import load_json_object
from work.clean_rebuild.staff_credit_layout import (
    STAFF_CANVAS_CHARACTERS,
    audit_staff_credits,
    centered_credit_line,
)
from work.clean_rebuild.translation_audit import SOURCES


class BoxLayoutAuditTests(unittest.TestCase):
    """Protect geometry learned from the retail script and MAIN.BIN renderer."""

    def test_special_line_and_paired_labels_have_eighteen_cell_contract(
        self,
    ) -> None:
        """Use 18 cells for 0x20 and the exact adjacent 0x22/0x23 label pair."""
        fixed = display_occurrences(b"\x20\x00\x01", 1, None)
        self.assertEqual(len(fixed[0]), 1)
        self.assertEqual(fixed[0][0]["permitted_cells"], SPECIAL_LINE_CELLS)
        self.assertEqual(fixed[0][0]["max_rows"], 1)

        labels = display_occurrences(
            b"\x22\x00\x01\x23\x00\x02",
            2,
            None,
        )
        self.assertEqual(labels[0][0]["part"], "location_name")
        self.assertEqual(labels[0][0]["permitted_cells"], SPECIAL_LINE_CELLS)
        self.assertEqual(labels[0][0]["max_rows"], 1)
        self.assertEqual(labels[1][0]["part"], "perspective_name")
        self.assertEqual(labels[1][0]["permitted_cells"], SPECIAL_LINE_CELLS)
        self.assertEqual(labels[1][0]["max_rows"], 1)

    def test_isolated_label_opcode_bytes_are_not_occurrences(self) -> None:
        """Do not certify operand bytes as scene labels without the paired shape."""
        for scn in (b"\x22\x00\x01", b"\x23\x00\x01"):
            with self.subTest(scn=scn):
                self.assertEqual(display_occurrences(scn, 1, None), {})

    def test_special_countdown_window_has_two_cell_contract(self) -> None:
        """The retail 0x24/.../0x28 countdown form is a two-cell window."""
        scn = bytes((0x24, 0x17, 0x07, 0x05, 0x0C, 0x28, 0x00, 0x01))
        uses = display_occurrences(scn, 1, None)
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
        self.assertEqual(STAFF_CANVAS_CHARACTERS, SPECIAL_LINE_CELLS * 2)
        for record in staff["records"]:
            if record.get("policy") != "translate":
                continue
            text = record["text"]
            with self.subTest(index=record["index"]):
                self.assertEqual(len(text), STAFF_CANVAS_CHARACTERS)
                self.assertEqual(measure_literal(text), SPECIAL_LINE_CELLS)

    def test_staff_rows_are_centered_on_native_canvas(self) -> None:
        """Keep all fixed STAFF padding derived from one centering rule."""
        staff = load_json_object(SOURCES / "STAFF.json")
        report = audit_staff_credits(staff)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["audited_record_count"], 62)
        for record in staff["records"]:
            if record.get("policy") != "translate":
                continue
            text = record["text"]
            with self.subTest(index=record["index"]):
                self.assertEqual(text, centered_credit_line(text))

    def test_staff_centering_audit_rejects_left_aligned_short_credit(
        self,
    ) -> None:
        """Catch the observed Ruthie-style regression even when width still fits."""
        report = audit_staff_credits(
            {
                "chapter": "STAFF",
                "records": [
                    {
                        "index": 19,
                        "policy": "translate",
                        "text": "Ruthie".ljust(STAFF_CANVAS_CHARACTERS),
                    }
                ],
            }
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["failure_count"], 1)
        self.assertIn(
            "STAFF:019: credit is not centered", report["failures"][0]
        )
        self.assertIn("padding 0/30, expected 15/15", report["failures"][0])


if __name__ == "__main__":
    unittest.main()

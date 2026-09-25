#!/usr/bin/env python3
"""Regression tests for exhaustive text-box layout certification."""

from __future__ import annotations

import unittest

from work.clean_rebuild.box_layout_audit import _row_details
from work.clean_rebuild.renderer_format import measure_literal
from work.clean_rebuild.scn_layout import (
    FLOATING_WIDTHS,
    SCENE_LOCATION_CANVAS,
    SCENE_LOCATION_CHARACTERS,
    SCENE_LOCATION_TEXT_ORIGIN,
    SCENE_PERSPECTIVE_CANVAS,
    SCENE_PERSPECTIVE_CHARACTERS,
    SCENE_PERSPECTIVE_TEXT_ORIGIN,
    SPECIAL_LINE_CANVASES,
    SPECIAL_LINE_CELLS,
    SPECIAL_LINE_TEXT_ORIGINS,
    SPECIAL_LINE_TILE_BANKS,
    SPEAKER_NAME_CELLS,
    SPEAKER_NAME_CHARACTERS,
    SPEAKER_NAME_TEXT_ORIGINS,
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

    def test_special_line_and_paired_labels_use_native_geometry(self) -> None:
        """Bind 0x20 and paired 0x22/0x23 labels to their real canvases."""
        fixed = display_occurrences(b"\x20\x00\x01", 1, None)
        self.assertEqual(len(fixed[0]), 1)
        self.assertEqual(fixed[0][0]["permitted_cells"], SPECIAL_LINE_CELLS)
        self.assertEqual(fixed[0][0]["tile_banks"], SPECIAL_LINE_TILE_BANKS)
        self.assertEqual(fixed[0][0]["canvases"], SPECIAL_LINE_CANVASES)
        self.assertEqual(
            fixed[0][0]["text_origins"], SPECIAL_LINE_TEXT_ORIGINS
        )
        self.assertEqual(fixed[0][0]["max_rows"], 1)

        labels = display_occurrences(
            b"\x22\x00\x01\x23\x00\x02",
            2,
            None,
        )
        location = labels[0][0]
        self.assertEqual(location["part"], "location_name")
        self.assertEqual(
            location["permitted_characters"], SCENE_LOCATION_CHARACTERS
        )
        self.assertEqual(location["canvas"], SCENE_LOCATION_CANVAS)
        self.assertEqual(location["text_origin"], SCENE_LOCATION_TEXT_ORIGIN)
        self.assertEqual(location["max_rows"], 1)

        perspective = labels[1][0]
        self.assertEqual(perspective["part"], "perspective_name")
        self.assertEqual(
            perspective["permitted_characters"],
            SCENE_PERSPECTIVE_CHARACTERS,
        )
        self.assertEqual(perspective["canvas"], SCENE_PERSPECTIVE_CANVAS)
        self.assertEqual(
            perspective["text_origin"], SCENE_PERSPECTIVE_TEXT_ORIGIN
        )
        self.assertEqual(perspective["max_rows"], 1)

    def test_dialogue_speaker_uses_six_cell_native_region(self) -> None:
        """Bind 0x21 speaker names and state byte to the lower-strip geometry."""
        uses = display_occurrences(
            bytes((0x21, 0x00, 0x01, 0x00, 0x02, 0x3B)),
            2,
            None,
        )
        speaker = uses[0][0]
        self.assertEqual(speaker["part"], "speaker_name")
        self.assertEqual(speaker["permitted_cells"], SPEAKER_NAME_CELLS)
        self.assertEqual(
            speaker["permitted_characters"], SPEAKER_NAME_CHARACTERS
        )
        self.assertEqual(speaker["text_origins"], SPEAKER_NAME_TEXT_ORIGINS)
        self.assertEqual(speaker["local_text_origin_x"], 2)
        self.assertEqual(speaker["local_dialogue_anchor_x"], 0x4A)
        self.assertEqual(speaker["state_byte"], "0x3B")
        self.assertTrue(speaker["continuation_latch"])
        dialogue = uses[1][0]
        self.assertEqual(dialogue["state_byte"], "0x3B")
        self.assertTrue(dialogue["continuation_latch"])

    def test_isolated_label_opcode_bytes_are_not_occurrences(self) -> None:
        """Do not certify operand bytes as scene labels without the paired shape."""
        for scn in (b"\x22\x00\x01", b"\x23\x00\x01"):
            with self.subTest(scn=scn):
                self.assertEqual(display_occurrences(scn, 1, None), {})

    def test_floating_window_geometry_matches_native_arithmetic(self) -> None:
        """Derive cell width, origin, and indicator mode from SCN operands."""
        expected_widths = {
            0x07: 3,
            0x08: 4,
            0x09: 4,
            0x0A: 5,
            0x0B: 6,
            0x0C: 6,
            0x0D: 7,
            0x0E: 8,
            0x0F: 8,
            0x10: 9,
            0x11: 10,
            0x12: 10,
        }
        self.assertEqual(FLOATING_WIDTHS, expected_widths)

        thought = display_occurrences(
            bytes((0x24, 0x02, 0x0E, 0x0C, 0x0C, 0x27, 0x00, 0x01)),
            1,
            None,
        )[0][0]
        self.assertEqual(thought["permitted_cells"], 6)
        self.assertEqual(thought["text_origin"], (24, 122))
        self.assertEqual(thought["row_stride_pixels"], 16)
        self.assertEqual(thought["indicator"], "blinking_bottom_center")

        overlay = display_occurrences(
            bytes((0x24, 0x02, 0x0F, 0x0E, 0x0C, 0x28, 0x00, 0x01)),
            1,
            {"scn_window_text_subtypes": [0x28]},
        )[0][0]
        self.assertEqual(overlay["permitted_cells"], 8)
        self.assertEqual(overlay["text_origin"], (24, 130))
        self.assertEqual(overlay["indicator"], "none")

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

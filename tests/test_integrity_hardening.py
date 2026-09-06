#!/usr/bin/env python3
"""Adversarial tests for SCN references, MES preservation, and renderer limits."""

from __future__ import annotations

import unittest

from work.clean_rebuild.mes_format import MesFile, record_render_tokens
from work.clean_rebuild.renderer_format import wrap_words, wrapped_row_failures
from work.clean_rebuild.scn_layout import TEXT_BOX_SCENE_LABEL, Layout
from work.clean_rebuild.script_integrity import (
    choice_edges,
    fixed_layout_width_failure,
    scan_scn_text_references,
)


class ScriptIntegrityTests(unittest.TestCase):
    """Prove recognized SCN edges fail closed when their operands are unsafe."""

    def test_valid_choice_edge_is_inventoried(self) -> None:
        """Inventory a structurally valid 0x31 choice and its branch target."""
        scn = bytes((0x31, 0x00, 0x01, 0xFF, 0x00, 0x06, 0x72))
        references = scan_scn_text_references(scn, 1, None)
        edges = choice_edges(references)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].record_index, 0)
        self.assertEqual(edges[0].branch_target, 6)
        self.assertEqual(edges[0].target_opcode, 0x72)

    def test_out_of_range_choice_target_is_not_accepted(self) -> None:
        """Reject a 0x31 candidate whose branch destination leaves the SCN."""
        scn = bytes((0x31, 0x00, 0x01, 0xFF, 0x01, 0x00))
        references = scan_scn_text_references(scn, 1, None)
        self.assertFalse(any(item.command == "0x31" for item in references))

    def test_dialogue_reference_requires_in_range_record(self) -> None:
        """Accept valid 0x21 IDs and reject the same shape with a stale ID."""
        valid = bytes((0x21, 0x00, 0x01, 0x00, 0x02))
        refs = scan_scn_text_references(valid, 2, None)
        self.assertEqual(
            {(item.record_index, item.role) for item in refs},
            {(0, "speaker_name"), (1, "dialogue_body")},
        )
        invalid = bytes((0x21, 0x00, 0x01, 0x00, 0x03))
        refs = scan_scn_text_references(invalid, 2, None)
        self.assertFalse(any(item.command == "0x21" for item in refs))

    def test_fixed_special_renderer_rejects_one_cell_overflow(self) -> None:
        """Reject a 19-cell line in the proven 18-cell 0x20/0x22/0x23 family."""
        self.assertIsNone(fixed_layout_width_failure("A" * 36, ("0x20",)))
        self.assertEqual(
            fixed_layout_width_failure("A" * 37, ("0x20",)),
            "fixed renderer overflow: 19 > 18 cells",
        )

    def test_countdown_renderer_uses_two_cell_limit(self) -> None:
        """Apply the immediate 0x24/0x28 countdown window's two-cell capacity."""
        self.assertIsNone(fixed_layout_width_failure("1234", ("0x24/0x28",)))
        self.assertEqual(
            fixed_layout_width_failure("12345", ("0x24/0x28",)),
            "fixed renderer overflow: 3 > 2 cells",
        )


class PreservedRecordIdentityTests(unittest.TestCase):
    """Protect preserved content across legal dynamic-glyph index compaction."""

    @staticmethod
    def _mes(record: bytes, glyphs: tuple[bytes, ...]) -> MesFile:
        return MesFile(
            split_offset=0,
            pointers=(0,),
            records=(record,),
            glyphs=glyphs,
        )

    def test_dynamic_index_remap_with_same_bitmap_is_equivalent(self) -> None:
        """Treat glyph-index renumbering as equivalent when the bitmap is identical."""
        glyph_a = b"A" * 18
        glyph_b = b"B" * 18
        before = self._mes(bytes((0x41, 0xF0, 0x02, 0x00)), (glyph_a, glyph_b))
        after = self._mes(bytes((0x41, 0xF0, 0x01, 0x00)), (glyph_b,))
        self.assertEqual(
            record_render_tokens(before, 0), record_render_tokens(after, 0)
        )

    def test_fixed_or_control_byte_change_is_detected(self) -> None:
        """Reject a preserved record when any fixed or control byte changes."""
        glyph = b"G" * 18
        before = self._mes(bytes((0x41, 0xF0, 0x01, 0x00)), (glyph,))
        after = self._mes(bytes((0x42, 0xF0, 0x01, 0x00)), (glyph,))
        self.assertNotEqual(
            record_render_tokens(before, 0), record_render_tokens(after, 0)
        )

    def test_dynamic_bitmap_change_is_detected(self) -> None:
        """Reject a preserved record when a referenced dynamic glyph bitmap changes."""
        before = self._mes(bytes((0xF0, 0x01, 0x00)), (b"A" * 18,))
        after = self._mes(bytes((0xF0, 0x01, 0x00)), (b"B" * 18,))
        self.assertNotEqual(
            record_render_tokens(before, 0), record_render_tokens(after, 0)
        )


class RendererBoundaryCampaignTests(unittest.TestCase):
    """Exercise exact-width and one-past-width renderer boundaries."""

    def test_eighteen_cell_boundary_accepts_36_rejects_37_character_token(
        self,
    ) -> None:
        """Accept the 18-cell limit and reject one additional packed character."""
        layout = Layout(18, 18, 18, 18, text_box=TEXT_BOX_SCENE_LABEL)
        exact = "A" * 36
        exact_rows = wrap_words(exact, layout)
        self.assertEqual(exact_rows, [exact])
        self.assertEqual(wrapped_row_failures(exact, exact_rows, layout), [])

        overflow = "A" * 37
        overflow_rows = wrap_words(overflow, layout)
        failures = wrapped_row_failures(overflow, overflow_rows, layout)
        self.assertTrue(failures)
        self.assertTrue(
            any("splits or alters source token" in item for item in failures)
        )

    def test_dialogue_first_and_continuation_boundaries_are_distinct(
        self,
    ) -> None:
        """Keep the native 12-cell opening row distinct from 11-cell continuations."""
        layout = Layout(12, 11, 12, 11)
        self.assertEqual(layout.visible_cells(0), 12)
        self.assertEqual(layout.visible_cells(1), 11)
        self.assertEqual(layout.visible_cells(2), 11)
        self.assertEqual(layout.visible_cells(3), 11)


if __name__ == "__main__":
    unittest.main()

"""Regressions for runtime-proven English spacing and continuation geometry."""

from __future__ import annotations

import unittest

from work.clean_rebuild import font_render, mes_compiler, scn_layout


class ContractionSpacingTests(unittest.TestCase):
    """Keep every apostrophe on the ordinary monospaced character grid."""

    def test_contractions_do_not_use_phase_dependent_compact_cells(
        self,
    ) -> None:
        """Pack common contractions identically regardless of apostrophe phase."""
        expected = {
            "You're": (
                ("literal", "Yo"),
                ("literal", "u'"),
                ("literal", "re"),
            ),
            "didn't": (
                ("literal", "di"),
                ("literal", "dn"),
                ("literal", "'t"),
            ),
            "I'm": (("literal", "I'"), ("literal", "m")),
            "Let's": (("literal", "Le"), ("literal", "t'"), ("literal", "s")),
        }
        for text, units in expected.items():
            with self.subTest(text=text):
                packed = mes_compiler._pack_row(text)
                self.assertIsNotNone(packed)
                assert packed is not None
                self.assertEqual(
                    tuple(cell for cell in packed[1] if cell[1] != "  "), units
                )
                self.assertFalse(
                    any(style == "compact" for style, _unit in packed[1])
                )

    def test_apostrophe_mark_is_centered_inside_its_six_pixel_slot(
        self,
    ) -> None:
        """Keep the narrow mark away from either edge without changing advance."""
        leading = font_render._bytes_matrix(
            font_render.render_literal_cell("'t")
        )
        trailing = font_render._bytes_matrix(
            font_render.render_literal_cell("u'")
        )
        self.assertEqual(leading[2][2], 1)
        self.assertEqual(leading[2][0], 0)
        self.assertEqual(trailing[2][7], 1)
        self.assertEqual(trailing[2][6], 0)

    def test_apostrophe_contraction_is_not_an_allowed_compact_cluster(
        self,
    ) -> None:
        """Reserve compact three-character cells for ellipses and decimals only."""
        with self.assertRaises(font_render.FontError):
            font_render.render_compact_cluster("I'm")


class ContinuationAlignmentTests(unittest.TestCase):
    """Lock the native standalone lower-continuation row stride."""

    def test_lower_continuation_starts_on_eleven_cell_stride(self) -> None:
        """Never reintroduce the stale twelfth cell that indented later rows."""
        layouts = scn_layout.infer_layouts(
            b"\x21\x00\x01\x00\x00",
            1,
            {0},
            None,
            retail_records=(b"\x01\x00",),
        )
        layout = layouts[0]
        self.assertEqual(
            (
                layout.visible_first,
                layout.visible_continuation,
                layout.runtime_first,
                layout.runtime_continuation,
            ),
            (11, 10, 11, 11),
        )
        self.assertEqual(layout.opening_anchor_cells, 0)
        self.assertEqual(layout.physical_cells(0), 11)
        self.assertEqual(layout.physical_cells(1), 11)


if __name__ == "__main__":
    unittest.main()

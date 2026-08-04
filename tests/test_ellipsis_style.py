"""Tests for the translation-wide no-space ellipsis style contract."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
if str(CLEAN) not in sys.path:
    sys.path.insert(0, str(CLEAN))

from mes_compiler import (  # noqa: E402
    _reconstruct_wrapped_text,
    _wrap_words,
    normalize_ellipsis_style,
)
from scn_layout import Layout  # noqa: E402
from translation_formatter import _renderer_boundary_failures  # noqa: E402
from scn_layout import RecordContract  # noqa: E402
from apply_translation_repairs import _canonical_text  # noqa: E402
from font_render import _bytes_matrix, render_compact_cluster  # noqa: E402


class EllipsisStyleTests(unittest.TestCase):
    """Keep ellipsis styling global, reviewable, and safe for proper forms."""

    def test_ordinary_follower_is_attached_and_lowercased(self) -> None:
        """Remove the pause space and sentence-style capitalization together."""
        self.assertEqual(
            normalize_ellipsis_style("Wait... What happened... The door?"),
            "Wait...what happened...the door?",
        )

    def test_names_titles_acronyms_and_first_person_forms_remain_capitalized(
        self,
    ) -> None:
        """Preserve reviewed exceptions while still removing their pause space."""
        self.assertEqual(
            normalize_ellipsis_style(
                "... I know... Ilyu... Betty... Chief... ITO... Japanese... Tsar..."
            ),
            "...I know...Ilyu...Betty...Chief...ITO...Japanese...Tsar...",
        )

    def test_quoted_and_numeric_followers_are_attached(self) -> None:
        """Normalize quote and number continuations without restoring a pause gap."""
        self.assertEqual(
            normalize_ellipsis_style('"Wait... "The answer is 90... 100."'),
            '"Wait..."the answer is 90...100."',
        )

    def test_ellipsis_can_end_a_renderer_row_without_a_rendered_space(self) -> None:
        """Allow a soft renderer break while retaining canonical attached prose."""
        layout = Layout(
            visible_first=8,
            visible_continuation=8,
            runtime_first=8,
            runtime_continuation=8,
        )
        rows = _wrap_words("premeditated...we continue", layout)

        self.assertEqual(rows, ["premeditated...", "we continue"])
        self.assertEqual(_reconstruct_wrapped_text(rows), "premeditated...we continue")

    def test_terminal_punctuation_may_follow_an_ellipsis_on_the_next_row(self) -> None:
        """Treat ``...?`` as an ellipsis edge, not a broken source token."""
        contract = RecordContract(
            roles=frozenset(("main_dialogue",)),
            layout=Layout(10, 10, 10, 10),
            max_rows=2,
        )
        rows = _wrap_words("What are you plotting...?", contract.layout)

        self.assertEqual(
            _renderer_boundary_failures("What are you plotting...?", rows, contract), []
        )

    def test_repair_application_cannot_restore_the_legacy_ellipsis_style(self) -> None:
        """Apply the same no-space rule to editable repair-table prose."""
        self.assertEqual(
            _canonical_text("Two... Calling again.", adaptive=True),
            "Two...calling again.",
        )
        self.assertEqual(
            _canonical_text("Line one...\nThe next line.", adaptive=False),
            "Line one...\nthe next line.",
        )

    def test_compact_ellipsis_does_not_leave_a_blank_cell_tail(self) -> None:
        """Spread the three dots through their cell up to the following word."""
        matrix = _bytes_matrix(render_compact_cluster("..."))
        occupied_columns = sorted(
            {column for row in matrix for column, value in enumerate(row) if value}
        )

        self.assertEqual(occupied_columns, [0, 5, 10])

    def test_all_translated_canonical_records_already_follow_the_style(self) -> None:
        """Reject a future source edit that restores a spaced ellipsis pause."""
        sources = CLEAN / "sources"
        for path in sorted(sources.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for record in payload.get("records", []):
                if record.get("policy") != "translate":
                    continue
                text = record.get("text")
                with self.subTest(chapter=path.stem, index=record.get("index")):
                    self.assertIsInstance(text, str)
                    self.assertEqual(text, normalize_ellipsis_style(text))


if __name__ == "__main__":
    unittest.main()

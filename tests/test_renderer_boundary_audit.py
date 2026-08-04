"""Regression coverage for renderer-row token and packed-cell safeguards.

These source-only tests exercise the guard independently of the large retail
fixture set. The optional corpus integration case runs when the prepared
Japanese reference is available, while the normal test suite still proves that
the formatter's public audit path incorporates the guard.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
if str(CLEAN) not in sys.path:
    sys.path.insert(0, str(CLEAN))

from scn_layout import Layout, RecordContract  # noqa: E402
import translation_formatter  # noqa: E402


def dialogue_contract(*, visible_cells: int = 12) -> RecordContract:
    """Return a small, SCN-shaped dialogue contract for isolated tests.

    Args:
        visible_cells: Proven visible capacity for both row types. Runtime
            capacity deliberately matches it because padding is not under test.

    Returns:
        A stable two-row dialogue contract suitable for formatter audits.

    Side Effects:
        None.
    """
    return RecordContract(
        roles=frozenset(("main_dialogue",)),
        layout=Layout(
            visible_first=visible_cells,
            visible_continuation=visible_cells,
            runtime_first=visible_cells,
            runtime_continuation=visible_cells,
        ),
        max_rows=2,
    )


class RendererBoundaryUnitTests(unittest.TestCase):
    """Prove the boundary guard accepts valid rows and rejects bad ones."""

    def test_valid_formatter_rows_preserve_whole_tokens(self) -> None:
        """Accept ordinary wrapping that moves complete words between rows."""
        contract = dialogue_contract(visible_cells=4)
        semantic = "one two three"
        rows = translation_formatter.format_preview(semantic, contract)

        self.assertEqual(rows, ["one two", "three"])
        self.assertEqual(
            translation_formatter._renderer_boundary_failures(semantic, rows, contract),
            [],
        )

    def test_fragmented_word_is_rejected_at_a_renderer_row_edge(self) -> None:
        """Reject the equivalent of the observed ``t`` then ``ugh.`` failure."""
        contract = dialogue_contract()
        failures = translation_formatter._renderer_boundary_failures(
            "You may be tough.",
            ["You may be t", "ugh."],
            contract,
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("tough.", failures[0])

    def test_row_that_exceeds_packed_visible_cells_is_rejected(self) -> None:
        """Reject a row beyond its SCN-derived two-character cell capacity."""
        contract = dialogue_contract(visible_cells=4)
        failures = translation_formatter._renderer_boundary_failures(
            "one two three",
            ["one two three"],
            contract,
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("uses 7 visible cells", failures[0])

    def test_record_audit_includes_boundary_guard_failures(self) -> None:
        """Prove the public audit route cannot omit the lower-level guard."""
        contract = dialogue_contract()
        with patch.object(
            translation_formatter,
            "format_preview",
            return_value=["You may be t", "ugh."],
        ):
            audit = translation_formatter._record_audit(
                "TEST:000",
                "You may be tough.",
                True,
                contract,
                {},
            )

        self.assertTrue(
            any(
                "renderer row boundary splits" in failure
                for failure in audit["failures"]
            )
        )


class RendererBoundaryCorpusTests(unittest.TestCase):
    """Exercise the whole canonical script when prepared retail fixtures exist."""

    def test_current_adaptive_corpus_has_no_boundary_failures(self) -> None:
        """Audit all SCN-classified records through the production entry point."""
        try:
            report = translation_formatter.audit_layouts()
        except FileNotFoundError as error:
            self.skipTest(f"prepared Japanese retail fixtures unavailable: {error}")

        boundary_failures = [
            failure
            for failure in report["failures"]
            if "renderer row boundary splits" in failure
        ]
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["adaptive_record_count"], 2759)
        self.assertEqual(report["unclassified_layout_count"], 0)
        self.assertGreater(report["text_box_counts"].get("lower_dialogue", 0), 0)
        self.assertGreater(report["text_box_counts"].get("floating_window", 0), 0)
        self.assertEqual(boundary_failures, [])


if __name__ == "__main__":
    unittest.main()

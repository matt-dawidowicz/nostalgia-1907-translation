"""Source-only contracts for non-applying review exports."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
if str(CLEAN) not in sys.path:
    sys.path.insert(0, str(CLEAN))

import export_fixed_layout_review as fixed_review  # noqa: E402
import export_translation_proposals as proposals  # noqa: E402


class ReviewExportTests(unittest.TestCase):
    """Keep review priorities and Japanese evidence explicitly grounded."""

    def test_part4c_priority_block_is_complete_and_runtime_only(self) -> None:
        """Prioritize all nine records without deriving a static runtime claim."""
        self.assertEqual(
            fixed_review.PRIORITY_PART4C,
            {f"PART4C:{index:03d}" for index in range(51, 60)},
        )
        for record_id in sorted(fixed_review.PRIORITY_PART4C):
            priority, risk, rationale = fixed_review._risk(record_id, "sample", [3])
            self.assertEqual((priority, risk), (1, "HIGH"))
            self.assertIn("no SCN-derived geometry", rationale)
            self.assertNotIn("source images", rationale)
            evidence = fixed_review._runtime_evidence(record_id).lower()
            self.assertIn("replay the exact scene/branch", evidence)
            self.assertIn("full-frame capture", evidence)

    def test_approved_part2e_pair_matches_reviewed_japanese_evidence(self) -> None:
        """Bind both contextual revisions to reviewed Japanese and canonical text."""
        evidence = json.loads(proposals.EVIDENCE.read_text(encoding="utf-8"))
        expectations = evidence["record_expectations"]
        source = json.loads((proposals.SOURCES / "PART2E.json").read_text(encoding="utf-8"))
        canonical = {
            f"PART2E:{record['index']:03d}": record["text"]
            for record in source["records"]
        }
        expected = {
            "PART2E:212": "I've got the cutters on the red wire...I'm cutting it.",
            "PART2E:213": "I've got the cutters on the blue wire...I'm cutting it.",
        }
        self.assertEqual(proposals.PROPOSALS, {})
        for record_id, english in expected.items():
            with self.subTest(record_id=record_id):
                reviewed = expectations[record_id]
                self.assertTrue(reviewed["japanese"])
                self.assertTrue(reviewed["literal"])
                self.assertEqual(reviewed["corrected_english"], english)
                self.assertEqual(canonical[record_id], english)

    def test_empty_proposal_export_needs_no_retail_or_comparison_data(self) -> None:
        """Keep the no-pending state usable in a media-free Codex checkout."""
        payload = proposals.build_proposals(
            Path("missing-retail-root"),
            Path("missing-comparison.json"),
        )
        self.assertEqual(payload["status"], "NO_PENDING_PROPOSALS")
        self.assertEqual(payload["proposal_count"], 0)
        self.assertEqual(payload["proposals"], [])
        self.assertFalse(payload["canonical_sources_modified"])
        self.assertFalse(payload["bin_cue_built"])

    def test_empty_queue_never_enters_retail_boundary_analysis(self) -> None:
        """Avoid retail reads and recompression analysis when nothing is pending."""
        with patch.object(
            proposals,
            "_archive_boundary_context",
            side_effect=AssertionError("boundary analysis must not run"),
        ):
            payload = proposals.build_proposals(
                Path("missing-retail-root"),
                Path("missing-comparison.json"),
            )
        self.assertEqual(payload["status"], "NO_PENDING_PROPOSALS")


if __name__ == "__main__":
    unittest.main()

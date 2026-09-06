"""Source-only contracts for maintained review exports and evidence."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from work.clean_rebuild import export_fixed_layout_review as fixed_review

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
SOURCES = CLEAN / "sources"
EVIDENCE = CLEAN / "bomb_semantics.json"


class ReviewExportTests(unittest.TestCase):
    """Keep active review priorities and source evidence grounded."""

    def test_part4c_priority_block_is_complete_and_runtime_only(self) -> None:
        """Prioritize all nine records without deriving a static runtime claim."""
        self.assertEqual(
            fixed_review.PRIORITY_PART4C,
            {f"PART4C:{index:03d}" for index in range(51, 60)},
        )
        for record_id in sorted(fixed_review.PRIORITY_PART4C):
            priority, risk, rationale = fixed_review._risk(
                record_id, "sample", [3]
            )
            self.assertEqual((priority, risk), (1, "HIGH"))
            self.assertIn("no SCN-derived geometry", rationale)
            self.assertNotIn("source images", rationale)
            evidence = fixed_review._runtime_evidence(record_id).lower()
            self.assertIn("replay the exact scene/branch", evidence)
            self.assertIn("full-frame capture", evidence)

    def test_approved_part2e_pair_matches_reviewed_japanese_evidence(
        self,
    ) -> None:
        """Bind contextual revisions to reviewed Japanese and canonical text."""
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        expectations = evidence["record_expectations"]
        source = json.loads(
            (SOURCES / "PART2E.json").read_text(encoding="utf-8")
        )
        canonical = {
            f"PART2E:{record['index']:03d}": record["text"]
            for record in source["records"]
        }
        expected = {
            "PART2E:212": "I've got the cutters on the red wire...I'm cutting it.",
            "PART2E:213": "I've got the cutters on the blue wire...I'm cutting it.",
        }
        for record_id, english in expected.items():
            with self.subTest(record_id=record_id):
                reviewed = expectations[record_id]
                self.assertTrue(reviewed["japanese"])
                self.assertTrue(reviewed["literal"])
                self.assertEqual(reviewed["corrected_english"], english)
                self.assertEqual(canonical[record_id], english)


if __name__ == "__main__":
    unittest.main()

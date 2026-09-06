"""Source-level regression tests for whole-game certification bookkeeping."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from work.clean_rebuild.whole_game_test import (  # noqa: E402
    GLOBAL_RUNTIME_CHECKS,
    PASS,
    PLAN_SCHEMA_VERSION,
    bind_build_identity,
    verify_runtime_log,
    write_plan,
)


def complete_plan() -> dict[str, object]:
    """Return a minimal but fully bound synthetic certification plan."""
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "static": {
            "layout": {
                "status": "PASS",
                "text_box_counts": {"lower_dialogue": 1},
                "classified_record_count": 1,
                "adaptive_record_count": 1,
                "fixed_record_count": 0,
            },
            "emitted_renderer": {
                "status": PASS,
                "chapters": 1,
                "renderer_contract_rows": 1,
                "renderer_contract_cells": 1,
                "renderer_contract_row_edges": 0,
            },
            "scn_references": {
                "status": "PASS",
                "reference_count": 1,
                "choice_branch_count": 1,
            },
        },
        "runtime": {
            "build_identity": {
                "cue_filename": "candidate.cue",
                "cue_sha256": "A" * 64,
                "track1_filename": "candidate_Track1.bin",
                "track1_sha256": "B" * 64,
            },
            "global_checks": [
                {
                    "id": item_id,
                    "requirement": requirement,
                    "status": PASS,
                    "evidence": "observed",
                }
                for item_id, requirement in GLOBAL_RUNTIME_CHECKS
            ],
            "chapters": [
                {
                    "chapter": "PART1A",
                    "runtime_status": PASS,
                    "runtime_evidence": "route completed",
                }
            ],
            "text_boxes": [
                {
                    "text_box": "lower_dialogue",
                    "static_record_count": 1,
                    "example_record_ids": ["PART1A:000"],
                    "runtime_status": PASS,
                    "runtime_evidence": "dialogue observed",
                }
            ],
            "fixed_layout_record_ids": [],
            "branch_edges": [
                {
                    "id": "PART1A:0x10->0x20",
                    "record_id": "PART1A:000",
                    "branch_target": 0x20,
                    "target_opcode": 0x72,
                    "status": PASS,
                    "evidence": "choice exercised",
                }
            ],
            "issues": [],
        },
    }


class WholeGameRuntimeLogTests(unittest.TestCase):
    """Keep runtime-certification completion separate from static coverage."""

    def test_runtime_log_remains_pending_until_every_scope_is_marked(
        self,
    ) -> None:
        """Reject incomplete chapters and text boxes instead of optimistic success."""
        plan = complete_plan()
        plan["runtime"]["chapters"][0]["runtime_status"] = "pending"
        report = verify_runtime_log(plan)
        self.assertEqual(report["status"], "PENDING_RUNTIME")
        self.assertEqual(report["pending"], ["chapter:PART1A"])

    def test_runtime_log_passes_only_after_every_scope_is_recorded(
        self,
    ) -> None:
        """Accept a complete explicit runtime certification log."""
        report = verify_runtime_log(complete_plan())
        self.assertEqual(report["status"], PASS)

    def test_unbound_candidate_cannot_pass_runtime_certification(self) -> None:
        """Require exact CUE and Track 1 identities before accepting a runtime pass."""
        plan = complete_plan()
        plan["runtime"]["build_identity"] = {
            "cue_sha256": "RECORD_BEFORE_PLAYTEST",
            "track1_sha256": "RECORD_BEFORE_PLAYTEST",
        }
        report = verify_runtime_log(plan)
        self.assertEqual(report["status"], "PENDING_RUNTIME")
        self.assertIn("build_identity", report["pending"])

    def test_passed_scope_requires_evidence(self) -> None:
        """Do not accept a checked box with no route or observation note."""
        plan = complete_plan()
        plan["runtime"]["global_checks"][0]["evidence"] = ""
        report = verify_runtime_log(plan)
        self.assertEqual(report["status"], "PENDING_RUNTIME")
        self.assertIn("global:boot:evidence", report["pending"])

    def test_branch_scope_requires_evidence(self) -> None:
        """Require evidence for every statically inventoried choice branch."""
        plan = complete_plan()
        plan["runtime"]["branch_edges"][0]["evidence"] = ""
        report = verify_runtime_log(plan)
        self.assertEqual(report["status"], "PENDING_RUNTIME")
        self.assertIn("branch:PART1A:0x10->0x20:evidence", report["pending"])

    def test_static_failure_prevents_runtime_pass(self) -> None:
        """Keep human runtime evidence from overriding a failed static gate."""
        plan = complete_plan()
        plan["static"]["layout"]["status"] = "FAIL"
        report = verify_runtime_log(plan)
        self.assertEqual(report["status"], "PENDING_RUNTIME")
        self.assertIn("static:layout", report["failed"])

    def test_scope_deletion_is_rejected(self) -> None:
        """Reject edited logs that remove generated certification scopes."""
        plan = complete_plan()
        plan["runtime"]["global_checks"] = plan["runtime"]["global_checks"][
            :-1
        ]
        with self.assertRaisesRegex(ValueError, "global runtime checks"):
            verify_runtime_log(plan)

    def test_branch_deletion_is_rejected(self) -> None:
        """Reject edited logs that remove statically required choice branches."""
        plan = complete_plan()
        plan["runtime"]["branch_edges"] = []
        with self.assertRaisesRegex(ValueError, "choice-branch inventory"):
            verify_runtime_log(plan)

    def test_writer_refuses_to_replace_an_existing_plan(self) -> None:
        """Preserve an existing runtime log rather than overwriting playtest evidence."""
        plan = complete_plan()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan"
            json_path, markdown_path = write_plan(output, plan)
            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8")), plan
            )
            with self.assertRaises(ValueError):
                write_plan(output, plan)

    def test_build_binding_records_candidate_hashes(self) -> None:
        """Tie human playtest evidence to one exact BIN/CUE candidate."""
        plan = {"runtime": {"build_identity": {}}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cue = root / "candidate.cue"
            track1 = root / "candidate_Track1.bin"
            cue.write_bytes(b"cue\n")
            track1.write_bytes(b"track one\n")
            bind_build_identity(plan, cue, track1)
        identity = plan["runtime"]["build_identity"]
        self.assertEqual(identity["cue_filename"], "candidate.cue")
        self.assertEqual(identity["track1_filename"], "candidate_Track1.bin")
        self.assertEqual(len(identity["cue_sha256"]), 64)
        self.assertEqual(len(identity["track1_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()

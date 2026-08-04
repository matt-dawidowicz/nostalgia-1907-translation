"""Source-level regression tests for whole-game certification bookkeeping."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "clean_rebuild"))

from whole_game_test import (  # noqa: E402
    PASS,
    bind_build_identity,
    verify_runtime_log,
    write_plan,
)


class WholeGameRuntimeLogTests(unittest.TestCase):
    """Keep runtime-certification completion separate from static coverage."""

    def test_runtime_log_remains_pending_until_every_scope_is_marked(self) -> None:
        """Reject incomplete chapters and text boxes instead of optimistic success."""
        plan = {
            "runtime": {
                "global_checks": [{"id": "boot", "status": PASS}],
                "chapters": [{"chapter": "PART1A", "runtime_status": "pending"}],
                "text_boxes": [{"text_box": "lower_dialogue", "runtime_status": PASS}],
            }
        }
        report = verify_runtime_log(plan)
        self.assertEqual(report["status"], "PENDING_RUNTIME")
        self.assertEqual(report["pending"], ["chapter:PART1A"])

    def test_runtime_log_passes_only_after_every_scope_is_recorded(self) -> None:
        """Accept a complete explicit runtime certification log."""
        plan = {
            "runtime": {
                "global_checks": [{"id": "boot", "status": PASS}],
                "chapters": [{"chapter": "PART1A", "runtime_status": PASS}],
                "text_boxes": [{"text_box": "lower_dialogue", "runtime_status": PASS}],
            }
        }
        report = verify_runtime_log(plan)
        self.assertEqual(report["status"], PASS)

    def test_writer_refuses_to_replace_an_existing_plan(self) -> None:
        """Preserve an existing runtime log rather than overwriting playtest evidence."""
        plan = {
            "static": {
                "layout": {
                    "classified_record_count": 0,
                    "adaptive_record_count": 0,
                    "fixed_record_count": 0,
                },
                "emitted_renderer": {
                    "renderer_contract_rows": 0,
                    "renderer_contract_cells": 0,
                    "renderer_contract_row_edges": 0,
                },
            },
            "runtime": {"global_checks": [], "chapters": [], "text_boxes": []},
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan"
            json_path, markdown_path = write_plan(output, plan)
            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), plan)
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

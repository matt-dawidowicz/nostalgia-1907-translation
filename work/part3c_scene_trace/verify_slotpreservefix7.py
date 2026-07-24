#!/usr/bin/env python3
"""Verify slot-preserve fix 7 plus all row-parity fix 6 contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
FINAL = WORKSPACE / "outputs" / "PART3C_slotpreservefix7_fresh"
ORIGINAL_LZ = (
    WORKSPACE / "work" / "part3c_original_compare" / "original_extract" / "PART3C.LZ"
)

sys.path.insert(0, str(HERE))
sys.path.insert(
    0,
    r"C:\Users\thema\Documents\Codex\2026-07-12\i\outputs\nostalgia1907_tools",
)

import verify_rowparityfix6 as base  # noqa: E402
from nostalgia1907 import read_iso_record_refs, read_lz_entries  # noqa: E402


def main() -> None:
    """Run inherited content/disc regressions and original-offset guards."""
    base.FINAL = FINAL
    base.MES = FINAL / "PART3C.MES"
    base.SCN = FINAL / "PART3C.SCN"
    base.FONT = FINAL / "FIX_CODE.FNT"
    base.LZ = FINAL / "PART3C_slotpreservefix7.LZ"
    base.ISO = FINAL / "Nostalgia1907_Act3C_000_223_slotpreservefix7.iso"
    base.TRACK1 = FINAL / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track1.bin"
    base.TRACK2 = FINAL / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track2.bin"
    base.CUE = FINAL / "Nostalgia1907_Act3C_000_223_slotpreservefix7.cue"
    base.ISO_EXTRACT = FINAL / "iso_extract"
    base.UNPACKED = FINAL / "archive_candidate_unpacked"
    base.REGRESSION = FINAL / "regression_full"
    base.REPORT = FINAL / "final_verification.json"

    original = read_lz_entries(ORIGINAL_LZ)
    delivered = read_lz_entries(base.LZ)
    if len(original) != len(delivered):
        raise ValueError("LZ inventory count differs from original")
    mismatches = [
        {
            "index": before.index,
            "name": before.name,
            "original": before.offset,
            "delivered": after.offset,
        }
        for before, after in zip(original, delivered)
        if before.name != after.name or before.offset != after.offset
    ]
    if mismatches:
        raise ValueError(f"LZ member offset regression: {mismatches}")
    if base.LZ.stat().st_size != ORIGINAL_LZ.stat().st_size:
        raise ValueError("LZ byte length is not the original byte length")

    refs = read_iso_record_refs(base.ISO)
    part3c = [
        ref
        for ref in refs
        if not ref.is_dir and Path(ref.path).name.upper() == "PART3C.LZ"
    ]
    layouts = {(item.extent, item.size) for item in part3c}
    if layouts != {(1412, base.LZ.stat().st_size)}:
        raise ValueError(f"unexpected ISO PART3C layout: {sorted(layouts)}")
    next_extents = sorted(
        {
            item.extent
            for item in refs
            if not item.is_dir and item.extent > 1412 and item.size > 0
        }
    )
    if not next_extents or next_extents[0] != 1564:
        raise ValueError("PART4A no longer begins at the guarded LBA 1564")

    base.main()
    report = json.loads(base.REPORT.read_text(encoding="utf-8"))
    report["archive_layout"] = {
        "all_52_member_offsets_match_original": True,
        "lz_byte_length_matches_original": True,
        "part3c_lz_lba": 1412,
        "next_file_lba": 1564,
        "physical_capacity": (1564 - 1412) * 2048,
        "physical_slack": (1564 - 1412) * 2048 - base.LZ.stat().st_size,
        "critical_offsets": {
            entry.name: f"0x{entry.offset:X}"
            for entry in delivered
            if entry.name
            in {"PART3C.SCN", "PART3C.MES", "120.BG", "121.BG", "122.BG"}
        },
    }
    base.REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

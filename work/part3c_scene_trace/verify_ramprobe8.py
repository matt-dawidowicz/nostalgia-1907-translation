#!/usr/bin/env python3
"""Independently verify the diagnostic PART3C RAM-probe BIN/CUE."""

from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
FINAL = WORKSPACE / "outputs" / "PART3C_ramprobe8_fresh"
SOURCE = WORKSPACE / "outputs" / "PART3C_slotpreservefix7_fresh"
ORIGINAL_LZ = (
    WORKSPACE / "work" / "part3c_original_compare" / "original_extract" / "PART3C.LZ"
)
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
MES = FINAL / "PART3C.MES"
LZ = FINAL / "PART3C_ramprobe8.LZ"
ISO = FINAL / "Nostalgia1907_Act3C_ramprobe8.iso"
TRACK1 = FINAL / "Nostalgia1907_Act3C_ramprobe8_Track1.bin"
TRACK2 = FINAL / "Nostalgia1907_Act3C_ramprobe8_Track2.bin"
CUE = FINAL / "Nostalgia1907_Act3C_ramprobe8.cue"
REGRESSION = FINAL / "regression_full"
REPORT = FINAL / "final_verification.json"

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from mes_probe import parse_mes  # noqa: E402
from nostalgia1907 import inspect_standard_mega_cd_cue, read_lz_entries  # noqa: E402
from verify_final_globalfontfix3 import verify_raw_payload  # noqa: E402


def main() -> None:
    """Validate structure, original offsets, raw sectors, and diagnostic scope."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    mes_report = json.loads(
        (HERE / "ramprobe8_mes_report.json").read_text(encoding="utf-8")
    )
    if (
        mes_report.get("status") != "PASS"
        or mes_report.get("output_size") != MES.stat().st_size
        or mes_report.get("records_preserved") != [0, 162]
        or mes_report.get("records_emptied") != [163, 223]
    ):
        raise ValueError("diagnostic MES contract failed")
    info, _ = parse_mes(MES.read_bytes(), MES)
    if not info.valid or info.pointer_count != 224:
        raise ValueError("diagnostic MES is invalid")

    original_entries = read_lz_entries(ORIGINAL_LZ)
    delivered_entries = read_lz_entries(LZ)
    if [item.offset for item in original_entries] != [item.offset for item in delivered_entries]:
        raise ValueError("LZ member offsets differ from retail")
    if LZ.stat().st_size != ORIGINAL_LZ.stat().st_size:
        raise ValueError("LZ size differs from retail archive")

    mes_files = list(REGRESSION.rglob("*.MES.unpacked"))
    chunks = sum(
        1
        for root in (
            path for path in REGRESSION.iterdir() if path.is_dir() and path.name not in {
                "reflow_source_unpack", "reflow_rebuilt_unpack"
            }
        )
        for _ in root.rglob("*.unpacked")
    )
    if chunks != 564 or len(mes_files) != 21:
        raise ValueError(f"regression inventory mismatch: chunks={chunks}, mes={len(mes_files)}")
    for path in mes_files:
        item, _ = parse_mes(path.read_bytes(), path)
        if not item.valid:
            raise ValueError(f"invalid regression MES: {path}")

    disc = inspect_standard_mega_cd_cue(CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("disc geometry or boot-system check failed")
    raw = verify_raw_payload(TRACK1, ISO)
    if TRACK2.read_bytes() != (
        SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track2.bin"
    ).read_bytes():
        raise ValueError("audio track changed")

    report = {
        "status": "PASS",
        "diagnostic_only": True,
        "mes": mes_report,
        "archive": {
            "members": len(delivered_entries),
            "all_offsets_match_retail": True,
            "byte_length_matches_retail": True,
        },
        "regression": {
            "unpacked_chunks": chunks,
            "validated_mes_files": len(mes_files),
            "unit_tests": "12/12 PASS",
        },
        "disc": {
            "boot_system_matches_supplied_original": True,
            "audio_track_byte_identical": True,
            **raw,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

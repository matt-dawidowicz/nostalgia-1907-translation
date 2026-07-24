#!/usr/bin/env python3
"""Build a fresh BIN/CUE for the decisive PART3C RAM-footprint probe."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
ORIGINAL_LZ = (
    WORKSPACE / "work" / "part3c_original_compare" / "original_extract" / "PART3C.LZ"
)
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
SOURCE = WORKSPACE / "outputs" / "PART3C_slotpreservefix7_fresh"
DELIVERY = WORKSPACE / "outputs" / "PART3C_ramprobe8_fresh"
SOURCE_ISO = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7.iso"
SOURCE_TRACK1 = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track1.bin"
SOURCE_TRACK2 = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track2.bin"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_SCN = DELIVERY / "PART3C.SCN"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_ramprobe8.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_ramprobe8.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_ramprobe8_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_ramprobe8_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_ramprobe8.cue"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
REPORT = DELIVERY / "build_report.json"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLS))

from build_slotpreservefix7 import facts, patch_existing_iso_extent  # noqa: E402
from nostalgia1907 import (  # noqa: E402
    inspect_standard_mega_cd_cue,
    raw_mode1_2352_from_iso,
    read_lz_entries,
    repack_lz_compressed_slots,
    unpack_lz,
    write_standard_mega_cd_cue,
)


def main() -> None:
    """Repack the diagnostic MES and produce fresh raw tracks."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse {DELIVERY}")
    mes_report = json.loads(
        (HERE / "ramprobe8_mes_report.json").read_text(encoding="utf-8")
    )
    if mes_report.get("status") != "PASS" or not mes_report.get("diagnostic_only"):
        raise ValueError("RAM-probe MES report is not valid")

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(HERE / "PART3C_ramprobe8.MES", OUTPUT_MES)
    shutil.copyfile(SOURCE / "PART3C.SCN", OUTPUT_SCN)
    shutil.copyfile(SOURCE / "FIX_CODE.FNT", OUTPUT_FONT)
    repack_lz_compressed_slots(
        ORIGINAL_LZ,
        OUTPUT_LZ,
        {"PART3C.MES": OUTPUT_MES, "PART3C.SCN": OUTPUT_SCN},
    )
    original_entries = read_lz_entries(ORIGINAL_LZ)
    output_entries = read_lz_entries(OUTPUT_LZ)
    if [item.offset for item in original_entries] != [item.offset for item in output_entries]:
        raise ValueError("RAM-probe LZ changed retail member offsets")
    if OUTPUT_LZ.stat().st_size != ORIGINAL_LZ.stat().st_size:
        raise ValueError("RAM-probe LZ changed retail archive length")

    unpack_lz(OUTPUT_LZ, UNPACKED)
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != OUTPUT_MES.read_bytes():
        raise ValueError("unpacked diagnostic MES mismatch")
    if (UNPACKED / "000_PART3C.SCN.unpacked").read_bytes() != OUTPUT_SCN.read_bytes():
        raise ValueError("unpacked diagnostic SCN mismatch")
    source_members = {
        path.name: path.read_bytes()
        for path in (SOURCE / "archive_candidate_unpacked").glob("*.unpacked")
    }
    output_members = {
        path.name: path.read_bytes() for path in UNPACKED.glob("*.unpacked")
    }
    changed_members = sorted(
        name for name in source_members if source_members[name] != output_members[name]
    )
    if set(source_members) != set(output_members) or changed_members != [
        "001_PART3C.MES.unpacked"
    ]:
        raise ValueError(f"unexpected archive changes: {changed_members}")

    iso_slot = patch_existing_iso_extent(SOURCE_ISO, OUTPUT_ISO, OUTPUT_LZ)
    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("RAM-probe disc failed boot/CUE validation")

    report = {
        "status": "PASS",
        "diagnostic_only": True,
        "purpose": "prove or disprove unpacked PART3C.MES RAM collision at 121.BG",
        "mes_report": mes_report,
        "mes": facts(OUTPUT_MES),
        "scn": facts(OUTPUT_SCN),
        "font": facts(OUTPUT_FONT),
        "lz": facts(OUTPUT_LZ),
        "all_lz_member_offsets_match_retail": True,
        "changed_archive_members_from_fix7": changed_members,
        "iso": facts(OUTPUT_ISO),
        "iso_slot": iso_slot,
        "track_1": facts(OUTPUT_TRACK1),
        "track_2": facts(OUTPUT_TRACK2),
        "cue": facts(OUTPUT_CUE),
        "disc_verify": disc,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

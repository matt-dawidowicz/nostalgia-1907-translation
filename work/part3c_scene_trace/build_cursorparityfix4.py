#!/usr/bin/env python3
"""Build a fresh PART3C cursor-parity Sega CD test image."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
ORIGINAL_ARCHIVE = (
    WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
)
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
DELIVERY = WORKSPACE / "outputs" / "PART3C_cursorparityfix4_fresh"

SOURCE_LZ = V3 / "PART3C_000_223_visualfix3.LZ"
SOURCE_ISO = V3 / "Nostalgia1907_Act3C_000_223_visualfix3.iso"
SOURCE_TRACK1 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track1.bin"
SOURCE_TRACK2 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track2.bin"
GLOBAL_FONT = V3 / "FIX_CODE.FNT"
SOURCE_MES = HERE / "PART3C_cursorparityfix4.MES"
CURSOR_REPORT = HERE / "cursor_parity_report.json"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_cursorparityfix4.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_000_223_cursorparityfix4.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_000_223_cursorparityfix4_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_000_223_cursorparityfix4_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_000_223_cursorparityfix4.cue"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
BUILD_REPORT = DELIVERY / "build_report.json"
DISC_REPORT = DELIVERY / "disc_verify.json"

TEXT_BOUNDARY_LIMIT = 0x2600
TARGET_COUNTS = {115: 16, 116: 5, 117: 12, 118: 10, 119: 20, 120: 7}

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from build_globalfontfix3 import (  # noqa: E402
    digest,
    file_facts,
    iso_payload,
    iso_payload_facts,
    member_hashes,
)
from mes_probe import parse_mes  # noqa: E402
from nostalgia1907 import (  # noqa: E402
    inspect_standard_mega_cd_cue,
    patch_iso_replacements,
    plan_iso_replacements,
    raw_mode1_2352_from_iso,
    repack_lz_compressed_reflow,
    unpack_lz,
    write_standard_mega_cd_cue,
)


def main() -> None:
    """Package the guarded MES while changing only PART3C.LZ in the ISO."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse output directory: {DELIVERY}")
    cursor_report = json.loads(CURSOR_REPORT.read_text(encoding="utf-8"))
    if cursor_report.get("status") != "PASS":
        raise ValueError("cursor-parity MES has not passed validation")
    if cursor_report["cell_contract"]["cursor_parity_translation"] != {
        str(index): cells for index, cells in TARGET_COUNTS.items()
    }:
        raise ValueError("cursor-parity report no longer matches the hard contract")

    mes = SOURCE_MES.read_bytes()
    info, _ = parse_mes(mes, SOURCE_MES)
    if not info.valid or info.pointer_count != 224:
        raise ValueError("cursor-parity MES is structurally invalid")
    if info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError("cursor-parity MES exceeds the guarded text boundary")

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(SOURCE_MES, OUTPUT_MES)
    shutil.copyfile(GLOBAL_FONT, OUTPUT_FONT)
    repack_lz_compressed_reflow(
        SOURCE_LZ,
        OUTPUT_LZ,
        {"PART3C.MES": OUTPUT_MES},
    )
    unpack_lz(OUTPUT_LZ, UNPACKED)
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != mes:
        raise ValueError("rebuilt LZ does not contain the cursor-parity MES")

    original_members = member_hashes(ORIGINAL_ARCHIVE)
    output_members = member_hashes(UNPACKED)
    if set(original_members) != set(output_members):
        raise ValueError("PART3C archive inventory changed")
    changed_archive_members = sorted(
        name
        for name in original_members
        if original_members[name] != output_members[name]
    )
    if changed_archive_members != ["001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected PART3C changes: {changed_archive_members}")
    protected_assets = [
        "000_PART3C.SCN.unpacked",
        "002_SCREEN0.BS.unpacked",
        "003_SCREEN1.BS.unpacked",
    ]
    for name in protected_assets:
        if (UNPACKED / name).read_bytes() != (ORIGINAL_ARCHIVE / name).read_bytes():
            raise ValueError(f"working scene asset changed: {name}")

    plans = plan_iso_replacements(SOURCE_ISO, {"/PART3C.LZ": OUTPUT_LZ})
    if len(plans) != 1 or not plans[0].fits or plans[0].relocated:
        raise ValueError("PART3C.LZ does not fit its original ISO extent")
    patch_iso_replacements(
        SOURCE_ISO,
        OUTPUT_ISO,
        {"/PART3C.LZ": OUTPUT_LZ},
    )

    source_iso = iso_payload_facts(SOURCE_ISO)
    output_iso = iso_payload_facts(OUTPUT_ISO)
    if set(source_iso) != set(output_iso):
        raise ValueError("ISO inventory changed")
    changed_iso_files = sorted(
        name for name in source_iso if source_iso[name] != output_iso[name]
    )
    if changed_iso_files != ["PART3C.LZ"]:
        raise ValueError(f"unexpected ISO files changed: {changed_iso_files}")
    if iso_payload(OUTPUT_ISO, "PART3C.LZ") != OUTPUT_LZ.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from rebuilt LZ")
    if iso_payload(OUTPUT_ISO, "FIX_CODE.FNT") != GLOBAL_FONT.read_bytes():
        raise ValueError("global fixed font changed")

    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("cursor-parity disc failed boot/CUE validation")
    DISC_REPORT.write_text(json.dumps(disc, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "PASS",
        "root_cause_guard": {
            "shared_cursor_records": [115, 116, 117, 118, 119],
            "following_floating_record": 120,
            "required_cell_counts": TARGET_COUNTS,
            "exact_working_japanese_cell_parity": True,
        },
        "boundary_guard": {
            "split_offset": info.split_offset,
            "split_offset_hex": f"0x{info.split_offset:X}",
            "limit": TEXT_BOUNDARY_LIMIT,
            "limit_hex": f"0x{TEXT_BOUNDARY_LIMIT:X}",
            "headroom": TEXT_BOUNDARY_LIMIT - info.split_offset,
        },
        "mes": file_facts(OUTPUT_MES),
        "font": file_facts(OUTPUT_FONT),
        "global_font_byte_identical_to_visualfix3": True,
        "lz": file_facts(OUTPUT_LZ),
        "changed_archive_members": changed_archive_members,
        "protected_scene_assets_byte_identical_to_original": protected_assets,
        "iso": file_facts(OUTPUT_ISO),
        "changed_iso_files": changed_iso_files,
        "iso_replacement": {
            "old_size": plans[0].old_size,
            "new_size": plans[0].new_size,
            "allocated_size": plans[0].output_allocated_size,
            "slack": plans[0].output_slack,
            "relocated": plans[0].relocated,
        },
        "track_1": file_facts(OUTPUT_TRACK1),
        "track_2": file_facts(OUTPUT_TRACK2),
        "track_2_byte_identical": OUTPUT_TRACK2.read_bytes()
        == SOURCE_TRACK2.read_bytes(),
        "cue": file_facts(OUTPUT_CUE),
        "disc_verify": disc,
    }
    BUILD_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build a fresh Sega CD BIN/CUE for the retail-geometry transition probe."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
ORIGINAL_COMPARE = WORKSPACE / "work" / "part3c_original_compare"
ORIGINAL_LZ = ORIGINAL_COMPARE / "original_extract" / "PART3C.LZ"
ORIGINAL_ARCHIVE = ORIGINAL_COMPARE / "original_part3c"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
SOURCE = WORKSPACE / "outputs" / "PART3C_slotpreservefix7_fresh"
DELIVERY = WORKSPACE / "outputs" / "PART3C_transitionfix9_fresh"
SOURCE_ISO = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7.iso"
SOURCE_TRACK1 = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track1.bin"
SOURCE_TRACK2 = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track2.bin"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_SCN = DELIVERY / "PART3C.SCN"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_transitionfix9.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_transitionfix9.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_transitionfix9_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_transitionfix9_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_transitionfix9.cue"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
REGRESSION = DELIVERY / "regression_full"
REPORT = DELIVERY / "build_report.json"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from build_slotpreservefix7 import facts, patch_existing_iso_extent  # noqa: E402
from build_globalfontfix3 import iso_payload, member_hashes  # noqa: E402
from nostalgia1907 import (  # noqa: E402
    inspect_standard_mega_cd_cue,
    raw_mode1_2352_from_iso,
    read_lz_entries,
    repack_lz_compressed_slots,
    unpack_lz,
    write_standard_mega_cd_cue,
)


def main() -> None:
    """Repack the transition probe into original LZ slots and fresh tracks."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse {DELIVERY}")
    mes_report = json.loads(
        (HERE / "transitionfix9_mes_report.json").read_text(encoding="utf-8")
    )
    if mes_report.get("status") != "PASS" or not mes_report.get("diagnostic_only"):
        raise ValueError("transition MES report is not clean")

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(HERE / "PART3C_transitionfix9.MES", OUTPUT_MES)
    shutil.copyfile(HERE / "PART3C_transitionfix9.SCN", OUTPUT_SCN)
    shutil.copyfile(SOURCE / "FIX_CODE.FNT", OUTPUT_FONT)
    shutil.copytree(
        WORKSPACE / "outputs" / "PART3C_ramprobe8_fresh" / "regression_full",
        REGRESSION,
    )
    repack_lz_compressed_slots(
        ORIGINAL_LZ,
        OUTPUT_LZ,
        {"PART3C.MES": OUTPUT_MES, "PART3C.SCN": OUTPUT_SCN},
    )
    original_entries = read_lz_entries(ORIGINAL_LZ)
    output_entries = read_lz_entries(OUTPUT_LZ)
    if [item.offset for item in original_entries] != [item.offset for item in output_entries]:
        raise ValueError("transition LZ changed retail member offsets")
    if OUTPUT_LZ.stat().st_size != ORIGINAL_LZ.stat().st_size:
        raise ValueError("transition LZ changed retail archive length")

    unpack_lz(OUTPUT_LZ, UNPACKED)
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != OUTPUT_MES.read_bytes():
        raise ValueError("unpacked transition MES mismatch")
    if (UNPACKED / "000_PART3C.SCN.unpacked").read_bytes() != OUTPUT_SCN.read_bytes():
        raise ValueError("unpacked transition SCN mismatch")
    original_members = member_hashes(ORIGINAL_ARCHIVE)
    output_members = member_hashes(UNPACKED)
    changed_from_retail = sorted(
        name for name in original_members if original_members[name] != output_members[name]
    )
    if set(original_members) != set(output_members) or changed_from_retail != [
        "001_PART3C.MES.unpacked"
    ]:
        raise ValueError(f"unexpected changes from retail archive: {changed_from_retail}")
    for name in ("016_120.BG.unpacked", "017_121.BG.unpacked", "018_122.BG.unpacked"):
        if (UNPACKED / name).read_bytes() != (ORIGINAL_ARCHIVE / name).read_bytes():
            raise ValueError(f"protected background changed: {name}")

    iso_slot = patch_existing_iso_extent(SOURCE_ISO, OUTPUT_ISO, OUTPUT_LZ)
    if iso_payload(OUTPUT_ISO, "PART3C.LZ") != OUTPUT_LZ.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from the rebuilt archive")
    if iso_payload(OUTPUT_ISO, "FIX_CODE.FNT") != OUTPUT_FONT.read_bytes():
        raise ValueError("ISO-embedded fixed font changed")
    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("transition disc failed boot/CUE validation")

    critical_offsets = {
        entry.name: f"0x{entry.offset:X}"
        for entry in output_entries
        if entry.name in {"PART3C.SCN", "PART3C.MES", "120.BG", "121.BG", "122.BG"}
    }
    report = {
        "status": "PASS",
        "diagnostic_only": True,
        "purpose": "test retail scene geometry and title padding at the 120.BG to 121.BG transition",
        "mes_report": mes_report,
        "mes": facts(OUTPUT_MES),
        "scn": facts(OUTPUT_SCN),
        "font": facts(OUTPUT_FONT),
        "lz": facts(OUTPUT_LZ),
        "all_lz_member_offsets_match_retail": True,
        "lz_byte_length_matches_retail": True,
        "critical_offsets": critical_offsets,
        "changed_archive_members_from_retail": changed_from_retail,
        "backgrounds_120_121_122_byte_identical_to_retail": True,
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

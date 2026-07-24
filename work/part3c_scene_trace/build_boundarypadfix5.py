#!/usr/bin/env python3
"""Build a fresh Sega CD image with the bounded, padded PART3C MES."""

from __future__ import annotations

import hashlib
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
DELIVERY = WORKSPACE / "outputs" / "PART3C_boundarypadfix5_fresh"

SOURCE_LZ = V3 / "PART3C_000_223_visualfix3.LZ"
SOURCE_ISO = V3 / "Nostalgia1907_Act3C_000_223_visualfix3.iso"
SOURCE_TRACK1 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track1.bin"
SOURCE_TRACK2 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track2.bin"
SOURCE_FONT = V3 / "FIX_CODE.FNT"
SOURCE_MES = HERE / "PART3C_boundarypadfix5.MES"
PATCHED_FONT = HERE / "FIX_CODE_boundarypadfix5.FNT"
COMPACTION_REPORT = HERE / "boundarypad_compaction_report.json"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_boundarypadfix5.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_000_223_boundarypadfix5.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_000_223_boundarypadfix5_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_000_223_boundarypadfix5_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_000_223_boundarypadfix5.cue"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
BUILD_REPORT = DELIVERY / "build_report.json"
DISC_REPORT = DELIVERY / "disc_verify.json"

WHOLE_MES_LIMIT = 0x3FFF
MINIMUM_V3_SAVING = 0x1E6
RECYCLED_SPILL_CODES = (0x48, 0xBC)
GLYPH_BYTES = 18

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from build_globalfontfix3 import (  # noqa: E402
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


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def file_facts(path: Path) -> dict[str, object]:
    """Return reproducible size and hash facts for a file."""
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": digest(data)}


def main() -> None:
    """Repack PART3C and create fresh raw tracks and a standard CUE."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse output directory: {DELIVERY}")
    compact = json.loads(COMPACTION_REPORT.read_text(encoding="utf-8"))
    if compact.get("status") != "PASS":
        raise ValueError("bounded padded MES has not passed compaction guards")

    mes = SOURCE_MES.read_bytes()
    info, _ = parse_mes(mes, SOURCE_MES)
    if not info.valid or info.pointer_count != 224:
        raise ValueError("bounded PART3C MES is structurally invalid")
    if len(mes) > WHOLE_MES_LIMIT:
        raise ValueError("bounded PART3C MES exceeds 0x3FFF")
    if V3.joinpath("PART3C.MES").stat().st_size - len(mes) < MINIMUM_V3_SAVING:
        raise ValueError("bounded PART3C MES misses the requested saving")

    source_font = SOURCE_FONT.read_bytes()
    output_font = PATCHED_FONT.read_bytes()
    changed_font_bytes = [
        index for index, (before, after) in enumerate(zip(source_font, output_font))
        if before != after
    ]
    permitted_font_bytes = {
        index
        for code in RECYCLED_SPILL_CODES
        for index in range((code - 1) * GLYPH_BYTES, code * GLYPH_BYTES)
    }
    if not changed_font_bytes or not set(changed_font_bytes) <= permitted_font_bytes:
        raise ValueError("font differs outside the two audited translation spill slots")

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(SOURCE_MES, OUTPUT_MES)
    shutil.copyfile(PATCHED_FONT, OUTPUT_FONT)
    repack_lz_compressed_reflow(SOURCE_LZ, OUTPUT_LZ, {"PART3C.MES": OUTPUT_MES})
    unpack_lz(OUTPUT_LZ, UNPACKED)
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != mes:
        raise ValueError("rebuilt PART3C.LZ does not contain the bounded MES")

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
        raise ValueError(f"unexpected PART3C members changed: {changed_archive_members}")
    protected_assets = [
        "000_PART3C.SCN.unpacked",
        "002_SCREEN0.BS.unpacked",
        "003_SCREEN1.BS.unpacked",
    ]
    for name in protected_assets:
        if (UNPACKED / name).read_bytes() != (ORIGINAL_ARCHIVE / name).read_bytes():
            raise ValueError(f"scene asset differs from the supplied original: {name}")

    replacements = {"/PART3C.LZ": OUTPUT_LZ, "/FIX_CODE.FNT": OUTPUT_FONT}
    plans = plan_iso_replacements(SOURCE_ISO, replacements)
    if len(plans) != 2 or any(not plan.fits or plan.relocated for plan in plans):
        raise ValueError("LZ/font replacements do not fit their existing ISO extents")
    patch_iso_replacements(SOURCE_ISO, OUTPUT_ISO, replacements)

    source_iso = iso_payload_facts(SOURCE_ISO)
    output_iso = iso_payload_facts(OUTPUT_ISO)
    if set(source_iso) != set(output_iso):
        raise ValueError("ISO file inventory changed")
    changed_iso_files = sorted(
        name for name in source_iso if source_iso[name] != output_iso[name]
    )
    if changed_iso_files != ["FIX_CODE.FNT", "PART3C.LZ"]:
        raise ValueError(f"unexpected ISO files changed: {changed_iso_files}")
    if iso_payload(OUTPUT_ISO, "PART3C.LZ") != OUTPUT_LZ.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from the rebuilt archive")
    if iso_payload(OUTPUT_ISO, "FIX_CODE.FNT") != output_font:
        raise ValueError("ISO-embedded FIX_CODE.FNT differs from the guarded font")

    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("fresh disc failed boot/CUE verification")
    DISC_REPORT.write_text(json.dumps(disc, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "PASS",
        "mes_guard": {
            "size": len(mes),
            "size_hex": f"0x{len(mes):X}",
            "whole_limit": WHOLE_MES_LIMIT,
            "whole_limit_hex": f"0x{WHOLE_MES_LIMIT:X}",
            "headroom": WHOLE_MES_LIMIT - len(mes),
            "saving_from_visualfix3": V3.joinpath("PART3C.MES").stat().st_size
            - len(mes),
            "split": info.split_offset,
            "split_hex": f"0x{info.split_offset:X}",
        },
        "mes": file_facts(OUTPUT_MES),
        "font": file_facts(OUTPUT_FONT),
        "font_changed_byte_count": len(changed_font_bytes),
        "font_change_limited_to_spill_codes": [
            f"0x{code:02X}" for code in RECYCLED_SPILL_CODES
        ],
        "lz": file_facts(OUTPUT_LZ),
        "changed_archive_members": changed_archive_members,
        "protected_scene_assets_byte_identical_to_original": protected_assets,
        "iso": file_facts(OUTPUT_ISO),
        "changed_iso_files": changed_iso_files,
        "iso_replacements": [
            {
                "path": plan.iso_path,
                "old_size": plan.old_size,
                "new_size": plan.new_size,
                "allocated_size": plan.output_allocated_size,
                "slack": plan.output_slack,
                "relocated": plan.relocated,
            }
            for plan in plans
        ],
        "track_1": file_facts(OUTPUT_TRACK1),
        "track_2": file_facts(OUTPUT_TRACK2),
        "track_2_byte_identical_to_visualfix3": OUTPUT_TRACK2.read_bytes()
        == SOURCE_TRACK2.read_bytes(),
        "cue": file_facts(OUTPUT_CUE),
        "disc_verify": disc,
    }
    BUILD_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

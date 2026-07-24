#!/usr/bin/env python3
"""Build a fresh BIN/CUE with the record-162 row-parity repair."""

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
ORIGINAL_ARCHIVE = WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
SOURCE = WORKSPACE / "outputs" / "PART3C_boundarypadfix5_fresh"
DELIVERY = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh"

SOURCE_LZ = SOURCE / "PART3C_boundarypadfix5.LZ"
SOURCE_ISO = SOURCE / "Nostalgia1907_Act3C_000_223_boundarypadfix5.iso"
SOURCE_TRACK1 = SOURCE / "Nostalgia1907_Act3C_000_223_boundarypadfix5_Track1.bin"
SOURCE_TRACK2 = SOURCE / "Nostalgia1907_Act3C_000_223_boundarypadfix5_Track2.bin"
SOURCE_FONT = SOURCE / "FIX_CODE.FNT"
PATCHED_MES = HERE / "PART3C_rowparityfix6.MES"
PATCHED_SCN = HERE / "PART3C_rowparityfix6.SCN"
MES_REPORT = HERE / "rowparityfix6_mes_report.json"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_SCN = DELIVERY / "PART3C.SCN"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_rowparityfix6.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_000_223_rowparityfix6.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_000_223_rowparityfix6_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_000_223_rowparityfix6_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_000_223_rowparityfix6.cue"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
BUILD_REPORT = DELIVERY / "build_report.json"
DISC_REPORT = DELIVERY / "disc_verify.json"

WHOLE_MES_LIMIT = 0x3FFF
SCN_WIDTH_OFFSET = 0x0B26
GLYPH_BYTES = 18

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from build_globalfontfix3 import iso_payload, iso_payload_facts, member_hashes  # noqa: E402
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


def facts(path: Path) -> dict[str, object]:
    """Return reproducible size and hash facts."""
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": digest(data)}


def main() -> None:
    """Repack the two changed PART3C members and build fresh raw tracks."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse output directory: {DELIVERY}")
    mes_report = json.loads(MES_REPORT.read_text(encoding="utf-8"))
    if mes_report.get("status") != "PASS":
        raise ValueError("row-parity MES/SCN guards have not passed")

    mes = PATCHED_MES.read_bytes()
    info, _ = parse_mes(mes, PATCHED_MES)
    if not info.valid or info.pointer_count != 224 or len(mes) > WHOLE_MES_LIMIT:
        raise ValueError("row-parity MES failed the hard structural/size guard")
    source_scn = (ORIGINAL_ARCHIVE / "000_PART3C.SCN.unpacked").read_bytes()
    target_scn = PATCHED_SCN.read_bytes()
    changed_scn_offsets = [
        index
        for index, (before, after) in enumerate(zip(source_scn, target_scn))
        if before != after
    ]
    if len(source_scn) != len(target_scn) or changed_scn_offsets != [SCN_WIDTH_OFFSET]:
        raise ValueError("SCN differs outside the single guarded width operand")
    if source_scn[SCN_WIDTH_OFFSET] != 0x0E or target_scn[SCN_WIDTH_OFFSET] != 0x12:
        raise ValueError("SCN width operand does not contain 0x0E -> 0x12")

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(PATCHED_MES, OUTPUT_MES)
    shutil.copyfile(PATCHED_SCN, OUTPUT_SCN)
    shutil.copyfile(SOURCE_FONT, OUTPUT_FONT)
    repack_lz_compressed_reflow(
        SOURCE_LZ,
        OUTPUT_LZ,
        {"PART3C.MES": OUTPUT_MES, "PART3C.SCN": OUTPUT_SCN},
    )
    unpack_lz(OUTPUT_LZ, UNPACKED)
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != mes:
        raise ValueError("rebuilt archive does not contain the guarded MES")
    if (UNPACKED / "000_PART3C.SCN.unpacked").read_bytes() != target_scn:
        raise ValueError("rebuilt archive does not contain the guarded SCN")

    source_members = member_hashes(SOURCE / "archive_candidate_unpacked")
    output_members = member_hashes(UNPACKED)
    if set(source_members) != set(output_members):
        raise ValueError("PART3C archive inventory changed")
    changed_from_source = sorted(
        name for name in source_members if source_members[name] != output_members[name]
    )
    if changed_from_source != ["000_PART3C.SCN.unpacked", "001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected archive changes: {changed_from_source}")
    original_members = member_hashes(ORIGINAL_ARCHIVE)
    changed_from_original = sorted(
        name for name in original_members if original_members[name] != output_members[name]
    )
    if changed_from_original != ["000_PART3C.SCN.unpacked", "001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected changes from original archive: {changed_from_original}")
    for name in ("002_SCREEN0.BS.unpacked", "003_SCREEN1.BS.unpacked"):
        if (UNPACKED / name).read_bytes() != (ORIGINAL_ARCHIVE / name).read_bytes():
            raise ValueError(f"protected graphics asset changed: {name}")

    replacements = {"/PART3C.LZ": OUTPUT_LZ}
    plans = plan_iso_replacements(SOURCE_ISO, replacements)
    if len(plans) != 1 or any(not plan.fits or plan.relocated for plan in plans):
        raise ValueError("PART3C.LZ does not fit its existing ISO extent")
    patch_iso_replacements(SOURCE_ISO, OUTPUT_ISO, replacements)
    source_iso = iso_payload_facts(SOURCE_ISO)
    output_iso = iso_payload_facts(OUTPUT_ISO)
    if set(source_iso) != set(output_iso):
        raise ValueError("ISO file inventory changed")
    changed_iso = sorted(
        name for name in source_iso if source_iso[name] != output_iso[name]
    )
    if changed_iso != ["PART3C.LZ"]:
        raise ValueError(f"unexpected ISO changes: {changed_iso}")
    if iso_payload(OUTPUT_ISO, "PART3C.LZ") != OUTPUT_LZ.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from the rebuilt archive")
    if iso_payload(OUTPUT_ISO, "FIX_CODE.FNT") != SOURCE_FONT.read_bytes():
        raise ValueError("ISO font changed during row-parity rebuild")

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
        "mes": facts(OUTPUT_MES),
        "mes_limit": WHOLE_MES_LIMIT,
        "mes_headroom": WHOLE_MES_LIMIT - len(mes),
        "scn": facts(OUTPUT_SCN),
        "scn_only_changed_offset": f"0x{SCN_WIDTH_OFFSET:04X}",
        "scn_width_change": "0x0E -> 0x12",
        "font": facts(OUTPUT_FONT),
        "font_byte_identical_to_boundarypadfix5": True,
        "lz": facts(OUTPUT_LZ),
        "changed_archive_members_from_boundarypadfix5": changed_from_source,
        "changed_archive_members_from_original": changed_from_original,
        "screen_assets_byte_identical_to_original": [
            "002_SCREEN0.BS.unpacked",
            "003_SCREEN1.BS.unpacked",
        ],
        "iso": facts(OUTPUT_ISO),
        "changed_iso_files_from_boundarypadfix5": changed_iso,
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
        "track_1": facts(OUTPUT_TRACK1),
        "track_2": facts(OUTPUT_TRACK2),
        "track_2_byte_identical_to_boundarypadfix5": (
            OUTPUT_TRACK2.read_bytes() == SOURCE_TRACK2.read_bytes()
        ),
        "cue": facts(OUTPUT_CUE),
        "disc_verify": disc,
    }
    BUILD_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

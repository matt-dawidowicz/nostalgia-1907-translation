#!/usr/bin/env python3
"""Build a PART3C-only disc while preserving the proven game-wide font."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
DELIVERY = WORKSPACE / "outputs" / "PART3C_globalfontfix3_fresh"
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)

SOURCE_LZ = V3 / "PART3C_000_223_visualfix3.LZ"
SOURCE_ISO = V3 / "Nostalgia1907_Act3C_000_223_visualfix3.iso"
SOURCE_TRACK1 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track1.bin"
SOURCE_TRACK2 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track2.bin"
GLOBAL_FONT = V3 / "FIX_CODE.FNT"
OUTPUT_MES_SOURCE = HERE / "PART3C_globalfontfix3.MES"
REMAP_REPORT = HERE / "font_remap_report.json"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_globalfontfix3.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_000_223_globalfontfix3.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_000_223_globalfontfix3_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_000_223_globalfontfix3_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_000_223_globalfontfix3.cue"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
DISC_REPORT = DELIVERY / "disc_verify.json"
BUILD_REPORT = DELIVERY / "build_report.json"

TEXT_BOUNDARY_LIMIT = 0x2600
POINTER_COUNT = 224

sys.path.insert(0, str(TOOLS))

from mes_probe import parse_mes  # noqa: E402
from nostalgia1907 import (  # noqa: E402
    inspect_standard_mega_cd_cue,
    patch_iso_replacements,
    plan_iso_replacements,
    raw_mode1_2352_from_iso,
    read_iso_entries,
    repack_lz_compressed_reflow,
    unpack_lz,
    write_standard_mega_cd_cue,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def file_facts(path: Path) -> dict[str, object]:
    """Return stable size and digest facts for a file."""
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": digest(data)}


def member_hashes(root: Path) -> dict[str, str]:
    """Hash actual unpacked archive members."""
    return {item.name: digest(item.read_bytes()) for item in root.glob("*.unpacked")}


def iso_payload_facts(path: Path) -> dict[str, tuple[int, str]]:
    """Hash all ISO file payloads."""
    result: dict[str, tuple[int, str]] = {}
    with path.open("rb") as stream:
        for entry in read_iso_entries(path):
            if entry.is_dir:
                continue
            stream.seek(entry.extent * 2048)
            payload = stream.read(entry.size)
            result[entry.path] = (entry.size, digest(payload))
    return result


def iso_payload(path: Path, member: str) -> bytes:
    """Read one ISO file payload."""
    for entry in read_iso_entries(path):
        if not entry.is_dir and entry.path == member:
            with path.open("rb") as stream:
                stream.seek(entry.extent * 2048)
                return stream.read(entry.size)
    raise ValueError(f"ISO member not found: {member}")


def main() -> None:
    """Repack the remapped MES and build a font-preserving BIN/CUE."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse output directory: {DELIVERY}")
    remap = json.loads(REMAP_REPORT.read_text(encoding="utf-8"))
    if remap.get("status") != "PASS":
        raise ValueError("fixed-code remap has not passed validation")
    if remap["font_contract"]["bitmap_mismatches"] != 0:
        raise ValueError("fixed-code remap has bitmap mismatches")

    mes = OUTPUT_MES_SOURCE.read_bytes()
    info, _ = parse_mes(mes, OUTPUT_MES_SOURCE)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError("remapped MES is structurally invalid")
    if info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError(
            f"text split 0x{info.split_offset:X} exceeds 0x{TEXT_BOUNDARY_LIMIT:X}"
        )

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(OUTPUT_MES_SOURCE, OUTPUT_MES)
    shutil.copyfile(GLOBAL_FONT, OUTPUT_FONT)
    repack_lz_compressed_reflow(
        SOURCE_LZ,
        OUTPUT_LZ,
        {"PART3C.MES": OUTPUT_MES},
    )
    unpack_lz(OUTPUT_LZ, UNPACKED)
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != mes:
        raise ValueError("rebuilt LZ does not contain the remapped MES")
    source_members = member_hashes(V3 / "archive_candidate_unpacked")
    output_members = member_hashes(UNPACKED)
    if set(source_members) != set(output_members):
        raise ValueError("PART3C archive inventory changed")
    changed_lz_members = sorted(
        name for name in source_members if source_members[name] != output_members[name]
    )
    if changed_lz_members != ["001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected LZ changes: {changed_lz_members}")

    plans = plan_iso_replacements(SOURCE_ISO, {"/PART3C.LZ": OUTPUT_LZ})
    if len(plans) != 1 or not plans[0].fits or plans[0].relocated:
        raise ValueError("PART3C.LZ does not fit its existing ISO extent")
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
        raise ValueError(f"unexpected ISO changes: {changed_iso_files}")
    if iso_payload(OUTPUT_ISO, "PART3C.LZ") != OUTPUT_LZ.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from rebuilt LZ")
    iso_font = iso_payload(OUTPUT_ISO, "FIX_CODE.FNT")
    if iso_font != GLOBAL_FONT.read_bytes():
        raise ValueError("game-wide fixed font changed")

    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("font-preserving disc failed boot/CUE validation")
    DISC_REPORT.write_text(json.dumps(disc, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "PASS",
        "boot_regression_fix": {
            "main_binary_references_global_font": True,
            "global_font_changed_from_visualfix3": False,
            "global_font_sha256": digest(GLOBAL_FONT.read_bytes()),
            "iso_files_changed_from_visualfix3": changed_iso_files,
        },
        "boundary_guard": {
            "kind": "MES text/glyph split",
            "split_offset": info.split_offset,
            "split_offset_hex": f"0x{info.split_offset:X}",
            "limit": TEXT_BOUNDARY_LIMIT,
            "limit_hex": f"0x{TEXT_BOUNDARY_LIMIT:X}",
            "headroom": TEXT_BOUNDARY_LIMIT - info.split_offset,
        },
        "mes": file_facts(OUTPUT_MES),
        "font": file_facts(OUTPUT_FONT),
        "font_byte_identical_to_visualfix3": True,
        "lz": file_facts(OUTPUT_LZ),
        "changed_lz_members": changed_lz_members,
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

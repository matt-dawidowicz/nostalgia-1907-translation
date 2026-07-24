#!/usr/bin/env python3
"""Build a fresh PART3C disc from the padding-corrected runtime contract."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
DELIVERY = WORKSPACE / "outputs" / "PART3C_runtimepadfix2_fresh"
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
V4 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"

SOURCE_LZ = V3 / "PART3C_000_223_visualfix3.LZ"
SOURCE_ISO = V3 / "Nostalgia1907_Act3C_000_223_visualfix3.iso"
SOURCE_TRACK1 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track1.bin"
SOURCE_TRACK2 = V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track2.bin"
REFERENCE_ISO = V4 / "Nostalgia1907_Act3C_000_223_visualfix4.iso"
REFERENCE_LZ = V4 / "PART3C_000_223_visualfix4.LZ"
SOURCE_MES = V4 / "PART3C.MES"
SOURCE_FONT = V4 / "FIX_CODE.FNT"
CONFIG = V4 / "PART3C_000_223_visualfix4_build_config.json"
BASELINE_REPORT = HERE / "baseline_validation.json"
FONT_REPORT = HERE / "visualfix4_font_verification.json"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_runtimepadfix2.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2.cue"
UNPACK_DIR = DELIVERY / "archive_candidate_unpacked"
DISC_REPORT = DELIVERY / "disc_verify.json"
BUILD_REPORT = DELIVERY / "build_report.json"

TEXT_BOUNDARY_LIMIT = 0x2600
POINTER_COUNT = 224
FORCED_PADDING = {116, 117, 118, 119, 120}

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
    """Return stable facts for one output file."""
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": digest(data)}


def iso_payload_facts(path: Path) -> dict[str, tuple[int, str]]:
    """Hash every ISO file payload without retaining all payloads."""
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
    """Read one named file payload from an ISO."""
    for entry in read_iso_entries(path):
        if not entry.is_dir and entry.path == member:
            with path.open("rb") as stream:
                stream.seek(entry.extent * 2048)
                return stream.read(entry.size)
    raise ValueError(f"ISO member not found: {member}")


def main() -> None:
    """Apply the guarded PART3C/font replacement and build fresh tracks."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse output directory: {DELIVERY}")
    baseline = json.loads(BASELINE_REPORT.read_text(encoding="utf-8"))
    if baseline.get("status") != "PASS":
        raise ValueError("padding-corrected baseline has not passed validation")
    font_report = json.loads(FONT_REPORT.read_text(encoding="utf-8"))
    if (
        font_report.get("status") != "PASS"
        or font_report.get("matching_font") != "visualfix4_standalone"
    ):
        raise ValueError("visualfix4 MES/font mapping has not passed validation")

    mes = SOURCE_MES.read_bytes()
    info, _ = parse_mes(mes, SOURCE_MES)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError("padding-corrected MES is structurally invalid")
    if info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError(
            f"text split 0x{info.split_offset:X} exceeds 0x{TEXT_BOUNDARY_LIMIT:X}"
        )
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    entries = {int(item["segment"]): item for item in config["segments"]}
    fixed_windows = set(config["scn_fixed_window_padding"]["segments"])
    forced = set(config["profile_forced_final_row_padding"]["segments"])
    if forced != FORCED_PADDING:
        raise ValueError(f"forced-padding set changed: {sorted(forced)}")
    unpadded = [
        index
        for index in sorted(fixed_windows | forced)
        if not entries[index]["pad_final_row"]
    ]
    if unpadded:
        raise ValueError(f"protected records are not padded: {unpadded}")

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(SOURCE_MES, OUTPUT_MES)
    shutil.copyfile(SOURCE_FONT, OUTPUT_FONT)
    repack_lz_compressed_reflow(
        SOURCE_LZ,
        OUTPUT_LZ,
        {"PART3C.MES": OUTPUT_MES},
    )
    if OUTPUT_LZ.read_bytes() != REFERENCE_LZ.read_bytes():
        raise ValueError("fresh PART3C LZ does not reproduce padding-corrected LZ")

    unpack_lz(OUTPUT_LZ, UNPACK_DIR)
    unpacked_mes = UNPACK_DIR / "001_PART3C.MES.unpacked"
    if unpacked_mes.read_bytes() != mes:
        raise ValueError("rebuilt LZ does not contain the guarded MES")
    source_members = {
        item.name: digest(item.read_bytes())
        for item in (V3 / "archive_candidate_unpacked").glob("*.unpacked")
    }
    output_members = {
        item.name: digest(item.read_bytes()) for item in UNPACK_DIR.glob("*.unpacked")
    }
    if set(source_members) != set(output_members):
        raise ValueError("PART3C LZ inventory changed")
    changed_lz_members = sorted(
        name for name in source_members if source_members[name] != output_members[name]
    )
    if changed_lz_members != ["001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected LZ changes: {changed_lz_members}")

    replacements = {
        "/PART3C.LZ": OUTPUT_LZ,
        "/FIX_CODE.FNT": OUTPUT_FONT,
    }
    plans = plan_iso_replacements(SOURCE_ISO, replacements)
    if len(plans) != 2 or any(not plan.fits or plan.relocated for plan in plans):
        raise ValueError("LZ/font replacements do not fit their existing ISO extents")
    patch_iso_replacements(SOURCE_ISO, OUTPUT_ISO, replacements)

    source_iso = iso_payload_facts(SOURCE_ISO)
    output_iso = iso_payload_facts(OUTPUT_ISO)
    reference_iso = iso_payload_facts(REFERENCE_ISO)
    if set(source_iso) != set(output_iso) or set(output_iso) != set(reference_iso):
        raise ValueError("ISO file inventory changed")
    changed_iso_files = sorted(
        name for name in source_iso if source_iso[name] != output_iso[name]
    )
    if changed_iso_files != ["FIX_CODE.FNT", "PART3C.LZ"]:
        raise ValueError(f"unexpected ISO changes: {changed_iso_files}")
    reference_mismatches = sorted(
        name for name in output_iso if output_iso[name] != reference_iso[name]
    )
    if reference_mismatches != ["FIX_CODE.FNT"]:
        raise ValueError(
            "fresh ISO must correct only the stale font in visualfix4: "
            f"{reference_mismatches}"
        )
    if iso_payload(OUTPUT_ISO, "PART3C.LZ") != OUTPUT_LZ.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from rebuilt archive")
    if iso_payload(OUTPUT_ISO, "FIX_CODE.FNT") != OUTPUT_FONT.read_bytes():
        raise ValueError("ISO-embedded FIX_CODE.FNT differs from guarded font")

    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, SOURCE_TRACK1)
    if not disc["template_boot_match"] or disc["track_count"] != 2:
        raise ValueError("fresh disc failed boot/CUE verification")
    DISC_REPORT.write_text(json.dumps(disc, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "PASS",
        "boundary_guard": {
            "kind": "MES text/glyph split",
            "split_offset": info.split_offset,
            "split_offset_hex": f"0x{info.split_offset:X}",
            "limit": TEXT_BOUNDARY_LIMIT,
            "limit_hex": f"0x{TEXT_BOUNDARY_LIMIT:X}",
            "headroom": TEXT_BOUNDARY_LIMIT - info.split_offset,
            "whole_mes_size_limit": None,
            "whole_mes_size": len(mes),
            "whole_mes_size_hex": f"0x{len(mes):X}",
        },
        "padding_guard": {
            "fixed_window_records": len(fixed_windows),
            "forced_records": sorted(forced),
            "protected_records": len(fixed_windows | forced),
            "all_protected_records_padded": True,
        },
        "mes": file_facts(OUTPUT_MES),
        "font": file_facts(OUTPUT_FONT),
        "lz": file_facts(OUTPUT_LZ),
        "changed_lz_members": changed_lz_members,
        "iso": file_facts(OUTPUT_ISO),
        "changed_iso_files": changed_iso_files,
        "visualfix4_iso_packaging_defect": {
            "mismatched_files": reference_mismatches,
            "reason": "visualfix4 ISO retained the visualfix3 font",
            "correct_font_matches_all_manifest_units": True,
        },
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
        "track_2_byte_identical": OUTPUT_TRACK2.read_bytes()
        == SOURCE_TRACK2.read_bytes(),
        "cue": file_facts(OUTPUT_CUE),
        "disc_verify": disc,
    }
    BUILD_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

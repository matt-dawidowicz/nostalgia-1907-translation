#!/usr/bin/env python3
"""Build a fresh PART3C test disc with original LZ member offsets."""

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
ORIGINAL_COMPARE = WORKSPACE / "work" / "part3c_original_compare"
ORIGINAL_LZ = ORIGINAL_COMPARE / "original_extract" / "PART3C.LZ"
ORIGINAL_ARCHIVE = ORIGINAL_COMPARE / "original_part3c"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
SOURCE = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh"
DELIVERY = WORKSPACE / "outputs" / "PART3C_slotpreservefix7_fresh"

SOURCE_ISO = SOURCE / "Nostalgia1907_Act3C_000_223_rowparityfix6.iso"
SOURCE_TRACK1 = SOURCE / "Nostalgia1907_Act3C_000_223_rowparityfix6_Track1.bin"
SOURCE_TRACK2 = SOURCE / "Nostalgia1907_Act3C_000_223_rowparityfix6_Track2.bin"
SOURCE_MES = SOURCE / "PART3C.MES"
SOURCE_SCN = SOURCE / "PART3C.SCN"
SOURCE_FONT = SOURCE / "FIX_CODE.FNT"

OUTPUT_MES = DELIVERY / "PART3C.MES"
OUTPUT_SCN = DELIVERY / "PART3C.SCN"
OUTPUT_FONT = DELIVERY / "FIX_CODE.FNT"
OUTPUT_LZ = DELIVERY / "PART3C_slotpreservefix7.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act3C_000_223_slotpreservefix7.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act3C_000_223_slotpreservefix7.cue"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
BUILD_REPORT = DELIVERY / "build_report.json"
DISC_REPORT = DELIVERY / "disc_verify.json"

DATA_SECTOR_SIZE = 2048
WHOLE_MES_LIMIT = 0x3FFF
SCN_WIDTH_OFFSET = 0x0B26

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from build_globalfontfix3 import iso_payload, iso_payload_facts, member_hashes  # noqa: E402
from mes_probe import parse_mes  # noqa: E402
from nostalgia1907 import (  # noqa: E402
    inspect_standard_mega_cd_cue,
    raw_mode1_2352_from_iso,
    read_iso_record_refs,
    read_lz_entries,
    repack_lz_compressed_slots,
    unpack_lz,
    write_iso_data_length,
    write_standard_mega_cd_cue,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def facts(path: Path) -> dict[str, object]:
    """Return reproducible size and hash facts."""
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": digest(data)}


def patch_existing_iso_extent(source: Path, output: Path, payload: Path) -> dict[str, int]:
    """Replace PART3C.LZ using its full physical gap without relocating it."""
    refs = read_iso_record_refs(source)
    matches = [
        ref
        for ref in refs
        if not ref.is_dir and Path(ref.path).name.upper() == "PART3C.LZ"
    ]
    if not matches:
        raise ValueError("source ISO has no PART3C.LZ directory record")
    layouts = {(item.extent, item.size) for item in matches}
    if len(layouts) != 1:
        raise ValueError(f"conflicting PART3C.LZ records: {sorted(layouts)}")
    extent, old_size = next(iter(layouts))
    next_extents = sorted(
        {
            item.extent
            for item in refs
            if not item.is_dir and item.extent > extent and item.size > 0
        }
    )
    if not next_extents:
        raise ValueError("could not prove the physical extent after PART3C.LZ")
    next_extent = next_extents[0]
    capacity = (next_extent - extent) * DATA_SECTOR_SIZE
    data = payload.read_bytes()
    if len(data) > capacity:
        raise ValueError(
            f"slot-preserved LZ is {len(data)} bytes but physical gap is {capacity}"
        )

    shutil.copyfile(source, output)
    with output.open("r+b") as iso:
        iso.seek(extent * DATA_SECTOR_SIZE)
        iso.write(data)
        iso.write(bytes(capacity - len(data)))
        for match in matches:
            write_iso_data_length(iso, match.record_offset, len(data))
    return {
        "extent": extent,
        "next_extent": next_extent,
        "old_size": old_size,
        "new_size": len(data),
        "physical_capacity": capacity,
        "slack": capacity - len(data),
    }


def main() -> None:
    """Preserve the original archive layout and build fresh raw tracks."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse output directory: {DELIVERY}")

    mes = SOURCE_MES.read_bytes()
    info, _ = parse_mes(mes, SOURCE_MES)
    if not info.valid or info.pointer_count != 224 or len(mes) > WHOLE_MES_LIMIT:
        raise ValueError("MES failed the hard 224-record/0x3FFF boundary guard")
    original_scn = (ORIGINAL_ARCHIVE / "000_PART3C.SCN.unpacked").read_bytes()
    scn = SOURCE_SCN.read_bytes()
    scn_diffs = [
        index for index, (before, after) in enumerate(zip(original_scn, scn))
        if before != after
    ]
    if len(original_scn) != len(scn) or scn_diffs != [SCN_WIDTH_OFFSET]:
        raise ValueError("SCN differs outside the guarded window-width byte")

    DELIVERY.mkdir(parents=True)
    shutil.copyfile(SOURCE_MES, OUTPUT_MES)
    shutil.copyfile(SOURCE_SCN, OUTPUT_SCN)
    shutil.copyfile(SOURCE_FONT, OUTPUT_FONT)
    repack_lz_compressed_slots(
        ORIGINAL_LZ,
        OUTPUT_LZ,
        {"PART3C.MES": OUTPUT_MES, "PART3C.SCN": OUTPUT_SCN},
    )

    original_entries = read_lz_entries(ORIGINAL_LZ)
    output_entries = read_lz_entries(OUTPUT_LZ)
    if len(original_entries) != len(output_entries):
        raise ValueError("archive entry count changed")
    offset_mismatches = [
        (before.index, before.name, before.offset, after.offset)
        for before, after in zip(original_entries, output_entries)
        if before.name != after.name or before.offset != after.offset
    ]
    if offset_mismatches:
        raise ValueError(f"archive offsets changed: {offset_mismatches}")
    if len(OUTPUT_LZ.read_bytes()) != len(ORIGINAL_LZ.read_bytes()):
        raise ValueError("slot-preserved archive length differs from original")

    unpack_lz(OUTPUT_LZ, UNPACKED)
    if (UNPACKED / "000_PART3C.SCN.unpacked").read_bytes() != scn:
        raise ValueError("rebuilt archive SCN mismatch")
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != mes:
        raise ValueError("rebuilt archive MES mismatch")
    original_members = member_hashes(ORIGINAL_ARCHIVE)
    output_members = member_hashes(UNPACKED)
    changed_members = sorted(
        name for name in original_members if original_members[name] != output_members[name]
    )
    if set(original_members) != set(output_members) or changed_members != [
        "000_PART3C.SCN.unpacked",
        "001_PART3C.MES.unpacked",
    ]:
        raise ValueError(f"unexpected archive changes: {changed_members}")

    iso_slot = patch_existing_iso_extent(SOURCE_ISO, OUTPUT_ISO, OUTPUT_LZ)
    if iso_slot["extent"] != 1412 or iso_slot["next_extent"] != 1564:
        raise ValueError(f"unexpected PART3C physical slot: {iso_slot}")
    if iso_payload(OUTPUT_ISO, "PART3C.LZ") != OUTPUT_LZ.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from rebuilt archive")
    if iso_payload(OUTPUT_ISO, "FIX_CODE.FNT") != OUTPUT_FONT.read_bytes():
        raise ValueError("translated font changed during slot-preserved rebuild")
    source_iso = iso_payload_facts(SOURCE_ISO)
    output_iso = iso_payload_facts(OUTPUT_ISO)
    changed_iso = sorted(
        name for name in source_iso if source_iso[name] != output_iso[name]
    )
    if set(source_iso) != set(output_iso) or changed_iso != ["PART3C.LZ"]:
        raise ValueError(f"unexpected ISO changes: {changed_iso}")

    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("fresh BIN/CUE failed boot-system verification")
    DISC_REPORT.write_text(json.dumps(disc, indent=2) + "\n", encoding="utf-8")

    tracked_offsets = {
        entry.name: f"0x{entry.offset:X}"
        for entry in output_entries
        if entry.name in {"PART3C.SCN", "PART3C.MES", "120.BG", "121.BG", "122.BG"}
    }
    report = {
        "status": "PASS",
        "diagnosis": "original LZ member offsets restored without changing prose",
        "mes": facts(OUTPUT_MES),
        "mes_limit": WHOLE_MES_LIMIT,
        "mes_headroom": WHOLE_MES_LIMIT - len(mes),
        "scn": facts(OUTPUT_SCN),
        "scn_changed_offsets": [f"0x{item:04X}" for item in scn_diffs],
        "font": facts(OUTPUT_FONT),
        "lz": facts(OUTPUT_LZ),
        "lz_byte_length_matches_original": True,
        "all_lz_member_offsets_match_original": True,
        "critical_offsets": tracked_offsets,
        "changed_archive_members_from_original": changed_members,
        "iso": facts(OUTPUT_ISO),
        "changed_iso_files_from_rowparityfix6": changed_iso,
        "iso_physical_slot": iso_slot,
        "track_1": facts(OUTPUT_TRACK1),
        "track_2": facts(OUTPUT_TRACK2),
        "track_2_byte_identical_to_rowparityfix6": (
            OUTPUT_TRACK2.read_bytes() == SOURCE_TRACK2.read_bytes()
        ),
        "cue": facts(OUTPUT_CUE),
        "disc_verify": disc,
    }
    BUILD_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

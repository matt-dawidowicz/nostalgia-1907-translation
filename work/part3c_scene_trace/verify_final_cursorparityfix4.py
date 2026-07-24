#!/usr/bin/env python3
"""Independently verify the PART3C shared-cursor fix delivery."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
BASE = WORKSPACE / "outputs" / "PART3C_globalfontfix3_fresh"
FINAL = WORKSPACE / "outputs" / "PART3C_cursorparityfix4_fresh"
ORIGINAL = WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)

MES_PATH = FINAL / "PART3C.MES"
FONT_PATH = FINAL / "FIX_CODE.FNT"
LZ_PATH = FINAL / "PART3C_cursorparityfix4.LZ"
ISO_PATH = FINAL / "Nostalgia1907_Act3C_000_223_cursorparityfix4.iso"
TRACK1_PATH = FINAL / "Nostalgia1907_Act3C_000_223_cursorparityfix4_Track1.bin"
TRACK2_PATH = FINAL / "Nostalgia1907_Act3C_000_223_cursorparityfix4_Track2.bin"
CUE_PATH = FINAL / "Nostalgia1907_Act3C_000_223_cursorparityfix4.cue"
ISO_EXTRACT = FINAL / "iso_extract"
UNPACKED = FINAL / "archive_candidate_unpacked"
REGRESSION = FINAL / "regression_full"
REPORT = FINAL / "final_verification.json"

POINTER_COUNT = 224
GLYPH_BYTES = 18
TEXT_BOUNDARY_LIMIT = 0x2600
TARGET_COUNTS = {115: 16, 116: 5, 117: 12, 118: 10, 119: 20, 120: 7}

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from build_cursor_parity_mes import (  # noqa: E402
    glyph_bitmap,
    glyph_tokens,
    render_unit,
    tokens,
)
from mes_probe import parse_mes, segments_for  # noqa: E402
from nostalgia1907 import inspect_standard_mega_cd_cue  # noqa: E402
from verify_final_globalfontfix3 import (  # noqa: E402
    file_facts,
    iso_payload_facts,
    member_hashes,
    verify_raw_payload,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid 224-entry MES and split its records."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def main() -> None:
    """Verify scene-stream parity, packaging, and disc geometry."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")

    data, info, records, tail = load_mes(MES_PATH)
    base_data, base_info, base_records, base_tail = load_mes(BASE / "PART3C.MES")
    _, _, original_records, _ = load_mes(ORIGINAL / "001_PART3C.MES.unpacked")
    font = FONT_PATH.read_bytes()
    if font != (V3 / "FIX_CODE.FNT").read_bytes():
        raise ValueError("global fixed font differs from visualfix3")
    if info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError("text split exceeds the 0x2600 boundary")
    if not tail.startswith(base_tail):
        raise ValueError("pre-existing dynamic glyph tail changed")
    if len(tail) != len(base_tail) + 2 * GLYPH_BYTES:
        raise ValueError("cursor fix must add exactly two dynamic glyphs")

    changed_records = [
        index for index, (before, after) in enumerate(zip(base_records, records))
        if before != after
    ]
    if changed_records != list(TARGET_COUNTS):
        raise ValueError(f"unexpected MES records changed: {changed_records}")

    original_counts = {index: len(tokens(original_records[index])) for index in TARGET_COUNTS}
    candidate_counts = {
        index: len(glyph_tokens(records[index], font, tail)) for index in TARGET_COUNTS
    }
    previous_counts = {
        index: len(glyph_tokens(base_records[index], font, base_tail))
        for index in TARGET_COUNTS
    }
    if original_counts != TARGET_COUNTS or candidate_counts != TARGET_COUNTS:
        raise ValueError(
            f"working cursor parity failed: original={original_counts}, "
            f"candidate={candidate_counts}"
        )
    cumulative_starts: dict[int, int] = {}
    cursor = 0
    for index in range(115, 120):
        cumulative_starts[index] = cursor
        cursor += candidate_counts[index]
    if cumulative_starts != {115: 0, 116: 16, 117: 21, 118: 33, 119: 43}:
        raise ValueError(f"continuation starts changed: {cumulative_starts}")
    if cursor != 63:
        raise ValueError(f"continuation stream ends at {cursor}, expected 63")

    expected_visible_units = {
        117: [
            ("packed-literal", "Tr"),
            ("packed-literal", "y "),
            ("packed-literal", "an"),
            ("packed-literal", "y "),
            ("packed-literal", "li"),
            ("packed-literal", "tt"),
            ("packed-literal", "le"),
            ("packed-literal", " t"),
            ("packed-literal", "ri"),
            ("packed-literal", "ck"),
            ("packed", "..."),
        ],
        118: [
            ("packed-literal", "I'"),
            ("packed-literal", "ll"),
            ("packed-literal", " s"),
            ("packed-literal", "na"),
            ("packed-literal", "p "),
            ("packed-literal", "yo"),
            ("packed-literal", "ur"),
            ("packed-literal", " n"),
            ("packed-literal", "ec"),
            ("packed-literal", "k!"),
        ],
        119: [
            ("packed-literal", "En"),
            ("packed-literal", "ou"),
            ("packed-literal", "gh"),
            ("packed-literal", "! "),
            ("packed-literal", "I "),
            ("packed-literal", "wi"),
            ("packed-literal", "ll"),
            ("packed-literal", " k"),
            ("packed-literal", "il"),
            ("packed-literal", "l "),
            ("packed-literal", "yo"),
            ("packed-literal", "u!"),
        ],
    }
    rendered_checks = 0
    for index, units in expected_visible_units.items():
        actual_bitmaps = [
            glyph_bitmap(token, font, tail)
            for token in glyph_tokens(records[index], font, tail)
        ]
        expected_bitmaps = [render_unit(style, unit) for style, unit in units]
        if actual_bitmaps[: len(units)] != expected_bitmaps:
            raise ValueError(f"record {index} visible text bitmap mismatch")
        if any(value != bytes(GLYPH_BYTES) for value in actual_bitmaps[len(units) :]):
            raise ValueError(f"record {index} has nonblank structural padding")
        rendered_checks += len(units)

    scn = (UNPACKED / "000_PART3C.SCN.unpacked").read_bytes()
    expected_chain = {
        0x823: bytes.fromhex("21 00 31 00 74"),
        0x82B: bytes.fromhex("21 00 75 00 00"),
        0x833: bytes.fromhex("21 00 76 00 00"),
        0x83B: bytes.fromhex("21 00 77 00 00"),
        0x843: bytes.fromhex("21 00 78 00 00"),
        0x849: bytes.fromhex("24 0F 14 0E 0C 27 00 79"),
    }
    for offset, command in expected_chain.items():
        if scn[offset : offset + len(command)] != command:
            raise ValueError(f"SCN continuation chain changed at 0x{offset:X}")

    original_members = member_hashes(ORIGINAL)
    delivered_members = member_hashes(UNPACKED)
    if set(original_members) != set(delivered_members):
        raise ValueError("PART3C archive inventory changed")
    changed_members = sorted(
        name
        for name in original_members
        if original_members[name] != delivered_members[name]
    )
    if changed_members != ["001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected PART3C members changed: {changed_members}")
    protected_assets = [
        "000_PART3C.SCN.unpacked",
        "002_SCREEN0.BS.unpacked",
        "003_SCREEN1.BS.unpacked",
    ]
    for name in protected_assets:
        if (UNPACKED / name).read_bytes() != (ORIGINAL / name).read_bytes():
            raise ValueError(f"scene asset differs from supplied original: {name}")

    if (ISO_EXTRACT / "PART3C.LZ").read_bytes() != LZ_PATH.read_bytes():
        raise ValueError("ISO-embedded PART3C.LZ differs from delivered LZ")
    if (ISO_EXTRACT / "FIX_CODE.FNT").read_bytes() != font:
        raise ValueError("ISO-embedded global fixed font differs")
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != data:
        raise ValueError("delivered LZ does not contain delivered MES")

    source_iso_files = iso_payload_facts(
        V3 / "Nostalgia1907_Act3C_000_223_visualfix3.iso"
    )
    delivered_iso_files = iso_payload_facts(ISO_PATH)
    if set(source_iso_files) != set(delivered_iso_files):
        raise ValueError("ISO file inventory changed")
    changed_iso_files = sorted(
        name
        for name in source_iso_files
        if source_iso_files[name] != delivered_iso_files[name]
    )
    if changed_iso_files != ["PART3C.LZ"]:
        raise ValueError(f"unexpected ISO files changed: {changed_iso_files}")

    regression_chunks = [
        member
        for lz_path in ISO_EXTRACT.glob("*.LZ")
        for member in (REGRESSION / lz_path.stem).rglob("*.unpacked")
    ]
    regression_mes = [
        path
        for path in REGRESSION.rglob("*.unpacked")
        if path.name.upper().endswith(".MES.UNPACKED")
    ]
    if len(regression_chunks) != 564 or len(regression_mes) != 21:
        raise ValueError("full regression counts changed")
    for mes_path in regression_mes:
        mes_info, _ = parse_mes(mes_path.read_bytes(), mes_path)
        if not mes_info.valid:
            raise ValueError(f"invalid regression MES: {mes_path}")

    disc = inspect_standard_mega_cd_cue(CUE_PATH, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("disc/CUE contract failed")
    raw_payload = verify_raw_payload(TRACK1_PATH, ISO_PATH)

    report = {
        "status": "PASS",
        "delivery": {
            "mes": file_facts(MES_PATH),
            "font": file_facts(FONT_PATH),
            "lz": file_facts(LZ_PATH),
            "iso": file_facts(ISO_PATH),
            "track_1": file_facts(TRACK1_PATH),
            "track_2": file_facts(TRACK2_PATH),
            "cue": file_facts(CUE_PATH),
        },
        "root_cause_contract": {
            "scn_normal_record": 115,
            "scn_continuation_records": [116, 117, 118, 119],
            "following_floating_record": 120,
            "working_japanese_cell_counts": original_counts,
            "previous_translation_cell_counts": previous_counts,
            "candidate_cell_counts": candidate_counts,
            "candidate_continuation_starts": cumulative_starts,
            "candidate_stream_end": cursor,
            "exact_cursor_parity": True,
        },
        "text_contract": {
            "unchanged_records": POINTER_COUNT - len(changed_records),
            "changed_records": changed_records,
            "verified_visible_units": rendered_checks,
            "record_117": "Try any little trick...",
            "record_118": "I'll snap your neck!",
            "record_119": "Enough! I will kill you!",
            "only_wording_change": "...and I will snap your neck! -> I'll snap your neck!",
        },
        "mes_contract": {
            "size": len(data),
            "split_offset": info.split_offset,
            "split_offset_hex": f"0x{info.split_offset:X}",
            "text_boundary_limit": TEXT_BOUNDARY_LIMIT,
            "text_headroom": TEXT_BOUNDARY_LIMIT - info.split_offset,
            "dynamic_glyphs": len(tail) // GLYPH_BYTES,
            "pre_existing_dynamic_tail_preserved": True,
            "added_dynamic_glyphs": 2,
        },
        "archive_contract": {
            "members": len(delivered_members),
            "changed_from_original": changed_members,
            "protected_scene_assets_byte_identical": protected_assets,
            "iso_files_changed_from_visualfix3": changed_iso_files,
            "global_font_byte_identical_to_visualfix3": True,
        },
        "full_regression": {
            "unpacked_chunks": len(regression_chunks),
            "validated_mes_files": len(regression_mes),
        },
        "disc_contract": {
            "track_count": disc["track_count"],
            "cue_line_endings": disc["cue_line_endings"],
            "boot_system_matches_supplied_original": disc["template_boot_match"],
            "track_1_sectors": disc["track_1"]["sectors"],
            "track_2_sectors": disc["track_2"]["sectors"],
            **raw_payload,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

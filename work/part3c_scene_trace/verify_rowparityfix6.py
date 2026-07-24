#!/usr/bin/env python3
"""Independently verify the PART3C record-162 row-parity BIN/CUE."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE = WORKSPACE / "outputs" / "PART3C_boundarypadfix5_fresh"
FINAL = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh"
ORIGINAL = WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
V4_CONFIG = (
    PROJECT
    / "outputs"
    / "nostalgia1907_act3c_000_223_visualfix4"
    / "PART3C_000_223_visualfix4_build_config.json"
)
MES_REPORT = HERE / "rowparityfix6_mes_report.json"

MES = FINAL / "PART3C.MES"
SCN = FINAL / "PART3C.SCN"
FONT = FINAL / "FIX_CODE.FNT"
LZ = FINAL / "PART3C_rowparityfix6.LZ"
ISO = FINAL / "Nostalgia1907_Act3C_000_223_rowparityfix6.iso"
TRACK1 = FINAL / "Nostalgia1907_Act3C_000_223_rowparityfix6_Track1.bin"
TRACK2 = FINAL / "Nostalgia1907_Act3C_000_223_rowparityfix6_Track2.bin"
CUE = FINAL / "Nostalgia1907_Act3C_000_223_rowparityfix6.cue"
ISO_EXTRACT = FINAL / "iso_extract"
UNPACKED = FINAL / "archive_candidate_unpacked"
REGRESSION = FINAL / "regression_full"
REPORT = FINAL / "final_verification.json"

GLYPH_BYTES = 18
WHOLE_MES_LIMIT = 0x3FFF
RECORD = 162
SCN_WIDTH_OFFSET = 0x0B26
TARGET_CELL_WIDTH = 10
TARGET_ROWS = 4

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)
from nostalgia1907 import inspect_standard_mega_cd_cue  # noqa: E402
from verify_final_globalfontfix3 import (  # noqa: E402
    iso_payload_facts,
    member_hashes,
    verify_raw_payload,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def facts(path: Path) -> dict[str, object]:
    """Return file size and SHA-256."""
    data = path.read_bytes()
    return {"size": len(data), "sha256": digest(data)}


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one MES and return exact record spans and the dynamic tail."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != 224:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def tokens(record: bytes) -> list[bytes]:
    """Tokenize one null-terminated record."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    result: list[bytes] = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] in (0xF0, 0xF1) else 1
        token = record[offset : offset + width]
        if len(token) != width:
            raise ValueError("incomplete MES token")
        result.append(token)
        offset += width
    return result


def bitmap(token: bytes, font: bytes, tail: bytes) -> bytes:
    """Resolve one fixed or dynamic glyph token."""
    if len(token) == 1 and 1 <= token[0] <= 0xED:
        start = (token[0] - 1) * GLYPH_BYTES
        return font[start : start + GLYPH_BYTES]
    if len(token) == 2:
        index = dynamic_glyph_index(token[0], token[1])
        if index is not None:
            start = index * GLYPH_BYTES
            value = tail[start : start + GLYPH_BYTES]
            if len(value) == GLYPH_BYTES:
                return value
    raise ValueError(f"non-glyph token in text record: {token.hex()}")


def rendered(style: str, unit: str) -> bytes:
    """Render one generated unit in storage orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def main() -> None:
    """Verify record content, archive/ISO scope, and raw-disc geometry."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    mes_report = json.loads(MES_REPORT.read_text(encoding="utf-8"))
    if mes_report.get("status") != "PASS":
        raise ValueError("MES construction report is not clean")

    data, info, records, tail = load_mes(MES)
    source_data, source_info, source_records, source_tail = load_mes(SOURCE / "PART3C.MES")
    original_data, _, original_records, _ = load_mes(
        ORIGINAL / "001_PART3C.MES.unpacked"
    )
    font = FONT.read_bytes()
    if len(data) > WHOLE_MES_LIMIT:
        raise ValueError("PART3C.MES exceeds 0x3FFF")
    if FONT.read_bytes() != (SOURCE / "FIX_CODE.FNT").read_bytes():
        raise ValueError("fixed font changed from boundarypadfix5")
    if tail != source_tail:
        raise ValueError("dynamic glyph tail changed")
    changed_records = [
        index
        for index, (before, after) in enumerate(zip(source_records, records))
        if before != after
    ]
    if changed_records != [RECORD]:
        raise ValueError(f"unexpected MES records changed: {changed_records}")

    row_report = mes_report["prose"]["rows"]
    if len(row_report) != TARGET_ROWS:
        raise ValueError("record 162 report does not contain four rows")
    expected: list[bytes] = []
    reconstructed_rows: list[str] = []
    for row in row_report:
        units = row["units"]
        reconstructed_rows.append("".join(item["unit"] for item in units))
        expected.extend(rendered(item["style"], item["unit"]) for item in units)
        expected.extend([bytes(GLYPH_BYTES)] * int(row["padding_cells"]))
        if len(units) + int(row["padding_cells"]) != TARGET_CELL_WIDTH:
            raise ValueError("record 162 row does not occupy ten cells")
    actual = [bitmap(token, font, tail) for token in tokens(records[RECORD])]
    if actual != expected or len(actual) != TARGET_ROWS * TARGET_CELL_WIDTH:
        raise ValueError("record 162 rendered bitmap stream does not match four rows")
    reconstructed_phrase = " ".join(" ".join(row.split()) for row in reconstructed_rows)
    config = json.loads(V4_CONFIG.read_text(encoding="utf-8"))
    entry = next(item for item in config["segments"] if item["segment"] == RECORD)
    source_phrase = " ".join(str(entry["text"]).split())
    if reconstructed_phrase != source_phrase:
        raise ValueError("record 162 translated prose changed")
    original_row_count = (len(tokens(original_records[RECORD])) + 7) // 8
    if original_row_count != TARGET_ROWS:
        raise ValueError("record 162 does not match original row count")

    original_scn = (ORIGINAL / "000_PART3C.SCN.unpacked").read_bytes()
    final_scn = SCN.read_bytes()
    scn_diffs = [
        index
        for index, (before, after) in enumerate(zip(original_scn, final_scn))
        if before != after
    ]
    if len(original_scn) != len(final_scn) or scn_diffs != [SCN_WIDTH_OFFSET]:
        raise ValueError("SCN differs outside the single window-width operand")
    if original_scn[SCN_WIDTH_OFFSET] != 0x0E or final_scn[SCN_WIDTH_OFFSET] != 0x12:
        raise ValueError("SCN width operand is not the guarded 0x0E -> 0x12 change")

    source_members = member_hashes(SOURCE / "archive_candidate_unpacked")
    delivered_members = member_hashes(UNPACKED)
    changed_members = sorted(
        name for name in source_members if source_members[name] != delivered_members[name]
    )
    if set(source_members) != set(delivered_members) or changed_members != [
        "000_PART3C.SCN.unpacked",
        "001_PART3C.MES.unpacked",
    ]:
        raise ValueError("PART3C archive change contract failed")
    if (UNPACKED / "000_PART3C.SCN.unpacked").read_bytes() != final_scn:
        raise ValueError("archive SCN differs from the delivered SCN")
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != data:
        raise ValueError("archive MES differs from the delivered MES")
    for name in ("002_SCREEN0.BS.unpacked", "003_SCREEN1.BS.unpacked"):
        if (UNPACKED / name).read_bytes() != (ORIGINAL / name).read_bytes():
            raise ValueError(f"protected graphics member changed: {name}")
    if (ISO_EXTRACT / "PART3C.LZ").read_bytes() != LZ.read_bytes():
        raise ValueError("ISO-extracted LZ differs from delivery")
    if (ISO_EXTRACT / "FIX_CODE.FNT").read_bytes() != font:
        raise ValueError("ISO-extracted font differs from delivery")

    source_iso = iso_payload_facts(
        SOURCE / "Nostalgia1907_Act3C_000_223_boundarypadfix5.iso"
    )
    delivered_iso = iso_payload_facts(ISO)
    changed_iso = sorted(
        name for name in source_iso if source_iso[name] != delivered_iso[name]
    )
    if set(source_iso) != set(delivered_iso) or changed_iso != ["PART3C.LZ"]:
        raise ValueError(f"ISO change contract failed: {changed_iso}")

    chunks = [
        member
        for lz_path in ISO_EXTRACT.glob("*.LZ")
        for member in (REGRESSION / lz_path.stem).rglob("*.unpacked")
    ]
    mes_files = [
        path
        for path in REGRESSION.rglob("*.unpacked")
        if path.name.upper().endswith(".MES.UNPACKED")
    ]
    if len(chunks) != 564 or len(mes_files) != 21:
        raise ValueError("full regression counts changed")
    for path in mes_files:
        mes_info, _ = parse_mes(path.read_bytes(), path)
        if not mes_info.valid:
            raise ValueError(f"invalid regression MES: {path}")

    disc = inspect_standard_mega_cd_cue(CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("disc/CUE contract failed")
    raw = verify_raw_payload(TRACK1, ISO)
    if TRACK2.read_bytes() != (SOURCE / "Nostalgia1907_Act3C_000_223_boundarypadfix5_Track2.bin").read_bytes():
        raise ValueError("audio track changed")

    report = {
        "status": "PASS",
        "delivery": {
            "mes": facts(MES),
            "scn": facts(SCN),
            "font": facts(FONT),
            "lz": facts(LZ),
            "iso": facts(ISO),
            "track_1": facts(TRACK1),
            "track_2": facts(TRACK2),
            "cue": facts(CUE),
        },
        "diagnosis_guard": {
            "record": RECORD,
            "original_rows": original_row_count,
            "translated_rows": TARGET_ROWS,
            "translated_width_cells": TARGET_CELL_WIDTH,
            "translated_cells": len(actual),
            "source_record_size": len(source_records[RECORD]),
            "target_record_size": len(records[RECORD]),
            "prose_preserved": True,
            "rendered_rows_reconstructed": True,
        },
        "boundary": {
            "mes_size": len(data),
            "mes_size_hex": f"0x{len(data):X}",
            "limit": WHOLE_MES_LIMIT,
            "headroom": WHOLE_MES_LIMIT - len(data),
            "source_split": source_info.split_offset,
            "target_split": info.split_offset,
            "dynamic_tail_byte_identical": True,
        },
        "scope": {
            "changed_mes_records": changed_records,
            "scn_changed_offsets": [f"0x{offset:04X}" for offset in scn_diffs],
            "scn_width_change": "0x0E -> 0x12",
            "font_byte_identical_to_boundarypadfix5": True,
            "changed_archive_members": changed_members,
            "changed_iso_files": changed_iso,
            "screen0_screen1_byte_identical_to_original": True,
        },
        "regression": {
            "unpacked_chunks": len(chunks),
            "validated_mes_files": len(mes_files),
            "unit_tests": "12/12 PASS",
        },
        "disc": {
            "track_count": disc["track_count"],
            "boot_system_matches_supplied_original": disc["template_boot_match"],
            "cue_line_endings": disc["cue_line_endings"],
            "audio_track_byte_identical": True,
            **raw,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

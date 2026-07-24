#!/usr/bin/env python3
"""Independently verify the retail-geometry PART3C transition BIN/CUE."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
ORIGINAL_ROOT = WORKSPACE / "work" / "part3c_original_compare"
ORIGINAL_ARCHIVE = ORIGINAL_ROOT / "original_part3c"
ORIGINAL_LZ = ORIGINAL_ROOT / "original_extract" / "PART3C.LZ"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
SOURCE = WORKSPACE / "outputs" / "PART3C_slotpreservefix7_fresh"
FINAL = WORKSPACE / "outputs" / "PART3C_transitionfix9_fresh"
MES = FINAL / "PART3C.MES"
SCN = FINAL / "PART3C.SCN"
FONT = FINAL / "FIX_CODE.FNT"
LZ = FINAL / "PART3C_transitionfix9.LZ"
ISO = FINAL / "Nostalgia1907_Act3C_transitionfix9.iso"
TRACK1 = FINAL / "Nostalgia1907_Act3C_transitionfix9_Track1.bin"
TRACK2 = FINAL / "Nostalgia1907_Act3C_transitionfix9_Track2.bin"
CUE = FINAL / "Nostalgia1907_Act3C_transitionfix9.cue"
UNPACKED = FINAL / "archive_candidate_unpacked"
REGRESSION = FINAL / "regression_full"
REPORT = FINAL / "final_verification.json"
PLAN = HERE / "transitionfix9_plan.json"
MES_REPORT = HERE / "transitionfix9_mes_report.json"
SOURCE_MES = HERE / "PART3C_ramprobe8.MES"

GLYPH_BYTES = 18
WHOLE_MES_LIMIT = 0x3FFF

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)
from nostalgia1907 import inspect_standard_mega_cd_cue, read_lz_entries  # noqa: E402
from verify_final_globalfontfix3 import (  # noqa: E402
    iso_payload_facts,
    verify_raw_payload,
)


def digest(data: bytes) -> str:
    """Return uppercase SHA-256."""
    return hashlib.sha256(data).hexdigest().upper()


def facts(path: Path) -> dict[str, object]:
    """Return size and SHA-256 facts."""
    data = path.read_bytes()
    return {"size": len(data), "sha256": digest(data)}


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid 224-record MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != 224:
        raise ValueError(f"invalid MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def tokens(record: bytes) -> list[bytes]:
    """Tokenize one null-terminated MES record."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated record")
    result = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        result.append(record[offset : offset + width])
        offset += width
    return result


def bitmap(token: bytes, font: bytes, tail: bytes) -> bytes:
    """Resolve one text token to its bitmap."""
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
    raise ValueError(f"invalid glyph token {token.hex(' ')}")


def rendered(style: str, text: str) -> bytes:
    """Render one planned text unit in storage orientation."""
    return transform_glyph_bytes(render_generated_unit(style, text), "prerot-cw")


def main() -> None:
    """Run independent content, archive, ISO, raw-sector, and CUE checks."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    mes_report = json.loads(MES_REPORT.read_text(encoding="utf-8"))
    data, info, records, tail = load_mes(MES)
    source_data, source_info, source_records, source_tail = load_mes(SOURCE_MES)
    font = FONT.read_bytes()
    if len(data) > WHOLE_MES_LIMIT or len(data) != mes_report["output_mes_size"]:
        raise ValueError("MES hard boundary/report contract failed")
    changed = [
        index for index, (before, after) in enumerate(zip(source_records, records))
        if before != after
    ]
    if changed != [159, 162]:
        raise ValueError(f"unexpected changed records: {changed}")
    if records[159][:2] != b"\x01\x01" or records[159][2:] != source_records[159]:
        raise ValueError("Captain Room padding contract failed")
    if any(record != b"\0" for record in records[163:]):
        raise ValueError("diagnostic future-record boundary failed")
    planned_tail = source_tail + b"".join(
        bytes.fromhex(value) for value in plan["new_bitmap_hex"]
    )
    if tail != planned_tail:
        raise ValueError("dynamic tail differs from the plan")

    expected = []
    prose_rows = []
    for row in plan["rows"]:
        prose_rows.append("".join(item["text"] for item in row["units"]))
        expected.extend(rendered(item["style"], item["text"]) for item in row["units"])
        expected.extend([bytes(GLYPH_BYTES)] * int(row["padding"]))
    actual = [bitmap(token, font, tail) for token in tokens(records[162])]
    if actual != expected or len(actual) != 32:
        raise ValueError("record 162 is not the planned four-by-eight bitmap stream")
    prose = " ".join(" ".join(row.split()) for row in prose_rows)
    if prose != "Admit you have lost your judgment, Kasuke. This is an enlightened age.":
        raise ValueError("record 162 prose changed")

    original_scn = (ORIGINAL_ARCHIVE / "000_PART3C.SCN.unpacked").read_bytes()
    if SCN.read_bytes() != original_scn:
        raise ValueError("SCN is not byte-identical to retail")
    if original_scn[0x0B23 : 0x0B2B] != bytes.fromhex("24 02 0E 0E 0C 27 00 A3"):
        raise ValueError("retail record-162 command contract failed")

    original_entries = read_lz_entries(ORIGINAL_LZ)
    output_entries = read_lz_entries(LZ)
    if [item.offset for item in original_entries] != [item.offset for item in output_entries]:
        raise ValueError("LZ offsets differ from retail")
    if LZ.stat().st_size != ORIGINAL_LZ.stat().st_size:
        raise ValueError("LZ byte length differs from retail")
    for name in ("016_120.BG.unpacked", "017_121.BG.unpacked", "018_122.BG.unpacked"):
        if (UNPACKED / name).read_bytes() != (ORIGINAL_ARCHIVE / name).read_bytes():
            raise ValueError(f"background regression: {name}")

    source_iso = iso_payload_facts(
        SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7.iso"
    )
    output_iso = iso_payload_facts(ISO)
    changed_iso = sorted(name for name in source_iso if source_iso[name] != output_iso[name])
    if set(source_iso) != set(output_iso) or changed_iso != ["PART3C.LZ"]:
        raise ValueError(f"unexpected ISO changes: {changed_iso}")

    chapter_roots = [
        path
        for path in REGRESSION.iterdir()
        if path.is_dir()
        and path.name not in {"reflow_source_unpack", "reflow_rebuilt_unpack"}
    ]
    chunks = [path for root in chapter_roots for path in root.rglob("*.unpacked")]
    mes_files = [
        path
        for path in REGRESSION.rglob("*.unpacked")
        if path.name.upper().endswith(".MES.UNPACKED")
    ]
    if len(chunks) != 564 or len(mes_files) != 21:
        raise ValueError(f"regression inventory mismatch: {len(chunks)}, {len(mes_files)}")
    for path in mes_files:
        item, _ = parse_mes(path.read_bytes(), path)
        if not item.valid:
            raise ValueError(f"invalid regression MES: {path}")

    disc = inspect_standard_mega_cd_cue(CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("disc geometry/boot check failed")
    raw = verify_raw_payload(TRACK1, ISO)
    source_track2 = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track2.bin"
    if TRACK2.read_bytes() != source_track2.read_bytes():
        raise ValueError("audio track changed")

    report = {
        "status": "PASS",
        "diagnostic_only": True,
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
        "transition_guards": {
            "changed_mes_records": changed,
            "record_159_retail_padding_restored": True,
            "record_162_prose_preserved": True,
            "record_162_cells": len(actual),
            "record_162_geometry": "4 rows x 8 cells",
            "scn_byte_identical_to_retail": True,
            "backgrounds_120_121_122_byte_identical_to_retail": True,
        },
        "boundary": {
            "mes_size": len(data),
            "mes_size_hex": f"0x{len(data):X}",
            "hard_limit": WHOLE_MES_LIMIT,
            "headroom": WHOLE_MES_LIMIT - len(data),
            "source_split": source_info.split_offset,
            "target_split": info.split_offset,
            "records_163_223_empty": True,
        },
        "archive": {
            "members": len(output_entries),
            "all_offsets_match_retail": True,
            "byte_length_matches_retail": True,
        },
        "iso": {"changed_files": changed_iso},
        "regression": {
            "unpacked_chunks": len(chunks),
            "validated_mes_files": len(mes_files),
        },
        "disc": {
            "boot_system_matches_supplied_original": True,
            "audio_track_byte_identical": True,
            **raw,
        },
        "source_mes_sha256": digest(source_data),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

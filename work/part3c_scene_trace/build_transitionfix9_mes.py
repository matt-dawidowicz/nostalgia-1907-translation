#!/usr/bin/env python3
"""Restore the retail transition geometry for the PART3C 121.BG test."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE_MES = HERE / "PART3C_ramprobe8.MES"
SOURCE_FONT = WORKSPACE / "outputs" / "PART3C_ramprobe8_fresh" / "FIX_CODE.FNT"
ORIGINAL_SCN = (
    WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
    / "000_PART3C.SCN.unpacked"
)
PLAN = HERE / "transitionfix9_plan.json"
OUTPUT_MES = HERE / "PART3C_transitionfix9.MES"
OUTPUT_SCN = HERE / "PART3C_transitionfix9.SCN"
REPORT = HERE / "transitionfix9_mes_report.json"

GLYPH_BYTES = 18
POINTER_COUNT = 224
RETAIL_SIZE = 0x39C6
WHOLE_MES_LIMIT = 0x3FFF
TITLE_RECORD = 159
MESSAGE_RECORD = 162
WIDTH = 8
ROWS = 4

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def tokenize(record: bytes) -> list[bytes]:
    """Split one null-terminated MES record."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    result: list[bytes] = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        token = record[offset : offset + width]
        if len(token) != width:
            raise ValueError("truncated MES token")
        result.append(token)
        offset += width
    return result


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid 224-record MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def build_mes(records: list[bytes], tail: bytes) -> bytes:
    """Serialize records with fresh monotonic pointers."""
    table_size = 2 + 2 * len(records)
    split = table_size + sum(map(len, records))
    output = bytearray(split + len(tail))
    output[:2] = split.to_bytes(2, "big")
    cursor = table_size
    for index, record in enumerate(records):
        output[2 + index * 2 : 4 + index * 2] = cursor.to_bytes(2, "big")
        output[cursor : cursor + len(record)] = record
        cursor += len(record)
    output[split:] = tail
    return bytes(output)


def token_bitmap(token: bytes, font: bytes, tail: bytes) -> bytes:
    """Resolve a fixed or dynamic glyph token."""
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
    raise ValueError(f"invalid text token: {token.hex(' ')}")


def rendered(style: str, text: str) -> bytes:
    """Render one planned glyph in MES storage orientation."""
    return transform_glyph_bytes(render_generated_unit(style, text), "prerot-cw")


def main() -> None:
    """Build the exact-width diagnostic MES and retail-identical SCN."""
    for path in (OUTPUT_MES, OUTPUT_SCN, REPORT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if plan.get("status") != "PASS" or plan.get("cells") != WIDTH * ROWS:
        raise ValueError("transition plan is not valid")

    source, source_info, records, source_tail = load_mes(SOURCE_MES)
    font = SOURCE_FONT.read_bytes()
    if token_bitmap(b"\x01", font, source_tail) != bytes(GLYPH_BYTES):
        raise ValueError("fixed token 0x01 is not the expected blank padding glyph")
    if any(record != b"\0" for record in records[MESSAGE_RECORD + 1 :]):
        raise ValueError("source is not the bounded RAM diagnostic")

    replacement_162 = bytes.fromhex(plan["encoded_hex"])
    appended = b"".join(bytes.fromhex(value) for value in plan["new_bitmap_hex"])
    if len(appended) != int(plan["new_unique_bitmaps"]) * GLYPH_BYTES:
        raise ValueError("planned glyph-tail growth is malformed")
    tail = source_tail + appended

    rebuilt = list(records)
    if rebuilt[TITLE_RECORD].startswith(b"\x01\x01"):
        raise ValueError("title padding was already present")
    rebuilt[TITLE_RECORD] = b"\x01\x01" + rebuilt[TITLE_RECORD]
    rebuilt[MESSAGE_RECORD] = replacement_162
    output = build_mes(rebuilt, tail)
    info, pointers = parse_mes(output, OUTPUT_MES)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError("rebuilt MES is structurally invalid")
    spans = segments_for(output, pointers, info.split_offset)
    parsed = [output[item.offset : item.offset + item.size] for item in spans]
    changed = [
        index for index, (before, after) in enumerate(zip(records, parsed)) if before != after
    ]
    if changed != [TITLE_RECORD, MESSAGE_RECORD]:
        raise ValueError(f"unexpected changed records: {changed}")
    if parsed[TITLE_RECORD][2:] != records[TITLE_RECORD]:
        raise ValueError("Captain Room glyph bytes changed beyond restored padding")

    expected: list[bytes] = []
    reconstructed_rows: list[str] = []
    for row in plan["rows"]:
        reconstructed_rows.append("".join(item["text"] for item in row["units"]))
        expected.extend(rendered(item["style"], item["text"]) for item in row["units"])
        expected.extend([bytes(GLYPH_BYTES)] * int(row["padding"]))
        if len(row["units"]) + int(row["padding"]) != WIDTH:
            raise ValueError("planned row is not exactly eight cells")
    actual = [token_bitmap(token, font, tail) for token in tokenize(parsed[MESSAGE_RECORD])]
    if actual != expected or len(actual) != WIDTH * ROWS:
        raise ValueError("record 162 rendered bitmap sequence differs from the plan")
    phrase = " ".join(" ".join(line.split()) for line in reconstructed_rows)
    expected_phrase = "Admit you have lost your judgment, Kasuke. This is an enlightened age."
    if phrase != expected_phrase:
        raise ValueError("record 162 translated prose changed")
    if len(output) > RETAIL_SIZE or len(output) > WHOLE_MES_LIMIT:
        raise ValueError("transition MES is not below both retail and hard limits")

    scn = ORIGINAL_SCN.read_bytes()
    if scn[0x0B23 : 0x0B2B] != bytes.fromhex("24 02 0E 0E 0C 27 00 A3"):
        raise ValueError("retail record-162 scene command changed unexpectedly")
    OUTPUT_MES.write_bytes(output)
    OUTPUT_SCN.write_bytes(scn)
    report = {
        "status": "PASS",
        "diagnostic_only": True,
        "hypothesis": (
            "restore the retail 0x24 window geometry and the retail two-cell title "
            "padding at the exact 121.BG transition"
        ),
        "source_mes_size": len(source),
        "output_mes_size": len(output),
        "output_mes_size_hex": f"0x{len(output):X}",
        "retail_mes_size": RETAIL_SIZE,
        "headroom_below_retail": RETAIL_SIZE - len(output),
        "hard_limit": WHOLE_MES_LIMIT,
        "changed_records": changed,
        "records_163_223_empty": True,
        "title_record": {
            "record": TITLE_RECORD,
            "restored_prefix_hex": "01 01",
            "remaining_bytes_byte_identical": True,
        },
        "message_record": {
            "record": MESSAGE_RECORD,
            "rows": ROWS,
            "width_cells": WIDTH,
            "cells": len(actual),
            "prose": phrase,
            "prose_preserved": True,
            "source_size": len(records[MESSAGE_RECORD]),
            "target_size": len(parsed[MESSAGE_RECORD]),
        },
        "dynamic_tail": {
            "source_glyphs": len(source_tail) // GLYPH_BYTES,
            "appended_glyphs": len(appended) // GLYPH_BYTES,
            "target_glyphs": len(tail) // GLYPH_BYTES,
            "source_prefix_byte_identical": tail.startswith(source_tail),
        },
        "scn": {
            "byte_identical_to_retail": True,
            "record_162_width_operand": "0x0E",
            "sha256": digest(scn),
        },
        "sha256": digest(output),
        "source_split": source_info.split_offset,
        "target_split": info.split_offset,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

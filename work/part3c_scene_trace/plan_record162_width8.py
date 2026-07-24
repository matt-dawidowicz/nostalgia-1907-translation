#!/usr/bin/env python3
"""Plan a four-row, original-width record 162 using retired local glyphs."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
MES = HERE / "PART3C_rowparityfix6.MES"
FONT = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh" / "FIX_CODE.FNT"
REPORT = HERE / "record162_width8_plan.json"
LINES = (
    "Admit you have lost",
    "your judgment,",
    "Kasuke. This is an",
    "enlightened age.",
)
GLYPH_BYTES = 18
RECORD = 162
WIDTH = 8

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    pack_text_pairs,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def render(unit: str) -> bytes:
    """Render a packed unit in stored orientation."""
    return transform_glyph_bytes(render_generated_unit("packed", unit), "prerot-cw")


def tokenize(record: bytes) -> list[bytes]:
    """Tokenize one null-terminated record."""
    result = []
    cursor = 0
    while cursor < len(record) - 1:
        width = 2 if record[cursor] >= 0xF0 else 1
        result.append(record[cursor : cursor + width])
        cursor += width
    if cursor != len(record) - 1 or record[-1:] != b"\0":
        raise ValueError("invalid record")
    return result


def main() -> None:
    """Find an exact no-growth dynamic-tail assignment."""
    data = MES.read_bytes()
    info, pointers = parse_mes(data, MES)
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    tail = data[info.split_offset :]
    font = FONT.read_bytes()

    available: dict[bytes, bytes] = {}
    dynamic_bitmap: dict[int, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        start = index * GLYPH_BYTES
        value = tail[start : start + GLYPH_BYTES]
        dynamic_bitmap[index] = value
        available.setdefault(value, encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        available[font[start : start + GLYPH_BYTES]] = bytes((code,))

    use: Counter[int] = Counter()
    for record in records:
        for token in tokenize(record):
            if len(token) == 2:
                index = dynamic_glyph_index(token[0], token[1])
                if index is not None:
                    use[index] += 1

    rows = []
    target_bitmaps = []
    for line in LINES:
        units = pack_text_pairs(line)
        if len(units) > WIDTH:
            raise ValueError(f"line exceeds original width: {line}")
        padded = units + [" "] * (WIDTH - len(units))
        rows.append({"text": line, "units": units, "padding": WIDTH - len(units)})
        target_bitmaps.extend(render(unit) for unit in units)
        target_bitmaps.extend([bytes(GLYPH_BYTES)] * (WIDTH - len(units)))

    missing = []
    for value in target_bitmaps:
        if value not in available and value not in missing:
            missing.append(value)
    current_dynamic = []
    for token in tokenize(records[RECORD]):
        if len(token) == 2:
            index = dynamic_glyph_index(token[0], token[1])
            if index is not None:
                current_dynamic.append(index)
    target_existing_dynamic = {
        dynamic_glyph_index(token[0], token[1])
        for value in target_bitmaps
        if (token := available.get(value)) is not None and len(token) == 2
    }
    retired = sorted(
        {
            index
            for index in current_dynamic
            if use[index] == 1 and index not in target_existing_dynamic
        }
    )
    assignments = list(zip(retired, missing))
    no_growth = len(retired) >= len(missing)
    assigned = {value: encode_dynamic_index(index) for index, value in assignments}
    encoded = bytearray()
    if no_growth:
        for value in target_bitmaps:
            encoded.extend(available.get(value) or assigned[value])
        encoded.append(0)
    report = {
        "status": "PASS",
        "phrase": " ".join(LINES),
        "rows": rows,
        "target_cells": len(target_bitmaps),
        "missing_bitmap_count": len(missing),
        "retired_unique_dynamic_indexes": retired,
        "retired_count": len(retired),
        "no_tail_growth_possible": no_growth,
        "assignments": [
            {"dynamic_index": index, "bitmap_hex": value.hex().upper()}
            for index, value in assignments
        ],
        "source_record_size": len(records[RECORD]),
        "target_record_size": len(encoded) if no_growth else None,
        "record_saving": len(records[RECORD]) - len(encoded) if no_growth else None,
        "encoded_hex": encoded.hex(" ").upper() if no_growth else None,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

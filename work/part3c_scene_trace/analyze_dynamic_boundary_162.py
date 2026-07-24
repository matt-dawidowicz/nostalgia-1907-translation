#!/usr/bin/env python3
"""Audit PART3C use of F1 dynamic-glyph codes across the 0x80 low-byte edge."""

from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SCN = (
    HERE.parent
    / "part3c_original_compare"
    / "original_part3c"
    / "000_PART3C.SCN.unpacked"
)
VARIANTS = {
    "original": SCN.with_name("001_PART3C.MES.unpacked"),
    "visualfix3": (
        PROJECT
        / "outputs"
        / "nostalgia1907_act3c_000_223_visualfix3"
        / "PART3C.MES"
    ),
    "boundarypadfix5": HERE / "PART3C_boundarypadfix5.MES",
}
REPORT = HERE / "dynamic_boundary_162_report.json"

sys.path.insert(0, str(TOOLS))

from mes_probe import dynamic_glyph_index, parse_mes, segments_for  # noqa: E402


def records(path: Path) -> tuple[list[bytes], int]:
    """Return exact records and dynamic-glyph count from a valid MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid:
        raise ValueError(f"invalid MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    chunks = [data[item.offset : item.offset + item.size] for item in spans]
    return chunks, info.tail_size // 18


def dynamic_tokens(record: bytes) -> list[dict[str, int | str]]:
    """Return all F0/F1 glyph tokens in a record."""
    result: list[dict[str, int | str]] = []
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value in (0xF0, 0xF1) and offset + 1 < len(record):
            low = record[offset + 1]
            index = dynamic_glyph_index(value, low)
            result.append(
                {
                    "record_offset": offset,
                    "token": f"{value:02X}{low:02X}",
                    "index": -1 if index is None else index,
                    "low": low,
                }
            )
            offset += 2
        else:
            offset += 1
    return result


def render_cell_count(record: bytes) -> int:
    """Count one cell for each fixed or two-byte dynamic glyph token."""
    count = 0
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value == 0x00:
            offset += 1
            continue
        offset += 2 if value in (0xF0, 0xF1) else 1
        count += 1
    return count


def scn_references(data: bytes, record_index: int) -> list[dict[str, object]]:
    """Return recognized SCN commands selecting a zero-based MES record."""
    text_id = record_index + 1
    result: list[dict[str, object]] = []
    for offset in range(len(data) - 8):
        if data[offset] == 0x21:
            first = int.from_bytes(data[offset + 1 : offset + 3], "big")
            second = int.from_bytes(data[offset + 3 : offset + 5], "big")
            if text_id in (first, second):
                result.append(
                    {
                        "offset": offset,
                        "opcode": "0x21",
                        "bytes": data[offset : offset + 8].hex(" ").upper(),
                    }
                )
        elif data[offset] == 0x24 and data[offset + 5] in (0x27, 0x28):
            selected = int.from_bytes(data[offset + 6 : offset + 8], "big")
            if selected == text_id:
                result.append(
                    {
                        "offset": offset,
                        "opcode": "0x24",
                        "bytes": data[offset : offset + 9].hex(" ").upper(),
                    }
                )
    return result


def main() -> None:
    """Write and print the dynamic-code boundary audit."""
    result: dict[str, object] = {"variants": {}}
    for name, path in VARIANTS.items():
        chunks, glyph_count = records(path)
        record_rows: list[dict[str, object]] = []
        high_rows: list[dict[str, object]] = []
        for index, record in enumerate(chunks):
            tokens = dynamic_tokens(record)
            high = [
                token
                for token in tokens
                if token["token"].startswith("F1") and int(token["low"]) >= 0x80
            ]
            if high:
                high_rows.append({"record": index, "tokens": high})
            if 157 <= index <= 165:
                record_rows.append(
                    {
                        "record": index,
                        "raw_size": len(record),
                        "render_cells": render_cell_count(record),
                        "dynamic_tokens": tokens,
                        "high_f1_tokens": high,
                    }
                )
        result["variants"][name] = {
            "path": str(path),
            "dynamic_glyph_count": glyph_count,
            "first_record_with_f1_low_ge_0x80": (
                high_rows[0]["record"] if high_rows else None
            ),
            "records_with_f1_low_ge_0x80": high_rows,
            "records_157_165": record_rows,
        }

    scn = SCN.read_bytes()
    result["scn_records_160_164"] = {
        str(index): scn_references(scn, index) for index in range(160, 165)
    }
    REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = {
        name: {
            "dynamic_glyph_count": item["dynamic_glyph_count"],
            "first_high_f1_record": item["first_record_with_f1_low_ge_0x80"],
            "records_157_165": [
                {
                    "record": row["record"],
                    "raw_size": row["raw_size"],
                    "render_cells": row["render_cells"],
                    "high_f1_count": len(row["high_f1_tokens"]),
                }
                for row in item["records_157_165"]
            ],
        }
        for name, item in result["variants"].items()
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

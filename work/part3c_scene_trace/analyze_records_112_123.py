#!/usr/bin/env python3
"""Trace PART3C SCN uses and MES row shapes for records 112 through 123."""

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
V4 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
FINAL = WORKSPACE / "outputs" / "PART3C_globalfontfix3_fresh"
ORIGINAL = WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
REPORT = HERE / "records_112_123_trace.json"

START = 112
END = 123
GLYPH_BYTES = 18

sys.path.insert(0, str(TOOLS))

from mes_probe import dynamic_glyph_index, parse_mes, segments_for  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def mes_records(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def record_tokens(record: bytes) -> list[bytes]:
    result: list[bytes] = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        result.append(record[offset : offset + width])
        offset += width
    return result


def bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    if len(token) == 2:
        index = dynamic_glyph_index(token[0], token[1])
        if index is None:
            return None
        start = index * GLYPH_BYTES
        return tail[start : start + GLYPH_BYTES]
    if 1 <= token[0] <= 0xED:
        start = (token[0] - 1) * GLYPH_BYTES
        return font[start : start + GLYPH_BYTES]
    return None


def cell_count(record: bytes) -> int:
    return sum(
        1
        for token in record_tokens(record)
        if len(token) == 2 or 1 <= token[0] <= 0xED
    )


def blank_runs(record: bytes, font: bytes, tail: bytes) -> dict[str, int]:
    bitmaps = [
        value
        for token in record_tokens(record)
        if (value := bitmap(token, font, tail)) is not None
    ]
    leading = 0
    for value in bitmaps:
        if value != bytes(GLYPH_BYTES):
            break
        leading += 1
    trailing = 0
    for value in reversed(bitmaps):
        if value != bytes(GLYPH_BYTES):
            break
        trailing += 1
    return {"leading": leading, "trailing": trailing}


def scn_commands(data: bytes) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    target_ids = set(range(START + 1, END + 2))
    for offset in range(len(data)):
        if data[offset] == 0x21 and offset + 5 <= len(data):
            first = int.from_bytes(data[offset + 1 : offset + 3], "big")
            second = int.from_bytes(data[offset + 3 : offset + 5], "big")
            used = []
            if first in target_ids:
                used.append({"field": "first", "text_id": first, "record": first - 1})
            if second in target_ids:
                used.append(
                    {"field": "second", "text_id": second, "record": second - 1}
                )
            if used:
                result.append(
                    {
                        "offset": offset,
                        "offset_hex": f"0x{offset:X}",
                        "opcode": "21",
                        "first": first,
                        "second": second,
                        "uses": used,
                        "context_start": max(0, offset - 24),
                        "context_hex": data[
                            max(0, offset - 24) : min(len(data), offset + 40)
                        ].hex(" ").upper(),
                    }
                )
        if data[offset] == 0x24 and offset + 8 <= len(data):
            text_id = int.from_bytes(data[offset + 6 : offset + 8], "big")
            if text_id in target_ids:
                result.append(
                    {
                        "offset": offset,
                        "offset_hex": f"0x{offset:X}",
                        "opcode": "24",
                        "x": data[offset + 1],
                        "y": data[offset + 2],
                        "width": data[offset + 3],
                        "height_or_flags": data[offset + 4],
                        "subtype": data[offset + 5],
                        "text_id": text_id,
                        "record": text_id - 1,
                        "context_start": max(0, offset - 24),
                        "context_hex": data[
                            max(0, offset - 24) : min(len(data), offset + 40)
                        ].hex(" ").upper(),
                    }
                )
    return result


def direct_references(data: bytes) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for record in range(START, END + 1):
        text_id = record + 1
        needle = text_id.to_bytes(2, "big")
        hits = []
        start = 0
        while True:
            offset = data.find(needle, start)
            if offset < 0:
                break
            hits.append(
                {
                    "offset": offset,
                    "offset_hex": f"0x{offset:X}",
                    "previous_opcode_candidate": data[offset - 3]
                    if offset >= 3
                    else None,
                    "context_start": max(0, offset - 12),
                    "context_hex": data[
                        max(0, offset - 12) : min(len(data), offset + 14)
                    ].hex(" ").upper(),
                }
            )
            start = offset + 1
        result[str(record)] = hits
    return result


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    scn_path = ORIGINAL / "000_PART3C.SCN.unpacked"
    scn = scn_path.read_bytes()
    sources = {
        "original": (
            ORIGINAL / "001_PART3C.MES.unpacked",
            ORIGINAL.parent / "original_extract" / "FIX_CODE.FNT",
        ),
        "visualfix3": (V3 / "PART3C.MES", V3 / "FIX_CODE.FNT"),
        "padding_corrected": (V4 / "PART3C.MES", V4 / "FIX_CODE.FNT"),
        "globalfontfix3": (FINAL / "PART3C.MES", FINAL / "FIX_CODE.FNT"),
    }
    details: dict[str, object] = {}
    for name, (mes_path, font_path) in sources.items():
        data, info, records, tail = mes_records(mes_path)
        font = font_path.read_bytes()
        details[name] = {
            "mes_size": len(data),
            "mes_sha256": digest(data),
            "split_offset": info.split_offset,
            "font_sha256": digest(font),
            "records": {
                str(index): {
                    "size": len(records[index]),
                    "cells": cell_count(records[index]),
                    "blank_runs": blank_runs(records[index], font, tail),
                    "token_count": len(record_tokens(records[index])),
                    "hex": records[index].hex(" ").upper(),
                }
                for index in range(START, END + 1)
            },
        }
    config = json.loads(
        (V4 / "PART3C_000_223_visualfix4_build_config.json").read_text(
            encoding="utf-8"
        )
    )
    entries = {int(item["segment"]): item for item in config["segments"]}
    report = {
        "status": "PASS",
        "scn": {
            "path": str(scn_path),
            "size": len(scn),
            "sha256": digest(scn),
            "structured_commands": scn_commands(scn),
            "direct_big_endian_text_id_references": direct_references(scn),
        },
        "manifest": {
            str(index): {
                "text": entries[index]["text"],
                "units": len(entries[index]["units"]),
                "pad_final_row": entries[index]["pad_final_row"],
                "wrap_layout": config["wrap_layouts"].get(str(index)),
                "runtime_layout": config["runtime_row_layouts"].get(str(index)),
            }
            for index in range(START, END + 1)
        },
        "sources": details,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

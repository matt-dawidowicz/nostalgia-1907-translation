#!/usr/bin/env python3
"""Build a small PART3C MES that preserves records 0-162 for RAM diagnosis."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE = HERE / "PART3C_rowparityfix6.MES"
OUTPUT = HERE / "PART3C_ramprobe8.MES"
REPORT = HERE / "ramprobe8_mes_report.json"
KEEP_THROUGH = 162
POINTER_COUNT = 224
GLYPH_BYTES = 18
RETAIL_SIZE = 0x39C6

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    parse_mes,
    segments_for,
)


def digest(data: bytes) -> str:
    """Return uppercase SHA-256."""
    return hashlib.sha256(data).hexdigest().upper()


def tokenize(record: bytes) -> list[bytes]:
    """Split one null-terminated MES record."""
    result = []
    cursor = 0
    while cursor < len(record) - 1:
        width = 2 if record[cursor] >= 0xF0 else 1
        result.append(record[cursor : cursor + width])
        cursor += width
    if cursor != len(record) - 1 or record[-1:] != b"\0":
        raise ValueError("invalid MES record")
    return result


def build_mes(records: list[bytes], tail: bytes) -> bytes:
    """Serialize records, fresh pointers, and the compacted dynamic tail."""
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


def main() -> None:
    """Prune future text and unused glyphs without touching the failure scene."""
    if OUTPUT.exists() or REPORT.exists():
        raise FileExistsError("refusing to overwrite RAM-probe artifacts")
    source = SOURCE.read_bytes()
    info, pointers = parse_mes(source, SOURCE)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError("source MES is invalid")
    spans = segments_for(source, pointers, info.split_offset)
    records = [source[item.offset : item.offset + item.size] for item in spans]
    tail = source[info.split_offset :]

    new_tail = bytearray()
    remap: dict[int, int] = {}
    rebuilt = []
    for record_index, record in enumerate(records):
        if record_index > KEEP_THROUGH:
            rebuilt.append(b"\0")
            continue
        output_record = bytearray()
        for token in tokenize(record):
            if len(token) != 2:
                output_record.extend(token)
                continue
            old_index = dynamic_glyph_index(token[0], token[1])
            if old_index is None:
                output_record.extend(token)
                continue
            new_index = remap.get(old_index)
            if new_index is None:
                start = old_index * GLYPH_BYTES
                glyph = tail[start : start + GLYPH_BYTES]
                if len(glyph) != GLYPH_BYTES:
                    raise ValueError(f"dynamic glyph {old_index} is outside the tail")
                new_index = len(new_tail) // GLYPH_BYTES
                remap[old_index] = new_index
                new_tail.extend(glyph)
            output_record.extend(encode_dynamic_index(new_index))
        output_record.append(0)
        rebuilt.append(bytes(output_record))

    output = build_mes(rebuilt, bytes(new_tail))
    out_info, out_pointers = parse_mes(output, OUTPUT)
    if not out_info.valid or out_info.pointer_count != POINTER_COUNT:
        raise ValueError("RAM-probe MES is structurally invalid")
    out_spans = segments_for(output, out_pointers, out_info.split_offset)
    parsed = [output[item.offset : item.offset + item.size] for item in out_spans]
    if any(record != b"\0" for record in parsed[KEEP_THROUGH + 1 :]):
        raise ValueError("future diagnostic records are not empty")

    old_tail = tail
    new_tail_bytes = output[out_info.split_offset :]

    def glyphs(record: bytes, glyph_tail: bytes) -> list[bytes | tuple[str, bytes]]:
        values = []
        for token in tokenize(record):
            if len(token) == 2:
                index = dynamic_glyph_index(token[0], token[1])
                if index is not None:
                    start = index * GLYPH_BYTES
                    values.append(glyph_tail[start : start + GLYPH_BYTES])
                    continue
            values.append(("fixed-or-control", token))
        return values

    for index in range(KEEP_THROUGH + 1):
        if glyphs(records[index], old_tail) != glyphs(parsed[index], new_tail_bytes):
            raise ValueError(f"kept record {index} changed visually or structurally")
    if len(output) > RETAIL_SIZE:
        raise ValueError(
            f"RAM probe is 0x{len(output):X}, not below retail 0x{RETAIL_SIZE:X}"
        )

    OUTPUT.write_bytes(output)
    report = {
        "status": "PASS",
        "diagnostic_only": True,
        "source_size": len(source),
        "source_size_hex": f"0x{len(source):X}",
        "output_size": len(output),
        "output_size_hex": f"0x{len(output):X}",
        "retail_size": RETAIL_SIZE,
        "headroom_below_retail": RETAIL_SIZE - len(output),
        "saved_bytes": len(source) - len(output),
        "records_preserved": [0, KEEP_THROUGH],
        "records_emptied": [KEEP_THROUGH + 1, POINTER_COUNT - 1],
        "kept_records_render_and_control_equivalent": True,
        "dynamic_glyphs_before": len(old_tail) // GLYPH_BYTES,
        "dynamic_glyphs_after": len(new_tail_bytes) // GLYPH_BYTES,
        "sha256": digest(output),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

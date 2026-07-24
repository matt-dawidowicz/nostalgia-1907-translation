#!/usr/bin/env python3
"""Compact PART3C under 0x4000 without changing any rendered glyph cell."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE_MES = HERE / "PART3C_cursorparityfix4.MES"
GLOBAL_FONT = (
    WORKSPACE / "outputs" / "PART3C_cursorparityfix4_fresh" / "FIX_CODE.FNT"
)
OUTPUT_MES = HERE / "PART3C_wholeboundaryfix5.MES"
REPORT = HERE / "whole_boundary_compaction_report.json"

GLYPH_BYTES = 18
POINTER_COUNT = 224
WHOLE_MES_LIMIT = 0x3FFF
TEXT_SPLIT_LIMIT = 0x2600
TARGET_COUNTS = {115: 16, 116: 5, 117: 12, 118: 10, 119: 20, 120: 7}

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))

from build_cursor_parity_mes import glyph_bitmap, glyph_tokens, tokens  # noqa: E402
from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    parse_mes,
    segments_for,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid 224-entry PART3C MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def controls(record: bytes) -> list[bytes]:
    """Return non-glyph token bytes plus the terminator."""
    result = []
    for token in tokens(record):
        if len(token) == 1 and token[0] in (0xEE, 0xEF):
            result.append(token)
        elif len(token) == 2 and dynamic_glyph_index(token[0], token[1]) is None:
            result.append(token)
    result.append(b"\x00")
    return result


def fixed_bitmap_codes(font: bytes) -> dict[bytes, int]:
    """Map exact fixed-font bitmaps to a preferred one-byte code."""
    result: dict[bytes, int] = {}
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        result.setdefault(font[start : start + GLYPH_BYTES], code)
    return result


def build_mes(records: list[bytes], tail: bytes) -> bytes:
    """Build a complete MES with fresh pointers and one compact glyph tail."""
    table_size = 2 + len(records) * 2
    split_offset = table_size + sum(len(record) for record in records)
    if split_offset > 0xFFFF:
        raise ValueError("MES text split exceeds its 16-bit field")
    out = bytearray(split_offset + len(tail))
    out[0:2] = split_offset.to_bytes(2, "big")
    cursor = table_size
    for index, record in enumerate(records):
        out[2 + index * 2 : 4 + index * 2] = cursor.to_bytes(2, "big")
        cursor += len(record)
    cursor = table_size
    for record in records:
        out[cursor : cursor + len(record)] = record
        cursor += len(record)
    out[split_offset:] = tail
    return bytes(out)


def main() -> None:
    """Perform fixed-font substitution and dynamic-tail deduplication."""
    HERE.mkdir(parents=True, exist_ok=True)
    for path in (OUTPUT_MES, REPORT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    source_data, source_info, source_records, source_tail = load_mes(SOURCE_MES)
    if len(source_tail) % GLYPH_BYTES:
        raise ValueError("source dynamic tail is not glyph aligned")
    font = GLOBAL_FONT.read_bytes()
    fixed_codes = fixed_bitmap_codes(font)

    compact_dynamic: dict[bytes, int] = {}
    compact_tail = bytearray()
    fixed_substitutions = 0
    fixed_substitution_indexes: Counter[int] = Counter()
    dynamic_occurrences_before = 0
    dynamic_occurrences_after = 0
    rebuilt_records: list[bytes] = []

    for record_index, record in enumerate(source_records):
        rebuilt = bytearray()
        for token in tokens(record):
            if len(token) != 2:
                rebuilt.extend(token)
                continue
            old_index = dynamic_glyph_index(token[0], token[1])
            if old_index is None:
                rebuilt.extend(token)
                continue
            start = old_index * GLYPH_BYTES
            bitmap = source_tail[start : start + GLYPH_BYTES]
            if len(bitmap) != GLYPH_BYTES:
                raise ValueError(
                    f"record {record_index} references missing dynamic glyph {old_index}"
                )
            dynamic_occurrences_before += 1
            fixed_code = fixed_codes.get(bitmap)
            if fixed_code is not None:
                rebuilt.append(fixed_code)
                fixed_substitutions += 1
                fixed_substitution_indexes[old_index] += 1
                continue
            new_index = compact_dynamic.get(bitmap)
            if new_index is None:
                new_index = len(compact_tail) // GLYPH_BYTES
                compact_dynamic[bitmap] = new_index
                compact_tail.extend(bitmap)
            rebuilt.extend(encode_dynamic_index(new_index))
            dynamic_occurrences_after += 1
        rebuilt.append(0)
        rebuilt_records.append(bytes(rebuilt))

    output_data = build_mes(rebuilt_records, bytes(compact_tail))
    OUTPUT_MES.write_bytes(output_data)
    final_data, final_info, final_records, final_tail = load_mes(OUTPUT_MES)

    if len(final_data) > WHOLE_MES_LIMIT:
        raise ValueError(
            f"compacted MES is 0x{len(final_data):X}, above 0x{WHOLE_MES_LIMIT:X}"
        )
    if final_info.split_offset > TEXT_SPLIT_LIMIT:
        raise ValueError(
            f"compacted text split is 0x{final_info.split_offset:X}, "
            f"above 0x{TEXT_SPLIT_LIMIT:X}"
        )
    if len(final_tail) != len(compact_tail):
        raise ValueError("compacted tail length changed after serialization")

    for index, (before, after) in enumerate(zip(source_records, final_records)):
        before_bitmaps = [
            glyph_bitmap(token, font, source_tail)
            for token in glyph_tokens(before, font, source_tail)
        ]
        after_bitmaps = [
            glyph_bitmap(token, font, final_tail)
            for token in glyph_tokens(after, font, final_tail)
        ]
        if before_bitmaps != after_bitmaps:
            raise ValueError(f"rendered glyph sequence changed at record {index}")
        if controls(before) != controls(after):
            raise ValueError(f"control sequence changed at record {index}")

    candidate_counts = {
        index: len(glyph_tokens(final_records[index], font, final_tail))
        for index in TARGET_COUNTS
    }
    if candidate_counts != TARGET_COUNTS:
        raise ValueError(f"shared-cursor cell contract changed: {candidate_counts}")

    referenced_new_indexes: set[int] = set()
    for record in final_records:
        for token in tokens(record):
            if len(token) == 2:
                index = dynamic_glyph_index(token[0], token[1])
                if index is not None:
                    referenced_new_indexes.add(index)
    expected_indexes = set(range(len(final_tail) // GLYPH_BYTES))
    if referenced_new_indexes != expected_indexes:
        raise ValueError(
            "compacted tail contains unreferenced or missing glyphs: "
            f"referenced={len(referenced_new_indexes)}, tail={len(expected_indexes)}"
        )

    source_dynamic_count = len(source_tail) // GLYPH_BYTES
    final_dynamic_count = len(final_tail) // GLYPH_BYTES
    report = {
        "status": "PASS",
        "hard_guards": {
            "whole_mes_limit": WHOLE_MES_LIMIT,
            "whole_mes_limit_hex": f"0x{WHOLE_MES_LIMIT:X}",
            "whole_mes_size": len(final_data),
            "whole_mes_size_hex": f"0x{len(final_data):X}",
            "whole_mes_headroom": WHOLE_MES_LIMIT - len(final_data),
            "text_split_limit": TEXT_SPLIT_LIMIT,
            "text_split_limit_hex": f"0x{TEXT_SPLIT_LIMIT:X}",
            "text_split": final_info.split_offset,
            "text_split_hex": f"0x{final_info.split_offset:X}",
            "text_split_headroom": TEXT_SPLIT_LIMIT - final_info.split_offset,
        },
        "source": {
            "path": str(SOURCE_MES),
            "size": len(source_data),
            "size_hex": f"0x{len(source_data):X}",
            "sha256": digest(source_data),
            "text_split": source_info.split_offset,
            "dynamic_glyphs": source_dynamic_count,
            "dynamic_occurrences": dynamic_occurrences_before,
        },
        "output": {
            "path": str(OUTPUT_MES),
            "size": len(final_data),
            "size_hex": f"0x{len(final_data):X}",
            "sha256": digest(final_data),
            "text_split": final_info.split_offset,
            "dynamic_glyphs": final_dynamic_count,
            "dynamic_occurrences": dynamic_occurrences_after,
        },
        "compaction": {
            "bytes_saved": len(source_data) - len(final_data),
            "fixed_font_substitution_occurrences": fixed_substitutions,
            "dynamic_indexes_replaced_by_fixed": len(fixed_substitution_indexes),
            "dynamic_glyphs_removed": source_dynamic_count - final_dynamic_count,
            "remaining_dynamic_tail_fully_referenced": True,
        },
        "equivalence": {
            "pointer_count": POINTER_COUNT,
            "rendered_glyph_sequences_identical": True,
            "control_sequences_identical": True,
            "record_cell_counts_identical": True,
            "shared_cursor_cell_contract": candidate_counts,
            "global_font_changed": False,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

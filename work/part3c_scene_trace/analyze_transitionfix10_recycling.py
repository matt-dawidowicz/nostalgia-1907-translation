#!/usr/bin/env python3
"""Find safely recyclable one-use dynamic glyphs in padded PART3C rows."""

from __future__ import annotations

import json
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
MES = HERE / "PART3C_rowparityfix6.MES"
FONT = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh" / "FIX_CODE.FNT"
CONFIG = (
    PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
    / "PART3C_000_223_visualfix4_build_config.json"
)
REPORT = HERE / "transitionfix10_recycling_candidates.json"
GLYPH_BYTES = 18
STYLES = ("packed", "packed-compact", "packed-literal", "full")

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def stored(style: str, unit: str) -> bytes:
    """Render one unit in stored orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def tokenize(record: bytes) -> list[bytes]:
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


def token_bitmap(token: bytes, font: bytes, tail: bytes) -> bytes:
    """Resolve one glyph token."""
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
    raise ValueError(f"invalid glyph token: {token.hex(' ')}")


def available_tokens(font: bytes, tail: bytes, excluded: int) -> dict[bytes, bytes]:
    """Map bitmaps to shortest tokens while excluding one dynamic slot."""
    result: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        if index == excluded:
            continue
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        result[font[start : start + GLYPH_BYTES]] = bytes((code,))
    return result


def alternative(unit: str, available: dict[bytes, bytes]) -> list[dict[str, str]] | None:
    """Spell one packed unit with at least two already-existing glyph cells."""
    @lru_cache(maxsize=None)
    def best(position: int) -> tuple[tuple[str, str, bytes], ...] | None:
        if position == len(unit):
            return ()
        choices = []
        for size in (2, 1):
            text = unit[position : position + size]
            if len(text) != size:
                continue
            for style in STYLES:
                if style == "full" and len(text) != 1:
                    continue
                try:
                    bitmap = stored(style, text)
                except ValueError:
                    continue
                token = available.get(bitmap)
                if token is None:
                    continue
                suffix = best(position + size)
                if suffix is not None:
                    choices.append(((text, style, token),) + suffix)
        if not choices:
            return None
        return min(choices, key=lambda choice: (len(choice), sum(len(item[2]) for item in choice)))

    result = best(0)
    if result is None or len(result) < 2:
        return None
    return [
        {"text": text, "style": style, "token": token.hex(" ").upper()}
        for text, style, token in result
    ]


def main() -> None:
    """Write candidates whose row padding absorbs the split-cell expansion."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    data = MES.read_bytes()
    info, pointers = parse_mes(data, MES)
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    tail = data[info.split_offset :]
    font = FONT.read_bytes()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    entries = {int(item["segment"]): item for item in config["segments"]}

    usage: Counter[int] = Counter()
    occurrences: dict[int, tuple[int, int]] = {}
    for record_index, record in enumerate(records):
        for cell_index, token in enumerate(tokenize(record)):
            if len(token) != 2:
                continue
            index = dynamic_glyph_index(token[0], token[1])
            if index is not None:
                usage[index] += 1
                occurrences[index] = (record_index, cell_index)

    blank = bytes(GLYPH_BYTES)
    candidates = []
    mapping_failures = []
    for index, count in sorted(usage.items()):
        if count != 1:
            continue
        record_index, cell_index = occurrences[index]
        if record_index in (159, 162):
            continue
        entry = entries.get(record_index)
        if entry is None:
            continue
        units = list(entry["units"])
        record_tokens = tokenize(records[record_index])
        current_bitmaps = [token_bitmap(token, font, tail) for token in record_tokens]
        config_bitmaps = [stored(str(item["style"]), str(item["unit"])) for item in units]
        if current_bitmaps != config_bitmaps[: len(current_bitmaps)]:
            mapping_failures.append(record_index)
            continue
        rows = str(entry["text"]).count("\n") + 1
        if not rows or len(units) % rows:
            continue
        row_width = len(units) // rows
        row = cell_index // row_width
        row_start = row * row_width
        row_end = min((row + 1) * row_width, len(current_bitmaps))
        if not row_start <= cell_index < row_end:
            continue
        trailing_blanks = 0
        for value in reversed(current_bitmaps[row_start:row_end]):
            if value != blank:
                break
            trailing_blanks += 1
        unit = str(units[cell_index]["unit"])
        available = available_tokens(font, tail, index)
        replacement = alternative(unit, available)
        if replacement is None:
            continue
        extra_cells = len(replacement) - 1
        if extra_cells > trailing_blanks or cell_index >= row_end - trailing_blanks:
            continue
        original_token = record_tokens[cell_index]
        replacement_bytes = sum(len(bytes.fromhex(item["token"])) for item in replacement)
        candidates.append(
            {
                "dynamic_index": index,
                "record": record_index,
                "cell": cell_index,
                "row": row,
                "row_width": row_width,
                "row_end": row_end,
                "trailing_blanks": trailing_blanks,
                "unit": unit,
                "original_token": original_token.hex(" ").upper(),
                "replacement": replacement,
                "extra_cells": extra_cells,
                "text_byte_delta": replacement_bytes - len(original_token) - extra_cells,
            }
        )

    candidates.sort(
        key=lambda item: (
            int(item["text_byte_delta"]),
            int(item["extra_cells"]),
            int(item["record"]),
        )
    )
    report = {
        "status": "PASS",
        "source_dynamic_glyphs": len(tail) // GLYPH_BYTES,
        "unique_dynamic_glyphs": sum(count == 1 for count in usage.values()),
        "candidate_count": len(candidates),
        "mapping_failures": sorted(set(mapping_failures)),
        "candidates": candidates,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

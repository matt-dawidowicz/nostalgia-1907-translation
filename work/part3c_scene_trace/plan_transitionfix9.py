#!/usr/bin/env python3
"""Find the lowest-growth original-width encoding for PART3C record 162."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
MES = HERE / "PART3C_ramprobe8.MES"
FONT = WORKSPACE / "outputs" / "PART3C_ramprobe8_fresh" / "FIX_CODE.FNT"
REPORT = HERE / "transitionfix9_plan.json"
GLYPH_BYTES = 18
WIDTH = 8
WORDS = tuple(
    "Admit you have lost your judgment, Kasuke. This is an enlightened age.".split()
)
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


@dataclass(frozen=True)
class Unit:
    """One rendered text unit and its current token, if already available."""

    text: str
    style: str
    bitmap: bytes
    token: bytes | None


def stored_unit(style: str, unit: str) -> bytes:
    """Render one generated glyph in the stored orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def tokenize(record: bytes) -> list[bytes]:
    """Split a null-terminated MES record into glyph/control tokens."""
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


def available_tokens(font: bytes, tail: bytes) -> dict[bytes, bytes]:
    """Map each available bitmap to its shortest token."""
    result: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        bitmap = font[start : start + GLYPH_BYTES]
        token = bytes((code,))
        if bitmap not in result or len(token) < len(result[bitmap]):
            result[bitmap] = token
    return result


def row_candidates(line: str, available: dict[bytes, bytes]) -> list[tuple[Unit, ...]]:
    """Enumerate non-dominated exact encodings of one row in eight cells."""
    states: dict[tuple[int, int, frozenset[bytes]], tuple[Unit, ...]] = {
        (0, 0, frozenset()): ()
    }
    while states:
        complete = [units for (position, _, _), units in states.items() if position == len(line)]
        if complete:
            break
        next_states: dict[tuple[int, int, frozenset[bytes]], tuple[Unit, ...]] = {}
        for (position, cells, missing), units in states.items():
            if position == len(line):
                next_states[(position, cells, missing)] = units
                continue
            if cells >= WIDTH:
                continue
            for size in (3, 2, 1):
                text = line[position : position + size]
                if len(text) != size:
                    continue
                seen: set[bytes] = set()
                for style in STYLES:
                    if style == "full" and len(text) != 1:
                        continue
                    try:
                        bitmap = stored_unit(style, text)
                    except ValueError:
                        continue
                    if bitmap in seen:
                        continue
                    seen.add(bitmap)
                    token = available.get(bitmap)
                    new_missing = missing if token is not None else missing | {bitmap}
                    unit = Unit(text, style, bitmap, token)
                    key = (position + size, cells + 1, new_missing)
                    candidate = units + (unit,)
                    previous = next_states.get(key)
                    if previous is None or sum(len(item.token or b"xx") for item in candidate) < sum(
                        len(item.token or b"xx") for item in previous
                    ):
                        next_states[key] = candidate
        # Retain only the best 20,000 states; score strongly favors fewer new bitmaps.
        if len(next_states) > 20000:
            ranked = sorted(
                next_states.items(),
                key=lambda item: (
                    len(item[0][2]),
                    item[0][1],
                    sum(len(unit.token or b"xx") for unit in item[1]),
                ),
            )[:20000]
            next_states = dict(ranked)
        states = next_states

    candidates = [
        units
        for (position, cells, _), units in states.items()
        if position == len(line) and cells <= WIDTH
    ]
    candidates.sort(
        key=lambda units: (
            len({unit.bitmap for unit in units if unit.token is None}),
            len(units),
            sum(len(unit.token or b"xx") for unit in units),
        )
    )
    return candidates[:256]


def main() -> None:
    """Choose a four-row word wrap and bitmap assignment."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    data = MES.read_bytes()
    info, pointers = parse_mes(data, MES)
    if not info.valid or info.pointer_count != 224:
        raise ValueError("invalid diagnostic MES")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    tail = data[info.split_offset :]
    font = FONT.read_bytes()
    available = available_tokens(font, tail)
    blank = available.get(bytes(GLYPH_BYTES))
    if blank is None:
        raise ValueError("no blank glyph is available")

    line_cache: dict[str, list[tuple[Unit, ...]]] = {}
    wraps: list[tuple[str, str, str, str]] = []
    for a in range(1, len(WORDS) - 2):
        for b in range(a + 1, len(WORDS) - 1):
            for c in range(b + 1, len(WORDS)):
                wrap = (
                    " ".join(WORDS[:a]),
                    " ".join(WORDS[a:b]),
                    " ".join(WORDS[b:c]),
                    " ".join(WORDS[c:]),
                )
                if all(len(line) <= 24 for line in wrap):
                    wraps.append(wrap)

    best: tuple[tuple[int, int, int], tuple[str, ...], tuple[tuple[Unit, ...], ...]] | None = None
    for wrap in wraps:
        choices = []
        possible = True
        for line in wrap:
            if line not in line_cache:
                line_cache[line] = row_candidates(line, available)
            if not line_cache[line]:
                possible = False
                break
            choices.append(line_cache[line][:64])
        if not possible:
            continue
        combined: list[tuple[tuple[Unit, ...], frozenset[bytes]]] = [((), frozenset())]
        for row_options in choices:
            next_combined: dict[frozenset[bytes], tuple[tuple[Unit, ...], ...]] = {}
            for built, missing in combined:
                for row in row_options:
                    row_missing = {unit.bitmap for unit in row if unit.token is None}
                    new_missing = missing | row_missing
                    candidate = built + (row,)
                    previous = next_combined.get(new_missing)
                    if previous is None or sum(len(item) for item in candidate) < sum(
                        len(item) for item in previous
                    ):
                        next_combined[new_missing] = candidate
            ranked = sorted(
                next_combined.items(),
                key=lambda item: (len(item[0]), sum(len(row) for row in item[1])),
            )[:2048]
            combined = [(built, missing) for missing, built in ranked]
        for built, missing in combined:
            record_bytes = sum(
                sum(len(unit.token or b"xx") for unit in row) + (WIDTH - len(row)) * len(blank)
                for row in built
            ) + 1
            score = (len(missing), record_bytes, sum(len(row) for row in built))
            if best is None or score < best[0]:
                best = (score, wrap, built)

    if best is None:
        raise ValueError("no four-row original-width encoding exists")
    score, wrap, rows = best
    missing_order: list[bytes] = []
    for row in rows:
        for unit in row:
            if unit.token is None and unit.bitmap not in missing_order:
                missing_order.append(unit.bitmap)
    assignments = {
        bitmap: encode_dynamic_index(len(tail) // GLYPH_BYTES + index)
        for index, bitmap in enumerate(missing_order)
    }
    encoded = bytearray()
    row_report = []
    for line, row in zip(wrap, rows):
        units_report = []
        for unit in row:
            token = unit.token or assignments[unit.bitmap]
            encoded.extend(token)
            units_report.append(
                {
                    "text": unit.text,
                    "style": unit.style,
                    "token": token.hex(" ").upper(),
                    "new": unit.token is None,
                }
            )
        padding = WIDTH - len(row)
        encoded.extend(blank * padding)
        row_report.append({"text": line, "units": units_report, "padding": padding})
    encoded.append(0)

    old_record = records[162]
    report = {
        "status": "PASS",
        "source_mes_size": len(data),
        "source_dynamic_glyphs": len(tail) // GLYPH_BYTES,
        "rows": row_report,
        "cells": WIDTH * 4,
        "new_unique_bitmaps": len(missing_order),
        "new_dynamic_glyphs": len(tail) // GLYPH_BYTES + len(missing_order),
        "source_record_size": len(old_record),
        "target_record_size": len(encoded),
        "projected_mes_size": len(data) - len(old_record) + len(encoded) + len(missing_order) * GLYPH_BYTES,
        "encoded_hex": encoded.hex(" ").upper(),
        "new_bitmap_hex": [bitmap.hex().upper() for bitmap in missing_order],
        "score": list(score),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

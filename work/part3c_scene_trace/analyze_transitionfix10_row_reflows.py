#!/usr/bin/env python3
"""Find same-width row reflows that retire one-use dynamic glyph slots."""

from __future__ import annotations

import itertools
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
REPORT = HERE / "transitionfix10_row_reflows.json"
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
    """Render one generated unit in stored orientation."""
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
    raise ValueError(f"invalid token {token.hex(' ')}")


def available_tokens(font: bytes, tail: bytes, excluded: set[int]) -> dict[bytes, bytes]:
    """Map bitmaps to shortest tokens, excluding retired dynamic slots."""
    result: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        if index in excluded:
            continue
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        result[font[start : start + GLYPH_BYTES]] = bytes((code,))
    return result


def encode_line(line: str, available: dict[bytes, bytes], width: int) -> list[dict[str, str]] | None:
    """Encode an exact prose line in no more than the original cell width."""
    @lru_cache(maxsize=None)
    def best(position: int, cells: int) -> tuple[tuple[str, str, bytes], ...] | None:
        if position == len(line):
            return ()
        if cells >= width:
            return None
        choices = []
        for size in (3, 2, 1):
            text = line[position : position + size]
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
                suffix = best(position + size, cells + 1)
                if suffix is not None:
                    choices.append(((text, style, token),) + suffix)
        if not choices:
            return None
        return min(
            choices,
            key=lambda choice: (
                len(choice),
                sum(len(item[2]) for item in choice),
                tuple(item[0] for item in choice),
            ),
        )

    result = best(0, 0)
    if result is None or len(result) > width:
        return None
    return [
        {"text": text, "style": style, "token": token.hex(" ").upper()}
        for text, style, token in result
    ]


def main() -> None:
    """Enumerate low-cost same-row, same-width retirement opportunities."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    data = MES.read_bytes()
    info, pointers = parse_mes(data, MES)
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    tail = data[info.split_offset :]
    font = FONT.read_bytes()
    entries = {
        int(item["segment"]): item
        for item in json.loads(CONFIG.read_text(encoding="utf-8"))["segments"]
    }

    usage: Counter[int] = Counter()
    for record in records:
        for token in tokenize(record):
            if len(token) == 2:
                index = dynamic_glyph_index(token[0], token[1])
                if index is not None:
                    usage[index] += 1

    blank = bytes(GLYPH_BYTES)
    candidates = []
    skipped_mapping = []
    for record_index, record in enumerate(records):
        if record_index in (159, 162):
            continue
        entry = entries.get(record_index)
        if entry is None:
            continue
        lines = str(entry["text"]).split("\n")
        config_units = list(entry["units"])
        if not lines or len(config_units) % len(lines):
            continue
        row_width = len(config_units) // len(lines)
        record_tokens = tokenize(record)
        if len(record_tokens) != len(config_units):
            continue
        current_bitmaps = [token_bitmap(token, font, tail) for token in record_tokens]
        config_bitmaps = [
            stored(str(item["style"]), str(item["unit"])) for item in config_units
        ]
        if current_bitmaps != config_bitmaps:
            skipped_mapping.append(record_index)
            continue
        for row, raw_line in enumerate(lines):
            start = row * row_width
            end = start + row_width
            row_tokens = record_tokens[start:end]
            unique = sorted(
                {
                    index
                    for token in row_tokens
                    if len(token) == 2
                    and (index := dynamic_glyph_index(token[0], token[1])) is not None
                    and usage[index] == 1
                }
            )
            if not unique:
                continue
            prose = raw_line.rstrip()
            if not prose:
                continue
            best_candidate = None
            for size in range(len(unique), 0, -1):
                for subset_tuple in itertools.combinations(unique, size):
                    subset = set(subset_tuple)
                    available = available_tokens(font, tail, subset)
                    blank_token = available.get(blank)
                    if blank_token is None:
                        continue
                    encoded = encode_line(prose, available, row_width)
                    if encoded is None:
                        continue
                    replacement_tokens = [
                        bytes.fromhex(item["token"]) for item in encoded
                    ] + [blank_token] * (row_width - len(encoded))
                    if any(
                        dynamic_glyph_index(token[0], token[1]) in subset
                        for token in replacement_tokens
                        if len(token) == 2
                    ):
                        continue
                    byte_delta = sum(map(len, replacement_tokens)) - sum(map(len, row_tokens))
                    candidate = {
                        "record": record_index,
                        "row": row,
                        "row_width": row_width,
                        "prose": prose,
                        "retired_dynamic_indexes": sorted(subset),
                        "retired_count": len(subset),
                        "byte_delta": byte_delta,
                        "source_hex": b"".join(row_tokens).hex(" ").upper(),
                        "replacement_hex": b"".join(replacement_tokens).hex(" ").upper(),
                        "units": encoded,
                        "padding": row_width - len(encoded),
                    }
                    if best_candidate is None or (
                        -candidate["retired_count"], candidate["byte_delta"]
                    ) < (-best_candidate["retired_count"], best_candidate["byte_delta"]):
                        best_candidate = candidate
                if best_candidate is not None:
                    break
            if best_candidate is not None:
                candidates.append(best_candidate)

    candidates.sort(
        key=lambda item: (
            float(item["byte_delta"]) / int(item["retired_count"]),
            int(item["byte_delta"]),
            -int(item["retired_count"]),
            int(item["record"]),
        )
    )
    report = {
        "status": "PASS",
        "candidate_count": len(candidates),
        "skipped_mapping": sorted(set(skipped_mapping)),
        "candidates": candidates,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

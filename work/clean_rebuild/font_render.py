#!/usr/bin/env python3
"""Render canonical English units as deterministic 12x12 game-font cells.

The renderer uses one-bit 12x12 glyphs stored in 18 bytes. A normal cell holds
one or two six-pixel English character slots; a small reviewed set of
three-character punctuation clusters can share a compact cell. Generated
bitmaps are prerotated into the orientation consumed by the Mega-CD renderer.

This module is deliberately unaware of MES indexes, SCN roles, and line
wrapping. ``mes_compiler.py`` chooses which source characters share cells and
deduplicates the resulting bitmaps. Unsupported characters fail explicitly
instead of being substituted.

See ``docs/BINARY_FORMATS.md`` for how fixed and dynamic font codes reference
these cells.
"""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PATTERN_PATH = HERE / "font_patterns.json"
GLYPH_WIDTH = 12
GLYPH_HEIGHT = 12
GLYPH_BYTES = 18


class FontError(ValueError):
    """Raised when source text cannot be represented by the canonical font."""


_PATTERN_DATA = json.loads(PATTERN_PATH.read_text(encoding="utf-8"))
CHARSET = str(_PATTERN_DATA["english_charset"])
PATTERNS: dict[str, list[str]] = _PATTERN_DATA["patterns"]


def _pattern(char: str) -> list[str]:
    """Return exact glyph art for a supported source character."""
    if char in PATTERNS:
        return PATTERNS[char]
    if char.isalpha() and char.upper() in PATTERNS:
        return PATTERNS[char.upper()]
    raise FontError(f"unsupported English glyph {char!r}")


def _matrix_bytes(matrix: list[list[int]]) -> bytes:
    """Pack a 12x12 one-bit matrix in row-major bit order."""
    if len(matrix) != GLYPH_HEIGHT or any(len(row) != GLYPH_WIDTH for row in matrix):
        raise FontError("glyph matrix is not 12x12")
    bits = [bit for row in matrix for bit in row]
    output = bytearray()
    for start in range(0, len(bits), 8):
        value = 0
        for bit in bits[start : start + 8]:
            value = value << 1 | bool(bit)
        output.append(value)
    return bytes(output)


def _bytes_matrix(data: bytes) -> list[list[int]]:
    """Unpack one native glyph into a 12x12 matrix."""
    if len(data) != GLYPH_BYTES:
        raise FontError(f"glyph is {len(data)} bytes, expected {GLYPH_BYTES}")
    bits = [
        (byte >> shift) & 1
        for byte in data
        for shift in range(7, -1, -1)
    ]
    return [
        bits[row * GLYPH_WIDTH : (row + 1) * GLYPH_WIDTH]
        for row in range(GLYPH_HEIGHT)
    ]


def prerotate_clockwise(data: bytes) -> bytes:
    """Apply the storage rotation expected by the Mega-CD renderer.

    Input and output are exact 12-by-12 one-bit cells encoded as 18 row-major
    bytes. The apparent clockwise transform compensates for the game's runtime
    tile orientation rather than changing visible text direction.
    """
    source = _bytes_matrix(data)
    rotated = [
        [source[GLYPH_HEIGHT - 1 - x][y] for x in range(GLYPH_WIDTH)]
        for y in range(GLYPH_HEIGHT)
    ]
    return _matrix_bytes(rotated)


def render_literal_cell(unit: str) -> bytes:
    """Render one or two literal six-pixel character slots in one cell.

    Spaces intentionally leave their half-cell blank. Unsupported characters
    and strings outside the one/two-character contract raise ``FontError``
    rather than substituting a glyph.
    """
    if not 1 <= len(unit) <= 2:
        raise FontError(f"literal cell must contain one or two characters: {unit!r}")
    matrix = [[0] * GLYPH_WIDTH for _ in range(GLYPH_HEIGHT)]
    for slot, char in enumerate(unit):
        if char == " ":
            continue
        pattern = _pattern(char)
        x_base = slot * 6
        for row_index, row in enumerate(pattern):
            y = 2 + row_index
            if y >= GLYPH_HEIGHT:
                break
            for column_index, value in enumerate(row):
                x = x_base + column_index
                if value in {"1", "#"} and x < GLYPH_WIDTH:
                    matrix[y][x] = 1
    return _matrix_bytes(matrix)


def stored_literal_cell(unit: str) -> bytes:
    """Render and prerotate a literal cell for direct MES storage."""
    return prerotate_clockwise(render_literal_cell(unit))


def _resample_row(row: str, width: int) -> str:
    """Narrow a bitmap row without discarding any occupied source column."""
    if len(row) <= width:
        return row
    output = ["0"] * width
    denominator = len(row) - 1
    for source_x, value in enumerate(row):
        if value not in {"1", "#"}:
            continue
        target_x = (source_x * (width - 1) + denominator // 2) // denominator
        output[target_x] = "1"
    return "".join(output)


def render_compact_cluster(unit: str) -> bytes:
    """Render a reviewed three-character punctuation cluster in one cell.

    Compact rendering is restricted to patterns recognized by the compiler so
    prose cannot be squeezed arbitrarily to evade layout or glyph limits.
    """
    if len(unit) != 3 or " " in unit or not any(char in ".'" for char in unit):
        raise FontError(f"unsupported compact punctuation cluster {unit!r}")
    patterns = [_pattern(char) for char in unit]
    widths = [max(len(row) for row in pattern) for pattern in patterns]
    gaps = [
        0 if unit[index] not in ".'" and unit[index + 1] in ".'" else 1
        for index in range(2)
    ]
    while sum(widths) + sum(gaps) > GLYPH_WIDTH:
        widest = max(widths)
        if widest <= 3:
            raise FontError(f"compact punctuation cluster does not fit: {unit!r}")
        widths[widths.index(widest)] -= 1
    matrix = [[0] * GLYPH_WIDTH for _ in range(GLYPH_HEIGHT)]
    x_base = 0
    for index, (pattern, width) in enumerate(zip(patterns, widths)):
        copied = [
            _resample_row(row, width) if len(row) != width else row
            for row in pattern
        ]
        for row_index, row in enumerate(copied):
            y = 2 + row_index
            if y >= GLYPH_HEIGHT:
                break
            for column_index, value in enumerate(row):
                x = x_base + column_index
                if value in {"1", "#"} and x < GLYPH_WIDTH:
                    matrix[y][x] = 1
        x_base += width
        if index < len(gaps):
            x_base += gaps[index]
    return _matrix_bytes(matrix)


def stored_cell(style: str, unit: str) -> bytes:
    """Render one canonical cell style in the game's stored orientation.

    ``style`` selects literal or reviewed compact rendering. Unknown styles are
    rejected so serialized font bytes always have an explicit compiler origin.
    """
    if style == "literal":
        glyph = render_literal_cell(unit)
    elif style == "compact":
        glyph = render_compact_cluster(unit)
    else:
        raise FontError(f"unknown cell style {style!r}")
    return prerotate_clockwise(glyph)


def validate_text(text: str) -> None:
    """Reject text that cannot be represented by the canonical font.

    Newlines are layout separators and are ignored. Every other character must
    have an exact source pattern; no lossy Unicode fallback is permitted.
    """
    unsupported = sorted({char for char in text if char not in CHARSET and char != "\n"})
    if unsupported:
        raise FontError(f"unsupported source characters: {unsupported}")

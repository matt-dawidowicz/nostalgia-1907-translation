#!/usr/bin/env python3
"""Render a transformed MES as readable, wrapped record pages for translation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_TOOLS = Path(
    r"C:\Users\thema\Documents\Codex\2026-07-12\i\outputs\nostalgia1907_tools"
)
sys.path.insert(0, str(PROJECT_TOOLS))

from mes_probe import (  # noqa: E402
    DYNAMIC_PREFIX_START,
    GLYPH_HEIGHT,
    GLYPH_WIDTH,
    dynamic_glyph_index,
    fixed_glyph_index,
    parse_mes,
    read_glyphs,
    segments_for,
)


def decode_cells(chunk: bytes, fixed: list[list[int]], dynamic: list[list[int]]) -> list[tuple[list[int] | None, str | None]]:
    """Decode one MES record into bitmap cells or labelled controls."""
    cells: list[tuple[list[int] | None, str | None]] = []
    pos = 0
    while pos < len(chunk):
        byte = chunk[pos]
        glyph = None
        label = None
        if byte == 0:
            label = "END"
            pos += 1
        elif byte == 0xEE:
            label = "EE"
            pos += 1
        elif byte >= DYNAMIC_PREFIX_START and pos + 1 < len(chunk):
            index = dynamic_glyph_index(byte, chunk[pos + 1])
            if index is not None and 0 <= index < len(dynamic):
                glyph = dynamic[index]
            else:
                label = f"{byte:02X}{chunk[pos + 1]:02X}"
            pos += 2
        elif byte >= 0xEF:
            label = f"{byte:02X}"
            pos += 1
        else:
            index = fixed_glyph_index(byte)
            if 0 <= index < len(fixed):
                glyph = fixed[index]
            else:
                label = f"{byte:02X}"
            pos += 1
        cells.append((glyph, label))
    return cells


def draw_glyph(draw: ImageDraw.ImageDraw, glyph: list[int], x0: int, y0: int, scale: int) -> None:
    """Draw one 12x12 monochrome glyph."""
    for y in range(GLYPH_HEIGHT):
        for x in range(GLYPH_WIDTH):
            if glyph[y * GLYPH_WIDTH + x]:
                draw.rectangle(
                    (x0 + x * scale, y0 + y * scale, x0 + (x + 1) * scale - 1, y0 + (y + 1) * scale - 1),
                    fill="black",
                )


def render(mes_path: Path, font_path: Path, output: Path, start: int, end: int, columns: int, scale: int) -> None:
    """Render inclusive record range with long records wrapped across rows."""
    data = mes_path.read_bytes()
    info, pointers = parse_mes(data, mes_path)
    if not info.valid:
        raise ValueError(f"invalid MES: {mes_path}")
    segments = segments_for(data, pointers, info.split_offset)
    if start < 0 or end < start or end >= len(segments):
        raise ValueError(f"invalid record range {start}-{end} for {len(segments)} records")
    fixed = read_glyphs(font_path.read_bytes())
    dynamic = read_glyphs(data[info.split_offset:])
    cell_w = GLYPH_WIDTH * scale
    cell_h = GLYPH_HEIGHT * scale
    label_w = 92
    row_gap = 4
    record_gap = 10
    decoded: list[tuple[int, int, list[tuple[list[int] | None, str | None]]]] = []
    height = 12
    for segment in segments[start : end + 1]:
        chunk = data[segment.offset : segment.offset + segment.size]
        cells = decode_cells(chunk, fixed, dynamic)
        rows = max(1, (len(cells) + columns - 1) // columns)
        decoded.append((segment.index, segment.offset, cells))
        height += rows * (cell_h + row_gap) + record_gap
    width = label_w + columns * cell_w + 16
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = 8
    for index, offset, cells in decoded:
        draw.text((6, y + 7), f"{index:03d}@{offset:04X}", fill=(70, 70, 70))
        for pos, (glyph, label) in enumerate(cells):
            row, column = divmod(pos, columns)
            x = label_w + column * cell_w
            yy = y + row * (cell_h + row_gap)
            if glyph is not None:
                draw_glyph(draw, glyph, x, yy, scale)
            else:
                draw.rectangle((x, yy, x + cell_w - 1, yy + cell_h - 1), outline=(190, 0, 0))
                draw.text((x + 1, yy + max(0, cell_h // 2 - 4)), label or "?", fill=(170, 0, 0))
        rows = max(1, (len(cells) + columns - 1) // columns)
        y += rows * (cell_h + row_gap) + record_gap
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mes", type=Path)
    parser.add_argument("font", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--columns", type=int, default=32)
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()
    render(args.mes, args.font, args.output, args.start, args.end, args.columns, args.scale)


if __name__ == "__main__":
    main()

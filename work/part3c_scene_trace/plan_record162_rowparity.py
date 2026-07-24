#!/usr/bin/env python3
"""Plan an exact-prose four-row encoding for PART3C record 162."""

from __future__ import annotations

import json
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
MES = HERE / "PART3C_boundarypadfix5.MES"
FONT = HERE / "FIX_CODE_boundarypadfix5.FNT"
ORIGINAL_FONT = HERE.parent / "part3c_original_compare" / "original_extract" / "FIX_CODE.FNT"
REGRESSION = HERE.parents[1] / "outputs" / "PART3C_boundarypadfix5_fresh" / "regression_full"
REPORT = HERE / "record162_rowparity_plan.json"
GLYPH_BYTES = 18
TARGET_LINES = (
    "Admit you have lost",
    "your judgment,",
    "Kasuke. This is an",
    "enlightened age.",
)

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


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Return MES bytes, parsed info, records, and dynamic tail."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid:
        raise ValueError(f"invalid MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def bitmap_tokens(font: bytes, tail: bytes) -> dict[bytes, bytes]:
    """Map each stored bitmap to its shortest current token."""
    result: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        result[font[start : start + GLYPH_BYTES]] = bytes((code,))
    return result


def stored_unit(unit: str, style: str = "packed") -> bytes:
    """Render one generated unit in stored prerotated orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def encode_line_from_existing(
    line: str, available: dict[bytes, bytes]
) -> list[dict[str, str]] | None:
    """Return the fewest existing bitmap tokens that exactly spell one line."""
    styles = ("packed", "packed-compact", "packed-literal", "full")

    @lru_cache(maxsize=None)
    def best(position: int) -> tuple[dict[str, str], ...] | None:
        if position == len(line):
            return ()
        choices: list[tuple[dict[str, str], ...]] = []
        for size in (3, 2, 1):
            unit = line[position : position + size]
            if len(unit) != size:
                continue
            for style in styles:
                try:
                    rendered = stored_unit(unit, style)
                except ValueError:
                    continue
                token = available.get(rendered)
                if token is None:
                    continue
                suffix = best(position + size)
                if suffix is None:
                    continue
                choices.append(
                    (
                        {
                            "style": style,
                            "unit": unit,
                            "token": token.hex(" ").upper(),
                        },
                    )
                    + suffix
                )
        if not choices:
            return None
        return min(
            choices,
            key=lambda choice: (
                len(choice),
                sum(len(bytes.fromhex(item["token"])) for item in choice),
                tuple(item["unit"] for item in choice),
            ),
        )

    result = best(0)
    return list(result) if result is not None else None


def fixed_usage(path: Path) -> Counter[int]:
    """Count one-byte fixed glyph references in one MES."""
    _, _, records, _ = load_mes(path)
    usage: Counter[int] = Counter()
    for record in records:
        offset = 0
        while offset < len(record):
            value = record[offset]
            if value == 0:
                offset += 1
            elif value in (0xF0, 0xF1):
                offset += 2
            else:
                if 1 <= value <= 0xED:
                    usage[value] += 1
                offset += 1
    return usage


def main() -> None:
    """Write a no-mutation encoding plan."""
    _, info, records, tail = load_mes(MES)
    font = FONT.read_bytes()
    available = bitmap_tokens(font, tail)
    units: list[str] = []
    rows: list[dict[str, object]] = []
    for line in TARGET_LINES:
        packed = pack_text_pairs(line)
        if len(packed) > 8:
            raise ValueError(f"line does not fit eight cells: {line!r}")
        padded = packed + ["  "] * (8 - len(packed))
        units.extend(padded)
        rows.append({"text": line, "content_units": packed, "padded_units": padded})
    missing = Counter(unit for unit in units if stored_unit(unit) not in available)
    phrase = " ".join(TARGET_LINES)
    words = phrase.split()
    exact_existing_wraps_by_width: dict[int, list[list[dict[str, object]]]] = {}
    for row_width in (8, 9, 10):
        exact_existing_wraps: list[list[dict[str, object]]] = []

        def visit_existing(start: int, built: list[dict[str, object]]) -> None:
            """Enumerate four-row wraps using only already stored bitmaps."""
            if len(built) > 4:
                return
            if start == len(words):
                if len(built) == 4:
                    exact_existing_wraps.append(built)
                return
            for end in range(start + 1, len(words) + 1):
                line = " ".join(words[start:end])
                encoded_units = encode_line_from_existing(line, available)
                if encoded_units is None or len(encoded_units) > row_width:
                    continue
                visit_existing(
                    end,
                    built
                    + [
                        {
                            "text": line,
                            "cell_count": len(encoded_units),
                            "units": encoded_units,
                        }
                    ],
                )

        visit_existing(0, [])
        exact_existing_wraps.sort(
            key=lambda wrap: (
                sum(int(row["cell_count"]) for row in wrap),
                sum(
                    len(bytes.fromhex(unit["token"]))
                    for row in wrap
                    for unit in row["units"]
                ),
            )
        )
        exact_existing_wraps_by_width[row_width] = exact_existing_wraps
    disc_usage: Counter[int] = Counter()
    chapter_names = {
        "START", "PART1A", "PART1B", "PART1C", "PART1D", "PART2A",
        "PART2B", "PART2C", "PART2D", "PART2E", "PART2F", "PART3A",
        "PART3B", "PART3B_", "PART3C", "PART4A", "PART4B", "PART4C",
        "STAFF",
    }
    audited_mes: list[str] = []
    for path in sorted(REGRESSION.glob("*/*.MES.unpacked")):
        if path.parent.name not in chapter_names:
            continue
        disc_usage.update(fixed_usage(path))
        audited_mes.append(str(path.relative_to(REGRESSION)))
    original_font = ORIGINAL_FONT.read_bytes()
    unused_codes = []
    for code in range(1, 0xEE):
        if disc_usage[code]:
            continue
        start = (code - 1) * GLYPH_BYTES
        unused_codes.append(
            {
                "code": f"0x{code:02X}",
                "original_blank": not any(original_font[start : start + GLYPH_BYTES]),
                "current_blank": not any(font[start : start + GLYPH_BYTES]),
            }
        )
    encoded = b"".join(
        available.get(stored_unit(unit), b"") for unit in units
    )
    report = {
        "source_mes_size": len(MES.read_bytes()),
        "source_split": info.split_offset,
        "source_record_162_size": len(records[162]),
        "target_phrase": phrase,
        "target_rows": rows,
        "target_cell_count": len(units),
        "missing_units": dict(sorted(missing.items())),
        "all_bitmaps_already_available": not missing,
        "four_row_existing_bitmap_wraps_by_width": {
            str(width): {
                "count": len(wraps),
                "best": wraps[:5],
            }
            for width, wraps in exact_existing_wraps_by_width.items()
        },
        "audited_mes_count": len(audited_mes),
        "globally_unused_fixed_codes": unused_codes,
        "encoded_size_if_available": len(encoded) + 1 if not missing else None,
        "encoded_hex_if_available": (
            (encoded + b"\0").hex(" ").upper() if not missing else None
        ),
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

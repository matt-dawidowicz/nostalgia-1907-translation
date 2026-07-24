#!/usr/bin/env python3
"""Rebuild PART3C records 115-120 with the working stream's cell boundaries."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
BASE = WORKSPACE / "outputs" / "PART3C_globalfontfix3_fresh"
ORIGINAL = WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
SCN_PATH = ORIGINAL / "000_PART3C.SCN.unpacked"
BASE_MES = BASE / "PART3C.MES"
GLOBAL_FONT = BASE / "FIX_CODE.FNT"
OUTPUT_MES = HERE / "PART3C_cursorparityfix4.MES"
REPORT = HERE / "cursor_parity_report.json"

GLYPH_BYTES = 18
POINTER_COUNT = 224
TEXT_BOUNDARY_LIMIT = 0x2600
TARGET_COUNTS = {115: 16, 116: 5, 117: 12, 118: 10, 119: 20, 120: 7}

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    parse_mes,
    rebuild_mes_segments,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def load_records(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid PART3C MES and split it into records."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def tokens(record: bytes) -> list[bytes]:
    """Tokenize one terminated MES record."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    result: list[bytes] = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        token = record[offset : offset + width]
        if len(token) != width or offset + width > len(record) - 1:
            raise ValueError("incomplete MES token")
        result.append(token)
        offset += width
    return result


def glyph_bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    """Resolve one text token to its exact bitmap."""
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


def glyph_tokens(record: bytes, font: bytes, tail: bytes) -> list[bytes]:
    """Return only tokens that resolve to glyph cells."""
    return [token for token in tokens(record) if glyph_bitmap(token, font, tail) is not None]


def build_bitmap_map(font: bytes, tail: bytes) -> dict[bytes, bytes]:
    """Map available bitmaps to a preferred fixed or dynamic token."""
    result: dict[bytes, bytes] = {}
    dynamic_count = len(tail) // GLYPH_BYTES
    for index in range(dynamic_count):
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        result[font[start : start + GLYPH_BYTES]] = bytes((code,))
    return result


def render_unit(style: str, unit: str) -> bytes:
    """Render one target unit in the stored PART3C bitmap orientation."""
    return transform_glyph_bytes(
        render_generated_unit(style, unit),
        "prerot-cw",
    )


def main() -> None:
    """Build the cursor-parity MES and emit its structural proof."""
    HERE.mkdir(parents=True, exist_ok=True)
    for path in (OUTPUT_MES, REPORT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    base_data, base_info, base_records, base_tail = load_records(BASE_MES)
    original_data, _, original_records, _ = load_records(
        ORIGINAL / "001_PART3C.MES.unpacked"
    )
    font = GLOBAL_FONT.read_bytes()
    if len(base_tail) % GLYPH_BYTES:
        raise ValueError("base dynamic glyph tail is misaligned")
    bitmap_map = build_bitmap_map(font, base_tail)
    extended_tail = bytearray(base_tail)
    added_units: list[dict[str, object]] = []

    def unit_token(style: str, unit: str) -> bytes:
        """Resolve or append one exact rendered glyph."""
        rendered = render_unit(style, unit)
        existing = bitmap_map.get(rendered)
        if existing is not None:
            return existing
        index = len(extended_tail) // GLYPH_BYTES
        token = encode_dynamic_index(index)
        extended_tail.extend(rendered)
        bitmap_map[rendered] = token
        added_units.append(
            {
                "style": style,
                "unit": unit,
                "dynamic_index": index,
                "token": token.hex().upper(),
                "bitmap_sha256": digest(rendered),
            }
        )
        return token

    blank = bitmap_map.get(bytes(GLYPH_BYTES))
    if blank is None or len(blank) != 1:
        raise ValueError("global fixed font has no one-byte blank glyph")

    base_glyphs = {
        index: glyph_tokens(base_records[index], font, base_tail)
        for index in TARGET_COUNTS
    }
    replacements: dict[int, bytes] = {}
    expected_units: dict[int, list[tuple[str, str]]] = {}

    replacements[115] = b"".join(base_glyphs[115] + [blank] * 6) + b"\x00"
    expected_units[115] = []

    replacements[116] = b"".join(base_glyphs[116][:5]) + b"\x00"
    expected_units[116] = []

    target_117 = [
        ("packed-literal", "Tr"),
        ("packed-literal", "y "),
        ("packed-literal", "an"),
        ("packed-literal", "y "),
        ("packed-literal", "li"),
        ("packed-literal", "tt"),
        ("packed-literal", "le"),
        ("packed-literal", " t"),
        ("packed-literal", "ri"),
        ("packed-literal", "ck"),
        ("packed", "..."),
    ]
    replacements[117] = (
        b"".join(unit_token(style, unit) for style, unit in target_117)
        + blank
        + b"\x00"
    )
    expected_units[117] = target_117

    target_118 = [
        ("packed-literal", "I'"),
        ("packed-literal", "ll"),
        ("packed-literal", " s"),
        ("packed-literal", "na"),
        ("packed-literal", "p "),
        ("packed-literal", "yo"),
        ("packed-literal", "ur"),
        ("packed-literal", " n"),
        ("packed-literal", "ec"),
        ("packed-literal", "k!"),
    ]
    replacements[118] = (
        b"".join(unit_token(style, unit) for style, unit in target_118) + b"\x00"
    )
    expected_units[118] = target_118

    target_119 = [
        ("packed-literal", "En"),
        ("packed-literal", "ou"),
        ("packed-literal", "gh"),
        ("packed-literal", "! "),
        ("packed-literal", "I "),
        ("packed-literal", "wi"),
        ("packed-literal", "ll"),
        ("packed-literal", " k"),
        ("packed-literal", "il"),
        ("packed-literal", "l "),
        ("packed-literal", "yo"),
        ("packed-literal", "u!"),
    ]
    replacements[119] = (
        b"".join(unit_token(style, unit) for style, unit in target_119)
        + blank * 8
        + b"\x00"
    )
    expected_units[119] = target_119

    replacements[120] = b"".join(base_glyphs[120][:7]) + b"\x00"
    expected_units[120] = []

    temporary = HERE / "PART3C_cursorparityfix4.tmp.MES"
    if temporary.exists():
        raise FileExistsError(f"refusing to overwrite {temporary}")
    rebuild_mes_segments(BASE_MES, temporary, replacements)
    temporary_data = temporary.read_bytes()
    temporary_info, _ = parse_mes(temporary_data, temporary)
    output_data = temporary_data + bytes(extended_tail[len(base_tail) :])
    temporary.replace(OUTPUT_MES)
    if len(extended_tail) != len(base_tail):
        OUTPUT_MES.write_bytes(output_data)

    final_data, final_info, final_records, final_tail = load_records(OUTPUT_MES)
    if final_info.split_offset != temporary_info.split_offset:
        raise ValueError("appending dynamic glyphs changed the text split")
    if final_info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError("cursor-parity text split exceeds the 0x2600 boundary")
    if not final_tail.startswith(base_tail):
        raise ValueError("existing dynamic glyph tail changed")

    final_counts = {
        index: len(glyph_tokens(final_records[index], font, final_tail))
        for index in TARGET_COUNTS
    }
    original_counts = {
        index: len(tokens(original_records[index])) for index in TARGET_COUNTS
    }
    if original_counts != TARGET_COUNTS:
        raise ValueError(f"working Japanese cell contract changed: {original_counts}")
    if final_counts != TARGET_COUNTS:
        raise ValueError(f"cursor-parity cell contract failed: {final_counts}")

    for index, units in expected_units.items():
        if not units:
            continue
        actual = [
            glyph_bitmap(token, font, final_tail)
            for token in glyph_tokens(final_records[index], font, final_tail)
        ]
        visible = len(units)
        expected = [render_unit(style, unit) for style, unit in units]
        if actual[:visible] != expected:
            raise ValueError(f"record {index} rendered units differ")
        if any(value != bytes(GLYPH_BYTES) for value in actual[visible:]):
            raise ValueError(f"record {index} padding is not blank")

    for index, (before, after) in enumerate(zip(base_records, final_records)):
        if index not in replacements and before != after:
            raise ValueError(f"non-target record {index} changed")

    scn = SCN_PATH.read_bytes()
    expected_chain = {
        0x823: bytes.fromhex("21 00 31 00 74"),
        0x82B: bytes.fromhex("21 00 75 00 00"),
        0x833: bytes.fromhex("21 00 76 00 00"),
        0x83B: bytes.fromhex("21 00 77 00 00"),
        0x843: bytes.fromhex("21 00 78 00 00"),
        0x849: bytes.fromhex("24 0F 14 0E 0C 27 00 79"),
    }
    for offset, command in expected_chain.items():
        if scn[offset : offset + len(command)] != command:
            raise ValueError(f"SCN cursor chain changed at 0x{offset:X}")

    report = {
        "status": "PASS",
        "root_cause": (
            "SCN renders record 115 followed by continuation records 116-119 "
            "through one shared text cursor; per-record padding did not preserve "
            "the working stream's cumulative cell boundaries."
        ),
        "base_mes": {
            "size": len(base_data),
            "sha256": digest(base_data),
            "split_offset": base_info.split_offset,
        },
        "output_mes": {
            "path": str(OUTPUT_MES),
            "size": len(final_data),
            "sha256": digest(final_data),
            "split_offset": final_info.split_offset,
            "split_offset_hex": f"0x{final_info.split_offset:X}",
            "text_headroom": TEXT_BOUNDARY_LIMIT - final_info.split_offset,
            "dynamic_glyph_count": len(final_tail) // GLYPH_BYTES,
            "added_dynamic_glyphs": added_units,
        },
        "scn_cursor_chain": [
            {
                "offset": offset,
                "offset_hex": f"0x{offset:X}",
                "bytes": command.hex(" ").upper(),
            }
            for offset, command in expected_chain.items()
        ],
        "cell_contract": {
            "working_japanese": original_counts,
            "previous_translation": {
                index: len(base_glyphs[index]) for index in TARGET_COUNTS
            },
            "cursor_parity_translation": final_counts,
            "exact_match": True,
        },
        "visible_text": {
            "115": "That is absurd...",
            "116": "Pathetic.",
            "117": "Try any little trick...",
            "118": "I'll snap your neck!",
            "119": "Enough! I will kill you!",
            "120": "He is huge...",
        },
        "wording_change": {
            "record": 118,
            "before": "...and I will snap your neck!",
            "after": "I'll snap your neck!",
            "reason": "The working continuation slot is exactly 10 glyph cells.",
        },
        "non_target_records_byte_identical": True,
        "global_font_changed": False,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

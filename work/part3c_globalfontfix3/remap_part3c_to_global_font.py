#!/usr/bin/env python3
"""Remap corrected PART3C fixed codes onto the proven global visualfix3 font."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
V4 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
SOURCE_MES = V4 / "PART3C.MES"
SOURCE_FONT = V4 / "FIX_CODE.FNT"
GLOBAL_FONT = V3 / "FIX_CODE.FNT"
CONFIG_PATH = V4 / "PART3C_000_223_visualfix4_build_config.json"
OUTPUT_MES = HERE / "PART3C_globalfontfix3.MES"
REPORT = HERE / "font_remap_report.json"

POINTER_COUNT = 224
GLYPH_BYTES = 18
TEXT_BOUNDARY_LIMIT = 0x2600
UNTRANSLATED_RECORD = 158

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def load_records(path: Path) -> tuple[bytes, object, list[object]]:
    """Read one valid 224-entry MES and its record spans."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    return data, info, segments_for(data, pointers, info.split_offset)


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
    """Resolve a glyph token to its exact bitmap."""
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


def main() -> None:
    """Perform a width-preserving bitmap-identity fixed-code remap."""
    HERE.mkdir(parents=True, exist_ok=True)
    for path in (OUTPUT_MES, REPORT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    source_data, source_info, spans = load_records(SOURCE_MES)
    v3_data, v3_info, v3_spans = load_records(V3 / "PART3C.MES")
    if source_info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError("source text split exceeds the guarded boundary")

    source_font = SOURCE_FONT.read_bytes()
    global_font = GLOBAL_FONT.read_bytes()
    if len(source_font) != len(global_font) or len(global_font) % GLYPH_BYTES:
        raise ValueError("fixed-font sizes are incompatible")

    global_codes: dict[bytes, list[int]] = defaultdict(list)
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        global_codes[global_font[start : start + GLYPH_BYTES]].append(code)

    used_source_codes: Counter[int] = Counter()
    code_map: dict[int, int] = {}
    missing: dict[int, str] = {}
    for index, span in enumerate(spans):
        if index == UNTRANSLATED_RECORD:
            continue
        record = source_data[span.offset : span.offset + span.size]
        for token in tokens(record):
            if len(token) != 1 or not 1 <= token[0] <= 0xED:
                continue
            old_code = token[0]
            used_source_codes[old_code] += 1
            start = (old_code - 1) * GLYPH_BYTES
            bitmap = source_font[start : start + GLYPH_BYTES]
            candidates = global_codes.get(bitmap)
            if not candidates:
                missing[old_code] = digest(bitmap)
                continue
            code_map[old_code] = candidates[0]
    if missing:
        raise ValueError(f"global font lacks used PART3C bitmaps: {missing}")

    output = bytearray(source_data)
    replaced_occurrences = 0
    unchanged_occurrences = 0
    per_record_changes: dict[int, int] = {}
    for index, span in enumerate(spans):
        if index == UNTRANSLATED_RECORD:
            continue
        record = source_data[span.offset : span.offset + span.size]
        offset = 0
        changes = 0
        while offset < len(record) - 1:
            value = record[offset]
            if value >= 0xF0:
                offset += 2
                continue
            if 1 <= value <= 0xED:
                replacement = code_map[value]
                output[span.offset + offset] = replacement
                if replacement == value:
                    unchanged_occurrences += 1
                else:
                    replaced_occurrences += 1
                    changes += 1
            offset += 1
        if changes:
            per_record_changes[index] = changes

    output_data = bytes(output)
    output_info, output_pointers = parse_mes(output_data, OUTPUT_MES)
    if not output_info.valid or output_info.split_offset != source_info.split_offset:
        raise ValueError("remap changed MES structure")
    output_spans = segments_for(
        output_data, output_pointers, output_info.split_offset
    )
    if output_data[output_info.split_offset :] != source_data[source_info.split_offset :]:
        raise ValueError("remap changed the dynamic glyph tail")
    if output_data[: 4 + POINTER_COUNT * 2] != source_data[: 4 + POINTER_COUNT * 2]:
        raise ValueError("remap changed the MES pointer table")
    v3_record_158 = v3_data[
        v3_spans[UNTRANSLATED_RECORD].offset :
        v3_spans[UNTRANSLATED_RECORD].offset + v3_spans[UNTRANSLATED_RECORD].size
    ]
    output_record_158 = output_data[
        output_spans[UNTRANSLATED_RECORD].offset :
        output_spans[UNTRANSLATED_RECORD].offset
        + output_spans[UNTRANSLATED_RECORD].size
    ]
    if output_record_158 != v3_record_158:
        raise ValueError("untranslated record 158 changed")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    manifest = {int(entry["segment"]): entry for entry in config["segments"]}
    checked_units = 0
    for index, entry in manifest.items():
        span = output_spans[index]
        record = output_data[span.offset : span.offset + span.size]
        glyph_tokens = [
            token
            for token in tokens(record)
            if glyph_bitmap(
                token,
                global_font,
                output_data[output_info.split_offset :],
            )
            is not None
        ]
        units = entry["units"]
        if len(glyph_tokens) != len(units):
            raise ValueError(
                f"record {index} glyph/unit mismatch: "
                f"{len(glyph_tokens)} != {len(units)}"
            )
        for position, (token, unit) in enumerate(zip(glyph_tokens, units)):
            expected = transform_glyph_bytes(
                render_generated_unit(str(unit["style"]), str(unit["unit"])),
                str(config["glyph_transform"]),
            )
            actual = glyph_bitmap(
                token,
                global_font,
                output_data[output_info.split_offset :],
            )
            if actual != expected:
                raise ValueError(
                    f"bitmap mismatch after remap: record {index}, "
                    f"glyph {position}, unit={unit['unit']!r}"
                )
            checked_units += 1

    OUTPUT_MES.write_bytes(output_data)
    report = {
        "status": "PASS",
        "source_mes": {
            "size": len(source_data),
            "sha256": digest(source_data),
            "split_offset": source_info.split_offset,
        },
        "output_mes": {
            "path": str(OUTPUT_MES),
            "size": len(output_data),
            "sha256": digest(output_data),
            "split_offset": output_info.split_offset,
            "text_headroom": TEXT_BOUNDARY_LIMIT - output_info.split_offset,
        },
        "font_contract": {
            "source_part3c_font_sha256": digest(source_font),
            "global_visualfix3_font_sha256": digest(global_font),
            "used_source_fixed_codes": len(used_source_codes),
            "mapped_fixed_codes": len(code_map),
            "missing_bitmaps": len(missing),
            "replaced_fixed_code_occurrences": replaced_occurrences,
            "unchanged_fixed_code_occurrences": unchanged_occurrences,
            "records_with_code_changes": len(per_record_changes),
            "checked_manifest_glyph_occurrences": checked_units,
            "bitmap_mismatches": 0,
        },
        "structure_contract": {
            "pointer_table_byte_identical": True,
            "record_sizes_byte_identical": True,
            "dynamic_tail_byte_identical": True,
            "untranslated_record_158_byte_identical_to_visualfix3": True,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

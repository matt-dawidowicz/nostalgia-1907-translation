#!/usr/bin/env python3
"""Build a padded, render-equivalent PART3C MES below the 0x4000 boundary."""

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
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
V4 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
SOURCE_MES = HERE.parent / "part3c_globalfontfix3" / "PART3C_globalfontfix3.MES"
SOURCE_FONT = V3 / "FIX_CODE.FNT"
V3_MES = V3 / "PART3C.MES"
CONFIG = V4 / "PART3C_000_223_visualfix4_build_config.json"
PHASE_REPORT = (
    PROJECT
    / "work"
    / "nostalgia1907"
    / "part3c_blackoutfix"
    / "phase_compaction_analysis.json"
)
OUTPUT_MES = HERE / "PART3C_boundarypadfix5.MES"
OUTPUT_FONT = HERE / "FIX_CODE_boundarypadfix5.FNT"
REPORT = HERE / "boundarypad_compaction_report.json"

GLYPH_BYTES = 18
POINTER_COUNT = 224
WHOLE_MES_LIMIT = 0x3FFF
TEXT_SPLIT_LIMIT = 0x2600
MINIMUM_V3_SAVING = 0x1E6
RECYCLED_SPILL_CODES = (0x48, 0xBC)

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid 224-record MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def tokens(record: bytes) -> list[bytes]:
    """Tokenize one null-terminated MES record."""
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


def bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    """Resolve a token to its exact stored glyph bitmap, if it is a glyph."""
    if len(token) == 1 and 1 <= token[0] <= 0xED:
        start = (token[0] - 1) * GLYPH_BYTES
        return font[start : start + GLYPH_BYTES]
    if len(token) == 2:
        index = dynamic_glyph_index(token[0], token[1])
        if index is None:
            return None
        start = index * GLYPH_BYTES
        value = tail[start : start + GLYPH_BYTES]
        if len(value) != GLYPH_BYTES:
            raise ValueError(f"dynamic glyph {index} is outside the tail")
        return value
    return None


def controls(record: bytes, font: bytes, tail: bytes) -> list[bytes]:
    """Return non-glyph tokens and the terminator in original order."""
    result = [token for token in tokens(record) if bitmap(token, font, tail) is None]
    result.append(b"\x00")
    return result


def preferred_bitmap_tokens(
    font: bytes, tail: bytes, excluded_fixed_codes: set[int]
) -> dict[bytes, bytes]:
    """Map each available bitmap to its shortest existing token."""
    result: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        if code in excluded_fixed_codes:
            continue
        start = (code - 1) * GLYPH_BYTES
        result[font[start : start + GLYPH_BYTES]] = bytes((code,))
    return result


def render_unit(style: str, unit: str) -> bytes:
    """Render one packed unit in stored prerotated orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def build_mes(records: list[bytes], tail: bytes) -> bytes:
    """Serialize records and a dynamic tail with fresh monotonic pointers."""
    table_size = 2 + len(records) * 2
    split = table_size + sum(map(len, records))
    result = bytearray(split + len(tail))
    result[:2] = split.to_bytes(2, "big")
    cursor = table_size
    for index, record in enumerate(records):
        result[2 + index * 2 : 4 + index * 2] = cursor.to_bytes(2, "big")
        result[cursor : cursor + len(record)] = record
        cursor += len(record)
    result[split:] = tail
    return bytes(result)


def main() -> None:
    """Apply safe phase, blank-suffix, and exact-bitmap compaction."""
    for path in (OUTPUT_MES, OUTPUT_FONT, REPORT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    source, source_info, source_records, source_tail = load_mes(SOURCE_MES)
    font = SOURCE_FONT.read_bytes()
    if len(source_tail) % GLYPH_BYTES:
        raise ValueError("source dynamic tail is not glyph aligned")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    entries = {int(item["segment"]): item for item in config["segments"]}
    fixed_windows = set(config["scn_fixed_window_padding"]["segments"])
    forced_padding = set(config["profile_forced_final_row_padding"]["segments"])
    protected = fixed_windows | forced_padding
    phase_data = json.loads(PHASE_REPORT.read_text(encoding="utf-8"))
    if phase_data["unmatched"]:
        raise ValueError("phase analysis contains unmatched rows")

    recycled_codes = set(RECYCLED_SPILL_CODES)
    available = preferred_bitmap_tokens(font, source_tail, recycled_codes)
    phase_records = list(source_records)
    phase_saving = 0
    phase_rows: list[dict[str, int]] = []
    phase_segments: set[int] = set()
    used_ranges: dict[int, list[tuple[int, int]]] = {}
    for candidate in phase_data["candidates"]:
        segment = int(candidate["segment"])
        entry = entries.get(segment)
        if entry is None:
            continue
        final_row = str(entry["text"]).count("\n")
        if segment in protected and int(candidate["row"]) >= final_row:
            continue
        start = int(candidate["unit_start"])
        end = int(candidate["unit_end"])
        current_units = [
            (str(item["style"]), str(item["unit"]))
            for item in entry["units"][start:end]
        ]
        expected_current = [tuple(item) for item in candidate["current_units"]]
        if current_units != expected_current:
            continue
        candidate_units = [tuple(item) for item in candidate["candidate_units"]]
        if len(candidate_units) != end - start:
            raise ValueError(f"phase candidate changes cell count at record {segment}")
        current_text = "".join(unit for _, unit in current_units)
        candidate_text = "".join(unit for _, unit in candidate_units)
        prose_matches = current_text.strip() == candidate_text.strip()
        if not prose_matches:
            raise ValueError(f"phase candidate changes prose at record {segment}")
        ranges = used_ranges.setdefault(segment, [])
        if any(start < old_end and end > old_start for old_start, old_end in ranges):
            raise ValueError(f"overlapping phase candidates at record {segment}")

        record_tokens = tokens(phase_records[segment])
        if len(record_tokens) != len(entry["units"]):
            raise ValueError(f"record/config cell mismatch at record {segment}")
        replacement = []
        for style, unit in candidate_units:
            token = available.get(render_unit(style, unit))
            if token is None:
                raise ValueError(
                    f"phase candidate uses unavailable bitmap at record {segment}: {unit!r}"
                )
            replacement.append(token)
        old_bytes = sum(len(token) for token in record_tokens[start:end])
        new_bytes = sum(len(token) for token in replacement)
        if new_bytes >= old_bytes:
            continue
        record_tokens[start:end] = replacement
        phase_records[segment] = b"".join(record_tokens) + b"\x00"
        saving = old_bytes - new_bytes
        phase_saving += saving
        phase_rows.append(
            {"segment": segment, "row": int(candidate["row"]), "saving": saving}
        )
        phase_segments.add(segment)
        ranges.append((start, end))

    blank = bytes(GLYPH_BYTES)
    trimmed_records: list[bytes] = []
    trailing_saving = 0
    trimmed_counts: Counter[int] = Counter()
    for index, record in enumerate(phase_records):
        record_tokens = tokens(record)
        removed = 0
        if index not in protected and index in entries:
            while record_tokens and bitmap(record_tokens[-1], font, source_tail) == blank:
                removed += len(record_tokens.pop())
        trimmed_records.append(b"".join(record_tokens) + b"\x00")
        if removed:
            trailing_saving += removed
            trimmed_counts[index] = removed

    if any(
        len(token) == 1 and token[0] in recycled_codes
        for record in trimmed_records
        for token in tokens(record)
    ):
        raise ValueError("a recycled spill code is still referenced before reassignment")

    fixed_without_recycled = {
        font[(code - 1) * GLYPH_BYTES : code * GLYPH_BYTES]
        for code in range(1, 0xEE)
        if code not in recycled_codes
    }
    spill_candidates: Counter[bytes] = Counter()
    for record in trimmed_records:
        for token in tokens(record):
            value = bitmap(token, font, source_tail)
            if value is not None and value not in fixed_without_recycled:
                spill_candidates[value] += 1
    if not spill_candidates:
        raise ValueError("no dynamic bitmap is available for recycled spill code")
    output_font = bytearray(font)
    selected_spills = sorted(
        spill_candidates.items(), key=lambda item: (item[1], item[0]), reverse=True
    )[: len(RECYCLED_SPILL_CODES)]
    if len(selected_spills) != len(RECYCLED_SPILL_CODES):
        raise ValueError("not enough dynamic bitmaps for recycled spill slots")
    spill_report = []
    for code, (spill_bitmap, spill_occurrences) in zip(
        RECYCLED_SPILL_CODES, selected_spills
    ):
        spill_start = (code - 1) * GLYPH_BYTES
        old_spill_bitmap = bytes(
            output_font[spill_start : spill_start + GLYPH_BYTES]
        )
        output_font[spill_start : spill_start + GLYPH_BYTES] = spill_bitmap
        spill_report.append(
            {
                "code": f"0x{code:02X}",
                "old_bitmap_sha256": digest(old_spill_bitmap),
                "new_bitmap_sha256": digest(spill_bitmap),
                "occurrences": spill_occurrences,
                "tail_bytes_saved": GLYPH_BYTES,
                "token_bytes_saved": spill_occurrences,
            }
        )
    output_font_bytes = bytes(output_font)

    compact_tail = bytearray()
    compact_indexes: dict[bytes, int] = {}
    fixed_substitutions = 0
    final_records: list[bytes] = []
    fixed_bitmaps = {
        output_font_bytes[(code - 1) * GLYPH_BYTES : code * GLYPH_BYTES]: code
        for code in range(1, 0xEE)
    }
    for record_index, record in enumerate(trimmed_records):
        rebuilt = bytearray()
        for token in tokens(record):
            value = bitmap(token, font, source_tail)
            if value is None:
                rebuilt.extend(token)
                continue
            fixed_code = fixed_bitmaps.get(value)
            if fixed_code is not None:
                if len(token) == 2:
                    fixed_substitutions += 1
                rebuilt.append(fixed_code)
                continue
            new_index = compact_indexes.get(value)
            if new_index is None:
                new_index = len(compact_tail) // GLYPH_BYTES
                compact_indexes[value] = new_index
                compact_tail.extend(value)
            rebuilt.extend(encode_dynamic_index(new_index))
        rebuilt.append(0)
        final_records.append(bytes(rebuilt))

    output = build_mes(final_records, bytes(compact_tail))
    final_info, final_pointers = parse_mes(output, OUTPUT_MES)
    if not final_info.valid or final_info.pointer_count != POINTER_COUNT:
        raise ValueError("compacted MES structure is invalid")
    if len(output) > WHOLE_MES_LIMIT:
        raise ValueError(
            f"combined safe compaction reached 0x{len(output):X}, "
            f"still above 0x{WHOLE_MES_LIMIT:X}; phase={phase_saving}, "
            f"trailing={trailing_saving}, spill_occurrences="
            f"{sum(item['occurrences'] for item in spill_report)}, "
            f"dynamic_before={len(source_tail) // GLYPH_BYTES}, "
            f"dynamic_after={len(compact_tail) // GLYPH_BYTES}"
        )
    if final_info.split_offset > TEXT_SPLIT_LIMIT:
        raise ValueError("compacted MES text split exceeds 0x2600")
    v3_size = V3_MES.stat().st_size
    if v3_size - len(output) < MINIMUM_V3_SAVING:
        raise ValueError("compacted MES does not meet the requested 0x1E6 saving")

    final_spans = segments_for(output, final_pointers, final_info.split_offset)
    parsed_final_records = [
        output[item.offset : item.offset + item.size] for item in final_spans
    ]
    final_tail = output[final_info.split_offset :]
    for index, (intended, final) in enumerate(zip(trimmed_records, parsed_final_records)):
        intended_bitmaps = [
            bitmap(token, font, source_tail)
            for token in tokens(intended)
            if bitmap(token, font, source_tail) is not None
        ]
        final_bitmaps = [
            bitmap(token, output_font_bytes, final_tail)
            for token in tokens(final)
            if bitmap(token, output_font_bytes, final_tail) is not None
        ]
        if intended_bitmaps != final_bitmaps:
            raise ValueError(f"exact-bitmap re-encoding changed record {index}")
        if controls(source_records[index], font, source_tail) != controls(
            final, output_font_bytes, final_tail
        ):
            raise ValueError(f"control bytes changed at record {index}")

    for index in sorted(protected):
        source_cells = sum(
            bitmap(token, font, source_tail) is not None
            for token in tokens(source_records[index])
        )
        final_cells = sum(
            bitmap(token, output_font_bytes, final_tail) is not None
            for token in tokens(parsed_final_records[index])
        )
        if source_cells != final_cells:
            raise ValueError(f"protected row-stride changed at record {index}")
        if index in trimmed_counts:
            raise ValueError(f"protected record {index} lost terminal padding")

    OUTPUT_MES.write_bytes(output)
    OUTPUT_FONT.write_bytes(output_font_bytes)
    report = {
        "status": "PASS",
        "source": {
            "path": str(SOURCE_MES),
            "size": len(source),
            "size_hex": f"0x{len(source):X}",
            "sha256": digest(source),
            "split": source_info.split_offset,
        },
        "output": {
            "path": str(OUTPUT_MES),
            "size": len(output),
            "size_hex": f"0x{len(output):X}",
            "sha256": digest(output),
            "split": final_info.split_offset,
            "split_hex": f"0x{final_info.split_offset:X}",
            "whole_mes_headroom": WHOLE_MES_LIMIT - len(output),
            "saving_from_visualfix3": v3_size - len(output),
        },
        "compaction": {
            "phase_rows": phase_rows,
            "phase_bytes": phase_saving,
            "terminal_blank_bytes": trailing_saving,
            "terminal_blank_records": dict(sorted(trimmed_counts.items())),
            "dynamic_to_fixed_occurrences": fixed_substitutions,
            "dynamic_glyphs_before": len(source_tail) // GLYPH_BYTES,
            "dynamic_glyphs_after": len(final_tail) // GLYPH_BYTES,
            "recycled_fixed_spills": spill_report,
            "exact_reencoding_bytes": (
                len(source)
                - len(output)
                - phase_saving
                - trailing_saving
            ),
        },
        "guards": {
            "whole_mes_at_most_0x3fff": True,
            "saving_at_least_0x1e6_from_visualfix3": True,
            "text_split_at_most_0x2600": True,
            "pointer_count": POINTER_COUNT,
            "protected_records": sorted(protected),
            "protected_cell_counts_unchanged": True,
            "protected_records_excluded_from_terminal_trimming": True,
            "protected_phase_changes_limited_to_nonfinal_rows": True,
            "translated_prose_preserved": True,
            "control_bytes_preserved": True,
            "final_bitmap_encoding_equivalent": True,
            "global_font_changed_only_at_unused_translation_spills_0x48_0xbc": True,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

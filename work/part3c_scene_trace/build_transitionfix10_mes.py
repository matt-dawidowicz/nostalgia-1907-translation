#!/usr/bin/env python3
"""Build the complete 224-record PART3C retail-geometry MES."""

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
SOURCE_MES = HERE / "PART3C_rowparityfix6.MES"
SOURCE_FONT = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh" / "FIX_CODE.FNT"
ORIGINAL_MES = (
    WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
    / "001_PART3C.MES.unpacked"
)
ORIGINAL_SCN = (
    WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
    / "000_PART3C.SCN.unpacked"
)
V4_CONFIG = (
    PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
    / "PART3C_000_223_visualfix4_build_config.json"
)
V3_MES = (
    PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3" / "PART3C.MES"
)
REFLOW_REPORT = HERE / "transitionfix10_row_reflows.json"
OUTPUT_MES = HERE / "PART3C_transitionfix10.MES"
OUTPUT_SCN = HERE / "PART3C_transitionfix10.SCN"
REPORT = HERE / "transitionfix10_mes_report.json"

GLYPH_BYTES = 18
POINTER_COUNT = 224
WHOLE_MES_LIMIT = 0x3FFF
TEXT_SPLIT_LIMIT = 0x2600
MINIMUM_V3_SAVING = 0x1E6
WIDTH = 8
ROWS = (
    "Admit you have lost",
    "your judgment,",
    "Kasuke. This is",
    "an enlightened age.",
)
SELECTED_REFLOWS = (
    (14, 0),
    (83, 0),
    (93, 0),
    (110, 2),
    (136, 1),
    (146, 0),
    (149, 0),
    (154, 1),
    (157, 1),
)
JOINT_83_REPLACEMENT = "A5 E4 F0 B9 F0 99 0A E4 F1 1C 01"

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


def digest(data: bytes) -> str:
    """Return uppercase SHA-256."""
    return hashlib.sha256(data).hexdigest().upper()


def tokenize(record: bytes) -> list[bytes]:
    """Tokenize one null-terminated MES record."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    result = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        token = record[offset : offset + width]
        if len(token) != width:
            raise ValueError("truncated MES token")
        result.append(token)
        offset += width
    return result


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid 224-record PART3C MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def token_bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    """Resolve a token to a glyph bitmap, or None for a control token."""
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
    """Return non-glyph controls plus the record terminator."""
    result = [token for token in tokenize(record) if token_bitmap(token, font, tail) is None]
    result.append(b"\0")
    return result


def stored(unit: str) -> bytes:
    """Render one packed unit in stored orientation."""
    return transform_glyph_bytes(render_generated_unit("packed", unit), "prerot-cw")


def preferred_tokens(
    font: bytes, tail: bytes, excluded_dynamic: set[int]
) -> dict[bytes, bytes]:
    """Map bitmaps to shortest tokens while excluding slots being recycled."""
    result: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        if index in excluded_dynamic:
            continue
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        result[font[start : start + GLYPH_BYTES]] = bytes((code,))
    return result


def build_mes(records: list[bytes], tail: bytes) -> bytes:
    """Serialize all records with fresh monotonic pointers."""
    table_size = 2 + 2 * len(records)
    split = table_size + sum(map(len, records))
    output = bytearray(split + len(tail))
    output[:2] = split.to_bytes(2, "big")
    cursor = table_size
    for index, record in enumerate(records):
        output[2 + index * 2 : 4 + index * 2] = cursor.to_bytes(2, "big")
        output[cursor : cursor + len(record)] = record
        cursor += len(record)
    output[split:] = tail
    return bytes(output)


def main() -> None:
    """Reflow safe rows, recycle ten glyph slots, and restore retail SCN."""
    for path in (OUTPUT_MES, OUTPUT_SCN, REPORT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
    source, source_info, source_records, source_tail = load_mes(SOURCE_MES)
    _, _, original_records, _ = load_mes(ORIGINAL_MES)
    font = SOURCE_FONT.read_bytes()
    if len(source_tail) != 400 * GLYPH_BYTES:
        raise ValueError("unexpected source dynamic-tail size")
    reflow_data = json.loads(REFLOW_REPORT.read_text(encoding="utf-8"))
    reflows = {
        (int(item["record"]), int(item["row"])): item
        for item in reflow_data["candidates"]
    }

    records = list(source_records)
    reflow_audit = []
    retired: set[int] = set()
    for record_index, row in SELECTED_REFLOWS:
        item = reflows[(record_index, row)]
        row_width = int(item["row_width"])
        source_tokens = tokenize(records[record_index])
        start = row * row_width
        end = start + row_width
        if b"".join(source_tokens[start:end]).hex(" ").upper() != item["source_hex"]:
            raise ValueError(f"reflow source drift at record {record_index}, row {row}")
        replacement_hex = (
            JOINT_83_REPLACEMENT if (record_index, row) == (83, 0)
            else str(item["replacement_hex"])
        )
        replacement = tokenize(bytes.fromhex(replacement_hex) + b"\0")
        if len(replacement) != row_width:
            raise ValueError(f"reflow changed row width at record {record_index}")
        source_tokens[start:end] = replacement
        records[record_index] = b"".join(source_tokens) + b"\0"
        retired_indexes = {int(value) for value in item["retired_dynamic_indexes"]}
        retired.update(retired_indexes)
        reflow_audit.append(
            {
                "record": record_index,
                "row": row,
                "row_width": row_width,
                "prose": item["prose"],
                "retired_dynamic_indexes": sorted(retired_indexes),
                "source_bytes": sum(map(len, tokenize(source_records[record_index]))),
                "target_bytes": sum(map(len, tokenize(records[record_index]))),
            }
        )
    expected_reflow_retired = {136, 294, 302, 333, 352, 364, 367, 371, 373}
    if retired != expected_reflow_retired:
        raise ValueError(f"unexpected reflow-retired slots: {sorted(retired)}")

    # The old ten-cell record-162 encoding uniquely owns slot 376.
    usage_before: Counter[int] = Counter()
    for record in records:
        for token in tokenize(record):
            if len(token) == 2:
                index = dynamic_glyph_index(token[0], token[1])
                if index is not None:
                    usage_before[index] += 1
    if usage_before[376] != 1:
        raise ValueError("record 162 no longer uniquely owns dynamic slot 376")
    retired.add(376)
    if len(retired) != 10 or max(retired) >= 382:
        raise ValueError("recycled slot set violates the low-F1 transition guard")

    available = preferred_tokens(font, source_tail, retired)
    blank = available.get(bytes(GLYPH_BYTES))
    if blank is None or len(blank) != 1:
        raise ValueError("no one-byte blank padding glyph is available")
    target_rows = []
    target_bitmaps = []
    for line in ROWS:
        units = pack_text_pairs(line)
        if len(units) > WIDTH:
            raise ValueError(f"record-162 row exceeds eight cells: {line}")
        target_rows.append((line, units, WIDTH - len(units)))
        target_bitmaps.extend(stored(unit) for unit in units)
        target_bitmaps.extend([bytes(GLYPH_BYTES)] * (WIDTH - len(units)))
    missing = []
    for value in target_bitmaps:
        if value not in available and value not in missing:
            missing.append(value)
    if len(missing) != len(retired):
        raise ValueError(f"expected ten missing record-162 bitmaps, found {len(missing)}")
    assignments = {
        value: index for value, index in zip(missing, sorted(retired))
    }
    tail = bytearray(source_tail)
    for value, index in assignments.items():
        start = index * GLYPH_BYTES
        tail[start : start + GLYPH_BYTES] = value

    encoded_162 = bytearray()
    row_report = []
    for line, units, padding in target_rows:
        unit_report = []
        for unit in units:
            value = stored(unit)
            token = available.get(value)
            recycled = False
            if token is None:
                token = encode_dynamic_index(assignments[value])
                recycled = True
            encoded_162.extend(token)
            unit_report.append(
                {
                    "unit": unit,
                    "token": token.hex(" ").upper(),
                    "recycled_slot": assignments.get(value) if recycled else None,
                }
            )
        encoded_162.extend(blank * padding)
        row_report.append(
            {"text": line, "units": unit_report, "padding_cells": padding}
        )
    encoded_162.append(0)

    records[159] = b"\x01\x01" + records[159]
    records[162] = bytes(encoded_162)
    output = build_mes(records, bytes(tail))
    info, pointers = parse_mes(output, OUTPUT_MES)
    spans = segments_for(output, pointers, info.split_offset)
    parsed = [output[item.offset : item.offset + item.size] for item in spans]
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError("final MES structure is invalid")

    expected_changed = sorted(
        {record for record, _ in SELECTED_REFLOWS} | {159, 162}
    )
    changed = [
        index for index, (before, after) in enumerate(zip(source_records, parsed))
        if before != after
    ]
    if changed != expected_changed:
        raise ValueError(f"unexpected final record changes: {changed}")
    if any(parsed[index] != source_records[index] for index in range(112, 124)):
        raise ValueError("protected records 112-123 changed")
    if any(parsed[index] != source_records[index] for index in range(163, 224)):
        raise ValueError("records 163-223 are not byte-identical to the full translation")
    if parsed[159][:2] != b"\x01\x01" or parsed[159][2:] != source_records[159]:
        raise ValueError("Captain Room padding/suffix contract failed")
    if len(tokenize(parsed[162])) != WIDTH * len(ROWS):
        raise ValueError("record 162 is not exactly four rows by eight cells")
    if any(
        token[0] == 0xF1 and token[1] >= 0x80
        for token in tokenize(parsed[162])
        if len(token) == 2
    ):
        raise ValueError("record 162 crosses the guarded F1 low-byte boundary")

    for index in changed:
        if controls(source_records[index], font, source_tail) != controls(
            parsed[index], font, bytes(tail)
        ):
            raise ValueError(f"control-byte sequence changed at record {index}")
    for record_index, row in SELECTED_REFLOWS:
        if len(tokenize(records[record_index])) != len(tokenize(source_records[record_index])):
            raise ValueError(f"reflow cell count changed at record {record_index}")

    # Every recycled slot must now be referenced only by record 162.
    final_refs: dict[int, set[int]] = {index: set() for index in retired}
    all_refs: set[int] = set()
    for record_index, record in enumerate(parsed):
        for token in tokenize(record):
            if len(token) != 2:
                continue
            index = dynamic_glyph_index(token[0], token[1])
            if index is not None:
                all_refs.add(index)
                if index in final_refs:
                    final_refs[index].add(record_index)
    if any(records_using != {162} for records_using in final_refs.values()):
        raise ValueError(f"recycled-slot ownership failed: {final_refs}")
    if all_refs != set(range(len(tail) // GLYPH_BYTES)):
        raise ValueError("dynamic tail contains an unreferenced or missing slot")

    source_phrase = next(
        str(item["text"])
        for item in json.loads(V4_CONFIG.read_text(encoding="utf-8"))["segments"]
        if int(item["segment"]) == 162
    )
    normalized_source = " ".join(source_phrase.split())
    normalized_target = " ".join(ROWS)
    if normalized_source != normalized_target:
        raise ValueError("record 162 translated prose changed")
    original_rows = (len(tokenize(original_records[162])) + WIDTH - 1) // WIDTH
    if original_rows != 4:
        raise ValueError("retail record 162 no longer establishes a four-row contract")

    if len(output) > WHOLE_MES_LIMIT or info.split_offset > TEXT_SPLIT_LIMIT:
        raise ValueError("final MES exceeds a hard runtime boundary")
    saving = V3_MES.stat().st_size - len(output)
    if saving < MINIMUM_V3_SAVING:
        raise ValueError("final MES does not preserve the required visualfix3 saving")

    scn = ORIGINAL_SCN.read_bytes()
    critical_chain = bytes.fromhex(
        "24 02 0E 0E 0C 27 00 A1 "
        "24 02 0E 0E 0C 27 00 A2 "
        "24 02 0E 0E 0C 27 00 A3 "
        "24 02 0E 0E 0C 27 00 A4"
    )
    if scn[0x0B13 : 0x0B33] != critical_chain:
        raise ValueError("retail 160-163 chained window commands changed")
    OUTPUT_MES.write_bytes(output)
    OUTPUT_SCN.write_bytes(scn)

    report = {
        "status": "PASS",
        "release_candidate": True,
        "diagnosis": "retail title padding and exact 0x24 window geometry are runtime invariants",
        "mes": {
            "source_size": len(source),
            "output_size": len(output),
            "output_size_hex": f"0x{len(output):X}",
            "hard_limit": WHOLE_MES_LIMIT,
            "headroom": WHOLE_MES_LIMIT - len(output),
            "source_split": source_info.split_offset,
            "output_split": info.split_offset,
            "text_split_limit": TEXT_SPLIT_LIMIT,
            "visualfix3_size": V3_MES.stat().st_size,
            "saving_from_visualfix3": saving,
            "minimum_saving": MINIMUM_V3_SAVING,
            "pointer_count": POINTER_COUNT,
            "sha256": digest(output),
        },
        "scope": {
            "changed_records": changed,
            "records_112_123_byte_identical": True,
            "records_163_223_byte_identical": True,
            "all_224_records_present": True,
            "translated_prose_preserved": True,
            "control_sequences_preserved": True,
        },
        "safe_reflows": reflow_audit,
        "record_159": {
            "retail_leading_padding_restored": "01 01",
            "translated_suffix_byte_identical": True,
        },
        "record_162": {
            "prose": normalized_target,
            "rows": row_report,
            "row_count": len(ROWS),
            "width_cells": WIDTH,
            "cell_count": WIDTH * len(ROWS),
            "retail_row_count": original_rows,
            "no_f1_low_byte_ge_0x80": True,
        },
        "dynamic_tail": {
            "source_glyphs": len(source_tail) // GLYPH_BYTES,
            "output_glyphs": len(tail) // GLYPH_BYTES,
            "byte_length_unchanged": len(tail) == len(source_tail),
            "recycled_slots": sorted(retired),
            "each_recycled_slot_owned_only_by_record_162": True,
            "all_slots_referenced": True,
        },
        "scn": {
            "byte_identical_to_retail": True,
            "critical_chain_offset": "0x0B13",
            "critical_chain_byte_identical": True,
            "record_162_width_operand": "0x0E",
            "sha256": digest(scn),
        },
        "font_changed": False,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Restore record 162 to four rows by widening only its 0x24 SCN window."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE_MES = HERE / "PART3C_boundarypadfix5.MES"
SOURCE_FONT = HERE / "FIX_CODE_boundarypadfix5.FNT"
ORIGINAL_DIR = HERE.parent / "part3c_original_compare" / "original_part3c"
ORIGINAL_MES = ORIGINAL_DIR / "001_PART3C.MES.unpacked"
ORIGINAL_SCN = ORIGINAL_DIR / "000_PART3C.SCN.unpacked"
V4_CONFIG = (
    PROJECT
    / "outputs"
    / "nostalgia1907_act3c_000_223_visualfix4"
    / "PART3C_000_223_visualfix4_build_config.json"
)
OUTPUT_MES = HERE / "PART3C_rowparityfix6.MES"
OUTPUT_SCN = HERE / "PART3C_rowparityfix6.SCN"
REPORT = HERE / "rowparityfix6_mes_report.json"

GLYPH_BYTES = 18
WHOLE_MES_LIMIT = 0x3FFF
RECORD = 162
SCN_COMMAND_OFFSET = 0x0B23
SCN_WIDTH_OFFSET = SCN_COMMAND_OFFSET + 3
SOURCE_RAW_WIDTH = 0x0E
TARGET_RAW_WIDTH = 0x12
SOURCE_CELL_WIDTH = 8
TARGET_CELL_WIDTH = 10
TARGET_ROWS = (
    "Admit you have",
    "lost your judgment,",
    "Kasuke. This is an",
    "enlightened age.",
)

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)
from plan_record162_rowparity import encode_line_from_existing  # noqa: E402


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load and split one valid MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != 224:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def bitmap_tokens(font: bytes, tail: bytes) -> dict[bytes, bytes]:
    """Map every current bitmap to its shortest token."""
    result: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        start = index * GLYPH_BYTES
        result.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        result[font[start : start + GLYPH_BYTES]] = bytes((code,))
    return result


def stored_unit(style: str, unit: str) -> bytes:
    """Render one generated unit in the MES/FNT storage orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def tokens(record: bytes) -> list[bytes]:
    """Tokenize one null-terminated MES record."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    result: list[bytes] = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] in (0xF0, 0xF1) else 1
        token = record[offset : offset + width]
        if len(token) != width:
            raise ValueError("incomplete MES token")
        result.append(token)
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
    raise ValueError(f"non-glyph token in generated record: {token.hex()}")


def build_mes(records: list[bytes], tail: bytes) -> bytes:
    """Serialize records with fresh monotonic pointers and an unchanged tail."""
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


def cell_count(record: bytes) -> int:
    """Return the number of rendered glyph cells."""
    return len(tokens(record))


def main() -> None:
    """Build the guarded MES and one-byte SCN operand patch."""
    for path in (OUTPUT_MES, OUTPUT_SCN, REPORT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    source, source_info, records, tail = load_mes(SOURCE_MES)
    _, _, original_records, _ = load_mes(ORIGINAL_MES)
    font = SOURCE_FONT.read_bytes()
    available = bitmap_tokens(font, tail)
    blank_token = available.get(bytes(GLYPH_BYTES))
    if blank_token is None or len(blank_token) != 1:
        raise ValueError("no one-byte blank glyph is available for row padding")

    config = json.loads(V4_CONFIG.read_text(encoding="utf-8"))
    entry = next(item for item in config["segments"] if item["segment"] == RECORD)
    source_phrase = " ".join(str(entry["text"]).split())
    target_phrase = " ".join(TARGET_ROWS)
    if target_phrase != source_phrase:
        raise ValueError("target row wrap changes translated prose")

    encoded = bytearray()
    expected_bitmaps: list[bytes] = []
    row_report: list[dict[str, object]] = []
    for line in TARGET_ROWS:
        encoded_units = encode_line_from_existing(line, available)
        if encoded_units is None or len(encoded_units) > TARGET_CELL_WIDTH:
            raise ValueError(f"cannot encode target row in {TARGET_CELL_WIDTH} cells: {line!r}")
        for item in encoded_units:
            token = bytes.fromhex(item["token"])
            encoded.extend(token)
            expected_bitmaps.append(stored_unit(item["style"], item["unit"]))
        padding = TARGET_CELL_WIDTH - len(encoded_units)
        encoded.extend(blank_token * padding)
        expected_bitmaps.extend([bytes(GLYPH_BYTES)] * padding)
        row_report.append(
            {
                "text": line,
                "content_cells": len(encoded_units),
                "padding_cells": padding,
                "units": encoded_units,
            }
        )
    encoded.append(0)
    replacement = bytes(encoded)
    actual_bitmaps = [token_bitmap(token, font, tail) for token in tokens(replacement)]
    if actual_bitmaps != expected_bitmaps:
        raise ValueError("record 162 bitmap reconstruction failed")
    if len(actual_bitmaps) != TARGET_CELL_WIDTH * len(TARGET_ROWS):
        raise ValueError("record 162 does not occupy exactly four ten-cell rows")

    source_records = list(records)
    source_record = source_records[RECORD]
    source_records[RECORD] = replacement
    candidate = build_mes(source_records, tail)
    candidate_info, candidate_pointers = parse_mes(candidate, OUTPUT_MES)
    if not candidate_info.valid or candidate_info.pointer_count != 224:
        raise ValueError("candidate MES is structurally invalid")
    candidate_spans = segments_for(candidate, candidate_pointers, candidate_info.split_offset)
    candidate_records = [
        candidate[item.offset : item.offset + item.size] for item in candidate_spans
    ]
    if any(
        candidate_records[index] != records[index]
        for index in range(len(records))
        if index != RECORD
    ):
        raise ValueError("a MES record other than 162 changed")
    if candidate[candidate_info.split_offset :] != tail:
        raise ValueError("dynamic glyph tail changed")
    if len(candidate) > WHOLE_MES_LIMIT:
        raise ValueError("row-parity MES exceeds 0x3FFF")

    original_rows = (cell_count(original_records[RECORD]) + SOURCE_CELL_WIDTH - 1) // SOURCE_CELL_WIDTH
    target_rows = cell_count(replacement) // TARGET_CELL_WIDTH
    if original_rows != 4 or target_rows != original_rows:
        raise ValueError("record 162 row parity was not restored")

    source_scn = ORIGINAL_SCN.read_bytes()
    if source_scn[SCN_COMMAND_OFFSET : SCN_COMMAND_OFFSET + 8] != bytes.fromhex(
        "24 02 0E 0E 0C 27 00 A3"
    ):
        raise ValueError("record 162 SCN command no longer matches the original")
    if source_scn[SCN_WIDTH_OFFSET] != SOURCE_RAW_WIDTH:
        raise ValueError("unexpected original SCN width operand")
    candidate_scn = bytearray(source_scn)
    candidate_scn[SCN_WIDTH_OFFSET] = TARGET_RAW_WIDTH
    changed_scn_offsets = [
        index
        for index, (before, after) in enumerate(zip(source_scn, candidate_scn))
        if before != after
    ]
    if changed_scn_offsets != [SCN_WIDTH_OFFSET]:
        raise ValueError("SCN changed outside the guarded width operand")

    OUTPUT_MES.write_bytes(candidate)
    OUTPUT_SCN.write_bytes(candidate_scn)
    report = {
        "status": "PASS",
        "diagnosis": (
            "record 162 expanded from four original rows to six translated rows "
            "inside a four-row chained 0x24 window sequence"
        ),
        "prose": {
            "source": source_phrase,
            "target": target_phrase,
            "byte_for_byte_text_normalization_match": source_phrase == target_phrase,
            "rows": row_report,
        },
        "record_162": {
            "source_size": len(source_record),
            "target_size": len(replacement),
            "source_cells": cell_count(source_record),
            "target_cells": cell_count(replacement),
            "original_rows": original_rows,
            "target_rows": target_rows,
            "target_width_cells": TARGET_CELL_WIDTH,
            "encoded_hex": replacement.hex(" ").upper(),
        },
        "mes": {
            "source_size": len(source),
            "target_size": len(candidate),
            "target_size_hex": f"0x{len(candidate):X}",
            "limit": WHOLE_MES_LIMIT,
            "headroom": WHOLE_MES_LIMIT - len(candidate),
            "source_split": source_info.split_offset,
            "target_split": candidate_info.split_offset,
            "dynamic_tail_byte_identical": True,
            "only_record_162_changed": True,
            "sha256": digest(candidate),
        },
        "scn": {
            "command_offset": SCN_COMMAND_OFFSET,
            "changed_offset": SCN_WIDTH_OFFSET,
            "changed_offset_hex": f"0x{SCN_WIDTH_OFFSET:04X}",
            "source_width": SOURCE_RAW_WIDTH,
            "target_width": TARGET_RAW_WIDTH,
            "only_width_operand_changed": True,
            "sha256": digest(candidate_scn),
        },
        "font_changed": False,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

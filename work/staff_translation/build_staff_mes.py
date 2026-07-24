#!/usr/bin/env python3
"""Build and strictly validate the English STAFF credits MES."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE = PROJECT / "work" / "nostalgia1907" / "unpacked" / "STAFF"
SOURCE_MES = SOURCE / "001_STAFF.MES.unpacked"
SOURCE_SCN = SOURCE / "000_STAFF.SCN.unpacked"
TEXTS = HERE / "STAFF_texts.json"
OUTPUT = HERE / "built"
OUTPUT_MES = OUTPUT / "STAFF.MES"
OUTPUT_SCN = OUTPUT / "STAFF.SCN"
MANIFEST = OUTPUT / "STAFF_manifest.json"

EXPECTED_RECORDS = 62
ASCII_LINE_CHARS = 40
RUNTIME_LINE_CELLS = 20
MAX_MES_SIZE = 0x3FFF

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    build_dynamic_text_mes_selective,
    parse_mes,
    read_segment_texts_json,
    segments_for,
)


def digest(data: bytes) -> str:
    """Return uppercase SHA-256."""
    return hashlib.sha256(data).hexdigest().upper()


def load_records(path: Path) -> tuple[bytes, object, list[int], list[bytes]]:
    """Read a MES with strict pointers and one final terminator per record."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != EXPECTED_RECORDS:
        raise ValueError(f"invalid STAFF MES structure: {path}")
    if any(left >= right for left, right in zip(pointers, pointers[1:])):
        raise ValueError(f"non-monotonic STAFF pointers: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    for index, record in enumerate(records):
        if not record or record[-1] != 0 or record.count(0) != 1:
            raise ValueError(f"STAFF record {index} lacks exactly one final terminator")
    if len(data[info.split_offset :]) % 18:
        raise ValueError("STAFF dynamic font bank is not 18-byte aligned")
    return data, info, pointers, records


def validate_scn() -> dict[str, object]:
    """Require the reviewed retail credit sequence to reference all records."""
    data = SOURCE_SCN.read_bytes()
    references = [
        data[offset + 2]
        for offset in range(len(data) - 2)
        if data[offset : offset + 2] == bytes((0x20, 0x00))
    ]
    expected = set(range(1, EXPECTED_RECORDS + 1))
    if len(references) != 65 or set(references) != expected:
        raise ValueError(f"STAFF SCN credit-reference inventory drifted: {references}")
    if any(value < 1 or value > EXPECTED_RECORDS for value in references):
        raise ValueError("STAFF SCN contains an out-of-range credit record")
    return {
        "sha256": digest(data),
        "credit_draw_commands": len(references),
        "unique_records_referenced": len(set(references)),
        "all_records_referenced": True,
        "references_in_range": True,
    }


def pair_aligned_center(text: str) -> str:
    """Center a card while starting visible text in the first half of a pair."""
    available = ASCII_LINE_CHARS - len(text)
    left = available // 2
    if left % 2:
        left += 1
    right = available - left
    if right < 0:
        raise ValueError(f"credit card exceeds {ASCII_LINE_CHARS} characters: {text!r}")
    return " " * left + text + " " * right


def main() -> None:
    """Build every credit card and write an audit manifest."""
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite STAFF build directory: {OUTPUT}")
    source_data, source_info, _, source_records = load_records(SOURCE_MES)
    if len(source_records) != EXPECTED_RECORDS:
        raise ValueError("STAFF source record count changed")
    replacements = read_segment_texts_json(TEXTS)
    expected_indices = set(range(EXPECTED_RECORDS))
    if set(replacements) != expected_indices:
        missing = sorted(expected_indices - set(replacements))
        extra = sorted(set(replacements) - expected_indices)
        raise ValueError(f"STAFF translation coverage mismatch: missing={missing}, extra={extra}")
    for index, text in replacements.items():
        if not text or len(text) > ASCII_LINE_CHARS:
            raise ValueError(f"STAFF record {index} has invalid length {len(text)}")
        if any(ord(character) < 0x20 or ord(character) > 0x7E for character in text):
            raise ValueError(f"STAFF record {index} is not printable ASCII")
        if "\n" in text or "\r" in text:
            raise ValueError(f"STAFF record {index} is not a single-line card")

    centered = {index: pair_aligned_center(text) for index, text in replacements.items()}
    if any(len(text) != ASCII_LINE_CHARS for text in centered.values()):
        raise ValueError("STAFF centering did not produce exact 40-character rows")

    OUTPUT.mkdir(parents=True)
    manifest = build_dynamic_text_mes_selective(
        SOURCE_MES,
        OUTPUT_MES,
        centered,
        glyph_transform="prerot-cw",
        max_render_cells={index: RUNTIME_LINE_CELLS for index in replacements},
        pack_pairs=True,
        pack_segments=set(replacements),
        literal_space_pack_segments=set(replacements),
        generated_glyph_order="first-use",
        prune_unused_original_glyphs=True,
    )
    shutil.copyfile(SOURCE_SCN, OUTPUT_SCN)

    output_data, output_info, output_pointers, output_records = load_records(OUTPUT_MES)
    if len(output_data) > MAX_MES_SIZE:
        raise ValueError("STAFF MES crossed the hard 0x3FFF boundary")
    if len(output_records) != EXPECTED_RECORDS or len(output_pointers) != EXPECTED_RECORDS:
        raise ValueError("STAFF output record inventory changed")
    if OUTPUT_SCN.read_bytes() != SOURCE_SCN.read_bytes():
        raise ValueError("STAFF SCN changed")
    segment_audit = manifest.get("segments", [])
    if len(segment_audit) != EXPECTED_RECORDS:
        raise ValueError("STAFF builder manifest lost records")
    if any(item.get("render_cell_count") != RUNTIME_LINE_CELLS for item in segment_audit):
        raise ValueError("STAFF card is not exactly 20 runtime cells after pair packing")
    if any(item.get("render_cell_limit") != RUNTIME_LINE_CELLS for item in segment_audit):
        raise ValueError("STAFF runtime width guard was not applied")

    scn_audit = validate_scn()
    manifest.update({
        "status": "PASS",
        "chapter": "STAFF",
        "translation_status": "first-pass-complete",
        "translation_coverage": {
            "expected_records": EXPECTED_RECORDS,
            "translated_records": len(replacements),
            "complete": True,
        },
        "visible_texts": {str(index): replacements[index] for index in sorted(replacements)},
        "centering": {
            "ascii_characters_per_card": ASCII_LINE_CHARS,
            "pair_packed_runtime_cells": RUNTIME_LINE_CELLS,
            "every_card_exact_width": True,
            "visible_text_starts_on_first_pair_half": True,
        },
        "source": {
            "size": len(source_data),
            "split_offset": source_info.split_offset,
            "sha256": digest(source_data),
        },
        "output": {
            "size": len(output_data),
            "size_hex": f"0x{len(output_data):X}",
            "hard_limit": "0x3FFF",
            "headroom": MAX_MES_SIZE - len(output_data),
            "split_offset": output_info.split_offset,
            "dynamic_glyphs": len(output_data[output_info.split_offset :]) // 18,
            "sha256": digest(output_data),
            "strictly_increasing_pointers": True,
            "one_final_terminator_per_record": True,
            "dynamic_tail_18_byte_aligned": True,
        },
        "scn": scn_audit,
    })
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "records": EXPECTED_RECORDS,
        "mes_size": len(output_data),
        "split_offset": output_info.split_offset,
        "dynamic_glyphs": len(output_data[output_info.split_offset :]) // 18,
        "scn_draw_commands": scn_audit["credit_draw_commands"],
    }, indent=2))


if __name__ == "__main__":
    main()

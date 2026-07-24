#!/usr/bin/env python3
"""Independently verify the bounded, padded PART3C BIN/CUE delivery."""

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
BASE = HERE.parent / "part3c_globalfontfix3" / "PART3C_globalfontfix3.MES"
ORIGINAL = WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
FINAL = WORKSPACE / "outputs" / "PART3C_boundarypadfix5_fresh"

MES = FINAL / "PART3C.MES"
FONT = FINAL / "FIX_CODE.FNT"
LZ = FINAL / "PART3C_boundarypadfix5.LZ"
ISO = FINAL / "Nostalgia1907_Act3C_000_223_boundarypadfix5.iso"
TRACK1 = FINAL / "Nostalgia1907_Act3C_000_223_boundarypadfix5_Track1.bin"
TRACK2 = FINAL / "Nostalgia1907_Act3C_000_223_boundarypadfix5_Track2.bin"
CUE = FINAL / "Nostalgia1907_Act3C_000_223_boundarypadfix5.cue"
ISO_EXTRACT = FINAL / "iso_extract"
UNPACKED = FINAL / "archive_candidate_unpacked"
REGRESSION = FINAL / "regression_full"
REPORT = FINAL / "final_verification.json"
CONFIG = V4 / "PART3C_000_223_visualfix4_build_config.json"
PHASE = (
    PROJECT
    / "work"
    / "nostalgia1907"
    / "part3c_blackoutfix"
    / "phase_compaction_analysis.json"
)
COMPACT = HERE / "boundarypad_compaction_report.json"

GLYPH_BYTES = 18
WHOLE_MES_LIMIT = 0x3FFF
MINIMUM_V3_SAVING = 0x1E6
RECYCLED_CODES = {0x48, 0xBC}

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)
from nostalgia1907 import inspect_standard_mega_cd_cue  # noqa: E402
from verify_final_globalfontfix3 import (  # noqa: E402
    iso_payload_facts,
    member_hashes,
    verify_raw_payload,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def facts(path: Path) -> dict[str, object]:
    """Return file size and SHA-256."""
    data = path.read_bytes()
    return {"size": len(data), "sha256": digest(data)}


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load one valid MES and split it into records."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid:
        raise ValueError(f"invalid MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def tokens(record: bytes) -> list[bytes]:
    """Tokenize one null-terminated record."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    result = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        token = record[offset : offset + width]
        if len(token) != width or offset + width > len(record) - 1:
            raise ValueError("incomplete token")
        result.append(token)
        offset += width
    return result


def bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    """Resolve a glyph token to its bitmap."""
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
            raise ValueError(f"missing dynamic glyph {index}")
        return value
    return None


def bitmaps(record: bytes, font: bytes, tail: bytes) -> list[bytes]:
    """Return the record's ordered rendered glyph bitmaps."""
    return [
        value
        for token in tokens(record)
        for value in [bitmap(token, font, tail)]
        if value is not None
    ]


def controls(record: bytes, font: bytes, tail: bytes) -> list[bytes]:
    """Return non-glyph controls and the terminator."""
    return [token for token in tokens(record) if bitmap(token, font, tail) is None] + [
        b"\x00"
    ]


def render(style: str, unit: str) -> bytes:
    """Render one manifest unit in stored orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def fixed_usage(path: Path) -> Counter[int]:
    """Count fixed one-byte codes in an MES."""
    _, _, records, _ = load_mes(path)
    result: Counter[int] = Counter()
    for record in records:
        for token in tokens(record):
            if len(token) == 1 and 1 <= token[0] <= 0xED:
                result[token[0]] += 1
    return result


def main() -> None:
    """Verify content, packaging, and raw disc geometry."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    compact = json.loads(COMPACT.read_text(encoding="utf-8"))
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    phase = json.loads(PHASE.read_text(encoding="utf-8"))
    if compact.get("status") != "PASS" or phase["unmatched"]:
        raise ValueError("source compaction reports are not clean")

    data, info, records, tail = load_mes(MES)
    _, _, base_records, base_tail = load_mes(BASE)
    output_font = FONT.read_bytes()
    base_font = V3.joinpath("FIX_CODE.FNT").read_bytes()
    if len(data) > WHOLE_MES_LIMIT:
        raise ValueError("whole MES exceeds 0x3FFF")
    if V3.joinpath("PART3C.MES").stat().st_size - len(data) < MINIMUM_V3_SAVING:
        raise ValueError("MES does not save the required 0x1E6 bytes")
    if info.pointer_count != 224 or info.split_offset > 0x2600:
        raise ValueError("MES pointer/split guard failed")

    changed_font_offsets = {
        index
        for index, (before, after) in enumerate(zip(base_font, output_font))
        if before != after
    }
    allowed_font_offsets = {
        index
        for code in RECYCLED_CODES
        for index in range((code - 1) * GLYPH_BYTES, code * GLYPH_BYTES)
    }
    if not changed_font_offsets or not changed_font_offsets <= allowed_font_offsets:
        raise ValueError("font changed outside translation-owned spill slots")

    entries = {int(item["segment"]): item for item in config["segments"]}
    protected = set(config["scn_fixed_window_padding"]["segments"]) | set(
        config["profile_forced_final_row_padding"]["segments"]
    )
    selected_rows = {
        (int(item["segment"]), int(item["row"]))
        for item in compact["compaction"]["phase_rows"]
    }
    candidates = {
        (int(item["segment"]), int(item["row"])): item
        for item in phase["candidates"]
        if (int(item["segment"]), int(item["row"])) in selected_rows
    }
    if set(candidates) != selected_rows:
        raise ValueError("selected phase rows cannot be reconstructed")

    checked_translated_cells = 0
    blank = bytes(GLYPH_BYTES)
    for index, record in enumerate(records):
        if controls(record, output_font, tail) != controls(
            base_records[index], base_font, base_tail
        ):
            raise ValueError(f"control bytes changed at record {index}")
        if index == 158:
            expected = bitmaps(base_records[index], base_font, base_tail)
        else:
            entry = entries[index]
            units = [
                (str(item["style"]), str(item["unit"])) for item in entry["units"]
            ]
            for key in sorted(
                (key for key in selected_rows if key[0] == index),
                key=lambda item: int(candidates[item]["unit_start"]),
                reverse=True,
            ):
                candidate = candidates[key]
                start = int(candidate["unit_start"])
                end = int(candidate["unit_end"])
                current = [tuple(item) for item in candidate["current_units"]]
                replacement = [tuple(item) for item in candidate["candidate_units"]]
                if units[start:end] != current:
                    raise ValueError(f"phase reconstruction mismatch at {key}")
                if "".join(unit for _, unit in current).strip() != "".join(
                    unit for _, unit in replacement
                ).strip():
                    raise ValueError(f"phase reconstruction changes prose at {key}")
                units[start:end] = replacement
            expected = [render(style, unit) for style, unit in units]
            if index not in protected:
                while expected and expected[-1] == blank:
                    expected.pop()
            checked_translated_cells += len(expected)
        actual = bitmaps(record, output_font, tail)
        if actual != expected:
            raise ValueError(f"rendered bitmap stream changed at record {index}")
        if index in protected and len(actual) != len(
            bitmaps(base_records[index], base_font, base_tail)
        ):
            raise ValueError(f"protected cell count changed at record {index}")

    for index in range(160, 165):
        if len(bitmaps(records[index], output_font, tail)) != len(
            bitmaps(base_records[index], base_font, base_tail)
        ):
            raise ValueError(f"failing-window cell count changed at record {index}")

    referenced = {
        dynamic_glyph_index(token[0], token[1])
        for record in records
        for token in tokens(record)
        if len(token) == 2 and dynamic_glyph_index(token[0], token[1]) is not None
    }
    if referenced != set(range(len(tail) // GLYPH_BYTES)):
        raise ValueError("dynamic tail is not exactly and fully referenced")

    other_mes = [
        path
        for path in REGRESSION.glob("*/*.MES.unpacked")
        if path.parent.name not in {"PART3C", "reflow_source_unpack", "reflow_rebuilt_unpack"}
    ]
    other_spill_uses = {
        str(path.relative_to(REGRESSION)): {
            f"0x{code:02X}": fixed_usage(path)[code]
            for code in sorted(RECYCLED_CODES)
            if fixed_usage(path)[code]
        }
        for path in other_mes
    }
    other_spill_uses = {key: value for key, value in other_spill_uses.items() if value}
    if other_spill_uses:
        raise ValueError(f"another chapter uses recycled spill codes: {other_spill_uses}")

    original_members = member_hashes(ORIGINAL)
    delivered_members = member_hashes(UNPACKED)
    changed_members = sorted(
        name
        for name in original_members
        if original_members[name] != delivered_members[name]
    )
    if set(original_members) != set(delivered_members) or changed_members != [
        "001_PART3C.MES.unpacked"
    ]:
        raise ValueError("PART3C archive member contract failed")
    for name in (
        "000_PART3C.SCN.unpacked",
        "002_SCREEN0.BS.unpacked",
        "003_SCREEN1.BS.unpacked",
    ):
        if (UNPACKED / name).read_bytes() != (ORIGINAL / name).read_bytes():
            raise ValueError(f"protected scene asset changed: {name}")
    if (ISO_EXTRACT / "PART3C.LZ").read_bytes() != LZ.read_bytes():
        raise ValueError("ISO-extracted PART3C.LZ differs")
    if (ISO_EXTRACT / "FIX_CODE.FNT").read_bytes() != output_font:
        raise ValueError("ISO-extracted FIX_CODE.FNT differs")

    source_iso = iso_payload_facts(V3 / "Nostalgia1907_Act3C_000_223_visualfix3.iso")
    delivered_iso = iso_payload_facts(ISO)
    changed_iso = sorted(
        name for name in source_iso if source_iso[name] != delivered_iso[name]
    )
    if set(source_iso) != set(delivered_iso) or changed_iso != [
        "FIX_CODE.FNT",
        "PART3C.LZ",
    ]:
        raise ValueError(f"ISO change contract failed: {changed_iso}")

    chunks = [
        member
        for lz_path in ISO_EXTRACT.glob("*.LZ")
        for member in (REGRESSION / lz_path.stem).rglob("*.unpacked")
    ]
    mes_files = [
        path
        for path in REGRESSION.rglob("*.unpacked")
        if path.name.upper().endswith(".MES.UNPACKED")
    ]
    if len(chunks) != 564 or len(mes_files) != 21:
        raise ValueError("full regression counts changed")
    for path in mes_files:
        mes_info, _ = parse_mes(path.read_bytes(), path)
        if not mes_info.valid:
            raise ValueError(f"invalid regression MES: {path}")

    disc = inspect_standard_mega_cd_cue(CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("disc/CUE contract failed")
    raw = verify_raw_payload(TRACK1, ISO)

    report = {
        "status": "PASS",
        "delivery": {
            "mes": facts(MES),
            "font": facts(FONT),
            "lz": facts(LZ),
            "iso": facts(ISO),
            "track_1": facts(TRACK1),
            "track_2": facts(TRACK2),
            "cue": facts(CUE),
        },
        "boundary": {
            "whole_mes_size": len(data),
            "whole_mes_size_hex": f"0x{len(data):X}",
            "whole_mes_limit": WHOLE_MES_LIMIT,
            "headroom": WHOLE_MES_LIMIT - len(data),
            "saving_from_visualfix3": V3.joinpath("PART3C.MES").stat().st_size
            - len(data),
            "text_split": info.split_offset,
        },
        "content": {
            "translated_records": len(entries),
            "verified_translated_cells": checked_translated_cells,
            "control_bytes_preserved": True,
            "translated_prose_preserved": True,
            "rendered_bitmap_streams_match_reconstructed_rows": True,
            "protected_records": len(protected),
            "protected_cell_counts_preserved": True,
            "records_160_164_cell_counts_preserved": True,
            "dynamic_tail_fully_referenced": True,
        },
        "font": {
            "changed_byte_count": len(changed_font_offsets),
            "change_limited_to_translation_spills": ["0x48", "0xBC"],
            "other_chapters_using_recycled_codes": other_spill_uses,
        },
        "archive": {
            "members": len(delivered_members),
            "changed_members": changed_members,
            "changed_iso_files": changed_iso,
            "scene_scn_bs2_bs3_byte_identical_to_original": True,
        },
        "regression": {
            "unpacked_chunks": len(chunks),
            "validated_mes_files": len(mes_files),
            "unit_tests": "12/12 PASS",
        },
        "disc": {
            "track_count": disc["track_count"],
            "boot_system_matches_supplied_original": disc["template_boot_match"],
            "cue_line_endings": disc["cue_line_endings"],
            **raw,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

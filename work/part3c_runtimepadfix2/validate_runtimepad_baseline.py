#!/usr/bin/env python3
"""Validate the padding-corrected PART3C baseline before rebuilding a disc."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
OUTPUTS = PROJECT / "outputs"
V3 = OUTPUTS / "nostalgia1907_act3c_000_223_visualfix3"
V4 = OUTPUTS / "nostalgia1907_act3c_000_223_visualfix4"
ORIGINAL = (
    HERE.parent
    / "part3c_original_compare"
    / "original_part3c"
)
REPORT = HERE / "baseline_validation.json"

TEXT_BOUNDARY_LIMIT = 0x2600
POINTER_COUNT = 224
GLYPH_BYTES = 18
FORCED_PADDING = {116, 117, 118, 119, 120}
EXPECTED_TRAILING_BLANK_CELLS = {116: 6, 117: 7, 118: 5, 119: 9, 120: 2}

sys.path.insert(0, str(TOOLS))

from mes_probe import dynamic_glyph_index, parse_mes, segments_for  # noqa: E402
from profiled_text_builder import (  # noqa: E402
    audit_runtime_row_boundaries,
    infer_scn_floating_row_limits,
    validate_scn_floating_row_limits,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def normalized_prose(text: str) -> str:
    """Remove only row-end padding from manifest text."""
    return "\n".join(line.rstrip() for line in text.splitlines())


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Read one valid 224-record MES and return its records and glyph tail."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid PART3C MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def record_tokens(record: bytes) -> list[bytes]:
    """Split one terminated record into fixed/control/dynamic tokens."""
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


def controls(record: bytes) -> list[bytes]:
    """Return ordered non-glyph controls plus the record terminator."""
    return [
        token for token in record_tokens(record) if token[0] in (0xEE, 0xEF)
    ] + [b"\x00"]


def token_bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    """Resolve a MES glyph token to its exact bitmap."""
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


def trailing_blank_cells(record: bytes, font: bytes, tail: bytes) -> int:
    """Count final glyph cells whose exact bitmap contains no ink."""
    count = 0
    for token in reversed(record_tokens(record)):
        if token_bitmap(token, font, tail) != bytes(GLYPH_BYTES):
            break
        count += 1
    return count


def layouts(raw: dict[str, object]) -> dict[int, tuple[int, int]]:
    """Convert a manifest layout object to integer-keyed tuples."""
    return {
        int(index): (int(value["first"]), int(value["continuation"]))
        for index, value in raw.items()
    }


def member_hashes(root: Path) -> dict[str, str]:
    """Hash actual unpacked archive members, excluding tool manifests."""
    return {
        item.name: digest(item.read_bytes())
        for item in root.glob("*.unpacked")
    }


def main() -> None:
    """Run the baseline guards and emit a machine-readable report."""
    HERE.mkdir(parents=True, exist_ok=True)
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")

    v3_config = json.loads(
        (V3 / "PART3C_000_223_visualfix3_build_config.json").read_text(
            encoding="utf-8"
        )
    )
    v4_config = json.loads(
        (V4 / "PART3C_000_223_visualfix4_build_config.json").read_text(
            encoding="utf-8"
        )
    )
    v3_entries = {int(item["segment"]): item for item in v3_config["segments"]}
    v4_entries = {int(item["segment"]): item for item in v4_config["segments"]}
    expected_segments = set(range(POINTER_COUNT)) - {158}
    if set(v3_entries) != expected_segments or set(v4_entries) != expected_segments:
        raise ValueError("translated segment contract changed")

    prose_mismatches = [
        index
        for index in sorted(expected_segments)
        if normalized_prose(str(v3_entries[index]["text"]))
        != normalized_prose(str(v4_entries[index]["text"]))
    ]
    if prose_mismatches:
        raise ValueError(f"translated prose changed: {prose_mismatches}")

    v3_data, v3_info, v3_records, _ = load_mes(V3 / "PART3C.MES")
    v4_data, v4_info, v4_records, v4_tail = load_mes(V4 / "PART3C.MES")
    if v4_info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError(
            f"text split 0x{v4_info.split_offset:X} exceeds 0x{TEXT_BOUNDARY_LIMIT:X}"
        )
    for index, entry in v4_entries.items():
        if bytes.fromhex(str(entry["encoded"])) != v4_records[index]:
            raise ValueError(f"visualfix4 manifest diverges at record {index}")
    if v4_records[158] != v3_records[158]:
        raise ValueError("untranslated record 158 changed")
    for index, (before, after) in enumerate(zip(v3_records, v4_records)):
        if controls(before) != controls(after):
            raise ValueError(f"control tokens changed at record {index}")

    fixed_windows = set(v4_config["scn_fixed_window_padding"]["segments"])
    forced_padding = set(v4_config["profile_forced_final_row_padding"]["segments"])
    if forced_padding != FORCED_PADDING:
        raise ValueError(f"forced padding set changed: {sorted(forced_padding)}")
    protected = fixed_windows | forced_padding
    unpadded = [
        index for index in sorted(protected) if not v4_entries[index]["pad_final_row"]
    ]
    if unpadded:
        raise ValueError(f"protected records lack final-row padding: {unpadded}")
    no_pad = set(v4_config.get("no_pad_final_row_segments") or ())
    if protected & no_pad:
        raise ValueError(
            f"protected records remain in no-pad set: {sorted(protected & no_pad)}"
        )

    font = (V4 / "FIX_CODE.FNT").read_bytes()
    actual_blank_cells = {
        index: trailing_blank_cells(v4_records[index], font, v4_tail)
        for index in sorted(FORCED_PADDING)
    }
    if actual_blank_cells != EXPECTED_TRAILING_BLANK_CELLS:
        raise ValueError(
            f"forced records have wrong terminal padding: {actual_blank_cells}"
        )

    replacements = {
        index: normalized_prose(str(entry["text"]))
        for index, entry in v4_entries.items()
    }
    wrap_layouts = layouts(v4_config["wrap_layouts"])
    runtime_layouts = layouts(v4_config["runtime_row_layouts"])
    wrap_segments = set(v4_config["wrap_segments"])
    runtime_report = audit_runtime_row_boundaries(
        replacements,
        v4_config,
        wrap_layouts,
        runtime_layouts,
        wrap_segments,
    )
    if runtime_report["segment_count"] != 208 or runtime_report["row_count"] != 617:
        raise ValueError(f"runtime row totals changed: {runtime_report}")

    scn = V4 / "archive_candidate_unpacked" / "000_PART3C.SCN.unpacked"
    floating_limits = infer_scn_floating_row_limits(
        scn,
        POINTER_COUNT,
        set(v4_entries),
        window_text_subtypes=frozenset((0x27, 0x28)),
    )
    validate_scn_floating_row_limits(v4_config, floating_limits)
    if len(floating_limits) != 38:
        raise ValueError(f"floating-window count changed: {len(floating_limits)}")

    original_scn = (ORIGINAL / "000_PART3C.SCN.unpacked").read_bytes()
    if scn.read_bytes() != original_scn:
        raise ValueError("PART3C.SCN differs from the supplied original")
    original_members = member_hashes(ORIGINAL)
    v4_members = member_hashes(V4 / "archive_candidate_unpacked")
    if set(original_members) != set(v4_members):
        raise ValueError("PART3C archive inventory changed")
    changed_members = sorted(
        name
        for name in original_members
        if original_members[name] != v4_members[name]
    )
    if changed_members != ["001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected PART3C members changed: {changed_members}")

    report = {
        "status": "PASS",
        "translated_records": len(v4_entries),
        "translated_prose_equivalent_to_visualfix3": True,
        "control_tokens_identical_to_visualfix3": True,
        "untranslated_record_158_byte_identical": True,
        "mes": {
            "size": len(v4_data),
            "size_hex": f"0x{len(v4_data):X}",
            "sha256": digest(v4_data),
            "pointer_count": POINTER_COUNT,
            "text_split": v4_info.split_offset,
            "text_split_hex": f"0x{v4_info.split_offset:X}",
            "text_boundary_limit": TEXT_BOUNDARY_LIMIT,
            "text_boundary_limit_hex": f"0x{TEXT_BOUNDARY_LIMIT:X}",
            "text_headroom": TEXT_BOUNDARY_LIMIT - v4_info.split_offset,
            "whole_file_limit_enforced": False,
        },
        "padding": {
            "fixed_window_record_count": len(fixed_windows),
            "forced_records": sorted(forced_padding),
            "protected_record_count": len(protected),
            "all_protected_records_pad_final_row": True,
            "forced_terminal_blank_cells": actual_blank_cells,
        },
        "runtime_audit": {
            "wrapped_segments": runtime_report["segment_count"],
            "runtime_rows": runtime_report["row_count"],
            "floating_windows": len(floating_limits),
            "layout_counts": runtime_report["layout_counts"],
            "wrap_layout_counts": runtime_report["wrap_layout_counts"],
        },
        "archive": {
            "member_count": len(v4_members),
            "changed_from_original": changed_members,
            "scn_byte_identical_to_original": True,
        },
        "visualfix3_size": len(v3_data),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

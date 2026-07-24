#!/usr/bin/env python3
"""Independently verify the delivered PART3C runtime-padding test image."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
DELIVERY = WORKSPACE / "outputs" / "PART3C_runtimepadfix2_fresh"
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
V4 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
ORIGINAL = WORKSPACE / "work" / "part3c_original_compare" / "original_part3c"

MES_PATH = DELIVERY / "PART3C.MES"
FONT_PATH = DELIVERY / "FIX_CODE.FNT"
LZ_PATH = DELIVERY / "PART3C_runtimepadfix2.LZ"
ISO_PATH = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2.iso"
TRACK1_PATH = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2_Track1.bin"
TRACK2_PATH = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2_Track2.bin"
CUE_PATH = DELIVERY / "Nostalgia1907_Act3C_000_223_runtimepadfix2.cue"
ISO_EXTRACT = DELIVERY / "iso_extract"
UNPACKED = DELIVERY / "archive_candidate_unpacked"
REGRESSION = DELIVERY / "regression_full"
REPORT = DELIVERY / "final_verification.json"
CONFIG_PATH = V4 / "PART3C_000_223_visualfix4_build_config.json"

POINTER_COUNT = 224
TEXT_BOUNDARY_LIMIT = 0x2600
GLYPH_BYTES = 18
FORCED_PADDING = {116, 117, 118, 119, 120}
EXPECTED_BLANKS = {116: 6, 117: 7, 118: 5, 119: 9, 120: 2}
RAW_SECTOR_SIZE = 2352
DATA_SECTOR_SIZE = 2048
MODE1_DATA_OFFSET = 16

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)
from nostalgia1907 import inspect_standard_mega_cd_cue, read_iso_entries  # noqa: E402
from profiled_text_builder import (  # noqa: E402
    audit_runtime_row_boundaries,
    infer_scn_floating_row_limits,
    validate_scn_floating_row_limits,
)


def digest(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def file_facts(path: Path) -> dict[str, object]:
    """Return size and digest facts for one file."""
    data = path.read_bytes()
    return {"size": len(data), "sha256": digest(data)}


def normalized_prose(text: str) -> str:
    """Remove only structure-imposed padding at row ends."""
    return "\n".join(line.rstrip() for line in text.splitlines())


def load_mes(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    """Load and split one valid PART3C message table."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != POINTER_COUNT:
        raise ValueError(f"invalid 224-entry MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def record_tokens(record: bytes) -> list[bytes]:
    """Split a terminated MES record into glyph/control tokens."""
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    tokens: list[bytes] = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        token = record[offset : offset + width]
        if len(token) != width or offset + width > len(record) - 1:
            raise ValueError("incomplete MES token")
        tokens.append(token)
        offset += width
    return tokens


def controls(record: bytes) -> list[bytes]:
    """Return ordered line/page controls and the record terminator."""
    return [token for token in record_tokens(record) if token[0] in (0xEE, 0xEF)] + [
        b"\x00"
    ]


def token_bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    """Resolve one MES glyph token to the bitmap the game will display."""
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
    """Count blank glyph cells at the end of a record."""
    count = 0
    for token in reversed(record_tokens(record)):
        if token_bitmap(token, font, tail) != bytes(GLYPH_BYTES):
            break
        count += 1
    return count


def layouts(raw: dict[str, object]) -> dict[int, tuple[int, int]]:
    """Convert JSON layout keys and widths to integers."""
    return {
        int(index): (int(value["first"]), int(value["continuation"]))
        for index, value in raw.items()
    }


def member_hashes(root: Path) -> dict[str, str]:
    """Hash actual unpacked LZ members beneath one directory."""
    return {item.name: digest(item.read_bytes()) for item in root.glob("*.unpacked")}


def iso_payload_facts(path: Path) -> dict[str, tuple[int, str]]:
    """Hash all ISO file payloads."""
    result: dict[str, tuple[int, str]] = {}
    with path.open("rb") as stream:
        for entry in read_iso_entries(path):
            if entry.is_dir:
                continue
            stream.seek(entry.extent * DATA_SECTOR_SIZE)
            payload = stream.read(entry.size)
            result[entry.path] = (entry.size, digest(payload))
    return result


def verify_raw_payload(raw_path: Path, iso_path: Path) -> dict[str, object]:
    """Verify that every raw Track 1 user-data sector equals the ISO."""
    if raw_path.stat().st_size % RAW_SECTOR_SIZE:
        raise ValueError("Track 1 is not sector aligned")
    if iso_path.stat().st_size % DATA_SECTOR_SIZE:
        raise ValueError("ISO is not sector aligned")
    raw_sectors = raw_path.stat().st_size // RAW_SECTOR_SIZE
    iso_sectors = iso_path.stat().st_size // DATA_SECTOR_SIZE
    if raw_sectors != iso_sectors:
        raise ValueError(f"Track 1/ISO sector mismatch: {raw_sectors} != {iso_sectors}")

    raw_user_hash = hashlib.sha256()
    iso_hash = hashlib.sha256()
    with raw_path.open("rb") as raw, iso_path.open("rb") as iso:
        for sector in range(iso_sectors):
            raw_sector = raw.read(RAW_SECTOR_SIZE)
            iso_sector = iso.read(DATA_SECTOR_SIZE)
            if len(raw_sector) != RAW_SECTOR_SIZE or len(iso_sector) != DATA_SECTOR_SIZE:
                raise ValueError(f"short read while checking sector {sector}")
            user_data = raw_sector[
                MODE1_DATA_OFFSET : MODE1_DATA_OFFSET + DATA_SECTOR_SIZE
            ]
            if user_data != iso_sector:
                raise ValueError(f"Track 1 user data differs at sector {sector}")
            raw_user_hash.update(user_data)
            iso_hash.update(iso_sector)
    if raw_user_hash.digest() != iso_hash.digest():
        raise ValueError("Track 1 user-data digest differs from ISO")
    return {
        "sectors": iso_sectors,
        "all_user_data_sectors_match_iso": True,
        "user_data_sha256": raw_user_hash.hexdigest().upper(),
    }


def main() -> None:
    """Run the independent delivery audit and emit a JSON report."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    v3_config = json.loads(
        (V3 / "PART3C_000_223_visualfix3_build_config.json").read_text(
            encoding="utf-8"
        )
    )
    entries = {int(item["segment"]): item for item in config["segments"]}
    v3_entries = {int(item["segment"]): item for item in v3_config["segments"]}
    expected_translated = set(range(POINTER_COUNT)) - {158}
    if set(entries) != expected_translated or set(v3_entries) != expected_translated:
        raise ValueError("translated-record inventory changed")
    prose_mismatches = [
        index
        for index in sorted(expected_translated)
        if normalized_prose(str(entries[index]["text"]))
        != normalized_prose(str(v3_entries[index]["text"]))
    ]
    if prose_mismatches:
        raise ValueError(f"translated prose changed: {prose_mismatches}")

    data, info, records, tail = load_mes(MES_PATH)
    _, _, v3_records, _ = load_mes(V3 / "PART3C.MES")
    if info.split_offset > TEXT_BOUNDARY_LIMIT:
        raise ValueError(
            f"text split 0x{info.split_offset:X} exceeds 0x{TEXT_BOUNDARY_LIMIT:X}"
        )
    for index, entry in entries.items():
        if bytes.fromhex(str(entry["encoded"])) != records[index]:
            raise ValueError(f"delivery MES diverges from manifest at record {index}")
    if records[158] != v3_records[158]:
        raise ValueError("untranslated record 158 changed")
    for index, (before, after) in enumerate(zip(v3_records, records)):
        if controls(before) != controls(after):
            raise ValueError(f"control tokens changed at record {index}")

    fixed_windows = set(config["scn_fixed_window_padding"]["segments"])
    forced = set(config["profile_forced_final_row_padding"]["segments"])
    protected = fixed_windows | forced
    if forced != FORCED_PADDING:
        raise ValueError(f"forced-padding contract changed: {sorted(forced)}")
    unpadded = [
        index for index in sorted(protected) if not entries[index]["pad_final_row"]
    ]
    if unpadded:
        raise ValueError(f"protected records lack final-row padding: {unpadded}")
    no_pad = set(config.get("no_pad_final_row_segments") or ())
    if protected & no_pad:
        raise ValueError(f"protected records appear in no-pad set: {protected & no_pad}")

    font = FONT_PATH.read_bytes()
    actual_blanks = {
        index: trailing_blank_cells(records[index], font, tail)
        for index in sorted(FORCED_PADDING)
    }
    if actual_blanks != EXPECTED_BLANKS:
        raise ValueError(f"terminal padding changed: {actual_blanks}")

    checked_units = 0
    bitmap_mismatches: list[dict[str, object]] = []
    transform = str(config["glyph_transform"])
    for entry in config["segments"]:
        segment = int(entry["segment"])
        for position, unit in enumerate(entry["units"]):
            expected = transform_glyph_bytes(
                render_generated_unit(str(unit["style"]), str(unit["unit"])),
                transform,
            )
            if unit["encoding"] == "fixed":
                code = int(str(unit["code"]), 0)
                start = (code - 1) * GLYPH_BYTES
                actual = font[start : start + GLYPH_BYTES]
            elif unit["encoding"] == "dynamic":
                start = int(unit["dynamic_index"]) * GLYPH_BYTES
                actual = tail[start : start + GLYPH_BYTES]
            else:
                raise ValueError(f"unknown manifest encoding: {unit!r}")
            checked_units += 1
            if actual != expected:
                bitmap_mismatches.append(
                    {"segment": segment, "position": position, "unit": unit["unit"]}
                )
    if bitmap_mismatches:
        raise ValueError(
            f"{len(bitmap_mismatches)} delivered glyph bitmaps mismatch; "
            f"first={bitmap_mismatches[0]}"
        )

    replacements = {
        index: normalized_prose(str(entry["text"])) for index, entry in entries.items()
    }
    runtime = audit_runtime_row_boundaries(
        replacements,
        config,
        layouts(config["wrap_layouts"]),
        layouts(config["runtime_row_layouts"]),
        set(config["wrap_segments"]),
    )
    if runtime["segment_count"] != 208 or runtime["row_count"] != 617:
        raise ValueError(f"runtime row totals changed: {runtime}")

    scn_path = UNPACKED / "000_PART3C.SCN.unpacked"
    floating = infer_scn_floating_row_limits(
        scn_path,
        POINTER_COUNT,
        set(entries),
        window_text_subtypes=frozenset((0x27, 0x28)),
    )
    validate_scn_floating_row_limits(config, floating)
    if len(floating) != 38:
        raise ValueError(f"floating-window count changed: {len(floating)}")

    original_members = member_hashes(ORIGINAL)
    delivered_members = member_hashes(UNPACKED)
    if set(original_members) != set(delivered_members):
        raise ValueError("PART3C member inventory changed")
    changed_members = sorted(
        name
        for name in original_members
        if original_members[name] != delivered_members[name]
    )
    if changed_members != ["001_PART3C.MES.unpacked"]:
        raise ValueError(f"unexpected PART3C members changed: {changed_members}")
    if scn_path.read_bytes() != (ORIGINAL / scn_path.name).read_bytes():
        raise ValueError("PART3C.SCN differs from supplied original")

    extracted_lz = ISO_EXTRACT / "PART3C.LZ"
    extracted_font = ISO_EXTRACT / "FIX_CODE.FNT"
    if extracted_lz.read_bytes() != LZ_PATH.read_bytes():
        raise ValueError("ISO-extracted PART3C.LZ differs from delivered LZ")
    if extracted_font.read_bytes() != FONT_PATH.read_bytes():
        raise ValueError("ISO-extracted FIX_CODE.FNT differs from delivered font")
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != data:
        raise ValueError("delivered LZ does not contain delivered MES")

    source_iso_files = iso_payload_facts(
        V3 / "Nostalgia1907_Act3C_000_223_visualfix3.iso"
    )
    delivered_iso_files = iso_payload_facts(ISO_PATH)
    if set(source_iso_files) != set(delivered_iso_files):
        raise ValueError("ISO file inventory changed")
    changed_iso_files = sorted(
        name
        for name in source_iso_files
        if source_iso_files[name] != delivered_iso_files[name]
    )
    if changed_iso_files != ["FIX_CODE.FNT", "PART3C.LZ"]:
        raise ValueError(f"unexpected ISO files changed: {changed_iso_files}")

    regression_chunks = [
        member
        for lz_path in ISO_EXTRACT.glob("*.LZ")
        for member in (REGRESSION / lz_path.stem).rglob("*.unpacked")
    ]
    regression_mes = [
        path
        for path in REGRESSION.rglob("*.unpacked")
        if path.name.upper().endswith(".MES.UNPACKED")
    ]
    if len(regression_chunks) != 564 or len(regression_mes) != 21:
        raise ValueError(
            "full regression output changed: "
            f"chunks={len(regression_chunks)}, MES={len(regression_mes)}"
        )
    for mes_path in regression_mes:
        mes_info, _ = parse_mes(mes_path.read_bytes(), mes_path)
        if not mes_info.valid:
            raise ValueError(f"invalid regression MES: {mes_path}")

    disc = inspect_standard_mega_cd_cue(
        CUE_PATH,
        V3 / "Nostalgia1907_Act3C_000_223_visualfix3_Track1.bin",
    )
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError(f"disc/CUE contract failed: {disc}")
    raw_payload = verify_raw_payload(TRACK1_PATH, ISO_PATH)

    report = {
        "status": "PASS",
        "delivery": {
            "mes": file_facts(MES_PATH),
            "font": file_facts(FONT_PATH),
            "lz": file_facts(LZ_PATH),
            "iso": file_facts(ISO_PATH),
            "track_1": file_facts(TRACK1_PATH),
            "track_2": file_facts(TRACK2_PATH),
            "cue": file_facts(CUE_PATH),
        },
        "mes_contract": {
            "pointer_count": info.pointer_count,
            "translated_records": len(entries),
            "translated_prose_identical_to_visualfix3": True,
            "control_tokens_identical_to_visualfix3": True,
            "untranslated_record_158_byte_identical": True,
            "whole_size": len(data),
            "whole_size_hex": f"0x{len(data):X}",
            "text_split": info.split_offset,
            "text_split_hex": f"0x{info.split_offset:X}",
            "text_boundary_limit": TEXT_BOUNDARY_LIMIT,
            "text_boundary_limit_hex": f"0x{TEXT_BOUNDARY_LIMIT:X}",
            "text_headroom": TEXT_BOUNDARY_LIMIT - info.split_offset,
        },
        "padding_contract": {
            "fixed_window_records": len(fixed_windows),
            "forced_records": sorted(forced),
            "protected_records": len(protected),
            "all_protected_records_padded": True,
            "forced_terminal_blank_cells": actual_blanks,
        },
        "glyph_contract": {
            "checked_unit_occurrences": checked_units,
            "mismatches": len(bitmap_mismatches),
            "delivered_font_and_dynamic_tail_match_manifest": True,
        },
        "runtime_contract": {
            "wrapped_segments": runtime["segment_count"],
            "runtime_rows": runtime["row_count"],
            "floating_windows": len(floating),
        },
        "archive_contract": {
            "members": len(delivered_members),
            "changed_from_original": changed_members,
            "scn_byte_identical_to_original": True,
            "iso_embedded_lz_exact": True,
            "iso_embedded_font_exact": True,
            "iso_files_changed_from_visualfix3": changed_iso_files,
        },
        "full_regression": {
            "unpacked_chunks": len(regression_chunks),
            "validated_mes_files": len(regression_mes),
        },
        "disc_contract": {
            "track_count": disc["track_count"],
            "cue_line_endings": disc["cue_line_endings"],
            "template_boot_match": disc["template_boot_match"],
            "track_1_sectors": disc["track_1"]["sectors"],
            "track_2_sectors": disc["track_2"]["sectors"],
            **raw_payload,
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

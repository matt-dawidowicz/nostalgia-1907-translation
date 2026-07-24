#!/usr/bin/env python3
"""Independently verify the complete PART3C transitionfix10 release candidate."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
ORIGINAL_ROOT = WORKSPACE / "work" / "part3c_original_compare"
ORIGINAL_ARCHIVE = ORIGINAL_ROOT / "original_part3c"
ORIGINAL_LZ = ORIGINAL_ROOT / "original_extract" / "PART3C.LZ"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
SOURCE = WORKSPACE / "outputs" / "PART3C_slotpreservefix7_fresh"
FINAL = WORKSPACE / "outputs" / "PART3C_transitionfix10_full_fresh"
MES = FINAL / "PART3C.MES"
SCN = FINAL / "PART3C.SCN"
FONT = FINAL / "FIX_CODE.FNT"
LZ = FINAL / "PART3C_transitionfix10.LZ"
ISO = FINAL / "Nostalgia1907_Act3C_transitionfix10_full.iso"
TRACK1 = FINAL / "Nostalgia1907_Act3C_transitionfix10_full_Track1.bin"
TRACK2 = FINAL / "Nostalgia1907_Act3C_transitionfix10_full_Track2.bin"
CUE = FINAL / "Nostalgia1907_Act3C_transitionfix10_full.cue"
UNPACKED = FINAL / "archive_candidate_unpacked"
REGRESSION = FINAL / "regression_full"
REPORT = FINAL / "final_verification.json"
MES_REPORT = HERE / "transitionfix10_mes_report.json"
REFLOW_REPORT = HERE / "transitionfix10_row_reflows.json"
SOURCE_MES = HERE / "PART3C_rowparityfix6.MES"
SOURCE_FONT = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh" / "FIX_CODE.FNT"
V4_CONFIG = (
    PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
    / "PART3C_000_223_visualfix4_build_config.json"
)

GLYPH_BYTES = 18
WHOLE_MES_LIMIT = 0x3FFF
TEXT_SPLIT_LIMIT = 0x2600
EXPECTED_CHANGED = [14, 83, 93, 110, 136, 146, 149, 154, 157, 159, 162]
RECYCLED = {136, 294, 302, 333, 352, 364, 367, 371, 373, 376}
JOINT_83_UNITS = [
    ("I", "packed"),
    ("r", "packed"),
    ("yu", "packed"),
    ("'s", "packed"),
    (" t", "packed-literal"),
    ("r", "packed"),
    ("ue", "packed"),
]

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(WORKSPACE / "work" / "part3c_globalfontfix3"))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)
from nostalgia1907 import inspect_standard_mega_cd_cue, read_lz_entries  # noqa: E402
from verify_final_globalfontfix3 import (  # noqa: E402
    iso_payload_facts,
    member_hashes,
    verify_raw_payload,
)


def digest(data: bytes) -> str:
    """Return uppercase SHA-256."""
    return hashlib.sha256(data).hexdigest().upper()


def facts(path: Path) -> dict[str, object]:
    """Return file size and SHA-256."""
    data = path.read_bytes()
    return {"size": len(data), "sha256": digest(data)}


def tokenize(record: bytes) -> list[bytes]:
    """Tokenize a record and reject embedded or missing terminators."""
    if not record or record[-1] != 0 or record.count(0) != 1:
        raise ValueError("record does not contain exactly one final terminator")
    result = []
    offset = 0
    while offset < len(record) - 1:
        width = 2 if record[offset] >= 0xF0 else 1
        token = record[offset : offset + width]
        if len(token) != width or (width == 2 and token[1] == 0):
            raise ValueError("invalid dynamic/control token")
        result.append(token)
        offset += width
    return result


def load_mes(path: Path) -> tuple[bytes, object, list[int], list[bytes], bytes]:
    """Load one valid monotonic 224-record MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != 224:
        raise ValueError(f"invalid PART3C MES: {path}")
    if any(left >= right for left, right in zip(pointers, pointers[1:])):
        raise ValueError("MES pointers are not strictly increasing")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    for record in records:
        tokenize(record)
    tail = data[info.split_offset :]
    if len(tail) % GLYPH_BYTES:
        raise ValueError("dynamic tail is not 18-byte aligned")
    return data, info, pointers, records, tail


def bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    """Resolve a text token, returning None for non-glyph controls."""
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
            raise ValueError(f"dynamic reference {index} is outside the tail")
        return value
    return None


def controls(record: bytes, font: bytes, tail: bytes) -> list[bytes]:
    """Return non-glyph controls and the terminator."""
    result = [token for token in tokenize(record) if bitmap(token, font, tail) is None]
    result.append(b"\0")
    return result


def rendered(style: str, text: str) -> bytes:
    """Render one generated unit in stored orientation."""
    return transform_glyph_bytes(render_generated_unit(style, text), "prerot-cw")


def first_high_f1(records: list[bytes]) -> int | None:
    """Return the first record using an F1 payload at or above 0x80."""
    for record_index, record in enumerate(records):
        if any(
            len(token) == 2 and token[0] == 0xF1 and token[1] >= 0x80
            for token in tokenize(record)
        ):
            return record_index
    return None


def main() -> None:
    """Run content, geometry, archive, ISO, sector, and tooling guards."""
    mes_report = json.loads(MES_REPORT.read_text(encoding="utf-8"))
    reflow_report = json.loads(REFLOW_REPORT.read_text(encoding="utf-8"))
    reflows = {
        (int(item["record"]), int(item["row"])): item
        for item in reflow_report["candidates"]
    }
    data, info, pointers, records, tail = load_mes(MES)
    source_data, source_info, _, source_records, source_tail = load_mes(SOURCE_MES)
    font = FONT.read_bytes()
    source_font = SOURCE_FONT.read_bytes()

    if len(data) > WHOLE_MES_LIMIT or info.split_offset > TEXT_SPLIT_LIMIT:
        raise ValueError("MES crossed a hard runtime boundary")
    if len(data) != 0x3FE2 or len(data) != mes_report["mes"]["output_size"]:
        raise ValueError("MES size drifted from the reviewed candidate")
    if len(tail) != len(source_tail) or len(tail) // GLYPH_BYTES != 400:
        raise ValueError("dynamic tail size/glyph count changed")
    if font != source_font:
        raise ValueError("global fixed font changed")

    changed = [
        index for index, (before, after) in enumerate(zip(source_records, records))
        if before != after
    ]
    if changed != EXPECTED_CHANGED:
        raise ValueError(f"unexpected changed records: {changed}")
    if any(records[index] != source_records[index] for index in range(112, 124)):
        raise ValueError("protected records 112-123 changed")
    if any(records[index] != source_records[index] for index in range(163, 224)):
        raise ValueError("full translation records 163-223 changed")
    for index in changed:
        if controls(records[index], font, tail) != controls(
            source_records[index], source_font, source_tail
        ):
            raise ValueError(f"control stream changed at record {index}")

    # Verify every safe row reflow renders the exact declared prose at the same width.
    reflow_checks = []
    for item in mes_report["safe_reflows"]:
        record_index = int(item["record"])
        row = int(item["row"])
        source_item = reflows[(record_index, row)]
        width = int(source_item["row_width"])
        start = row * width
        row_tokens = tokenize(records[record_index])[start : start + width]
        if len(row_tokens) != width:
            raise ValueError(f"short reflow row at record {record_index}")
        if record_index == 83:
            expected_units = JOINT_83_UNITS
            padding = 1
        else:
            expected_units = [
                (str(unit["text"]), str(unit["style"]))
                for unit in source_item["units"]
            ]
            padding = int(source_item["padding"])
        if "".join(text for text, _ in expected_units) != str(source_item["prose"]):
            raise ValueError(f"reflow prose mismatch at record {record_index}")
        expected_bitmaps = [rendered(style, text) for text, style in expected_units]
        expected_bitmaps.extend([bytes(GLYPH_BYTES)] * padding)
        actual_bitmaps = [bitmap(token, font, tail) for token in row_tokens]
        if actual_bitmaps != expected_bitmaps or len(expected_bitmaps) != width:
            raise ValueError(f"reflow rendering mismatch at record {record_index}")
        if len(tokenize(records[record_index])) != len(tokenize(source_records[record_index])):
            raise ValueError(f"reflow changed record cell count at {record_index}")
        reflow_checks.append(
            {"record": record_index, "row": row, "width": width, "prose": source_item["prose"]}
        )

    # Verify the two proven runtime invariants directly.
    if records[159][:2] != b"\x01\x01" or records[159][2:] != source_records[159]:
        raise ValueError("Captain Room retail padding contract failed")
    if bitmap(b"\x01", font, tail) != bytes(GLYPH_BYTES):
        raise ValueError("title padding token is no longer blank")
    record_162_report = mes_report["record_162"]
    expected_162 = []
    prose_rows = []
    for row in record_162_report["rows"]:
        prose_rows.append(str(row["text"]))
        expected_162.extend(rendered("packed", str(item["unit"])) for item in row["units"])
        expected_162.extend([bytes(GLYPH_BYTES)] * int(row["padding_cells"]))
    actual_162 = [bitmap(token, font, tail) for token in tokenize(records[162])]
    if actual_162 != expected_162 or len(actual_162) != 32:
        raise ValueError("record 162 is not the reviewed four-by-eight rendering")
    config_162 = next(
        str(item["text"])
        for item in json.loads(V4_CONFIG.read_text(encoding="utf-8"))["segments"]
        if int(item["segment"]) == 162
    )
    if " ".join(config_162.split()) != " ".join(prose_rows):
        raise ValueError("record 162 translated prose changed")
    if any(
        len(token) == 2 and token[0] == 0xF1 and token[1] >= 0x80
        for token in tokenize(records[162])
    ):
        raise ValueError("record 162 crossed the guarded F1 payload boundary")
    if first_high_f1(records) != first_high_f1(source_records):
        raise ValueError("first high-F1 record moved earlier")

    # Verify dynamic-slot ownership and byte-level tail scope.
    refs: dict[int, set[int]] = {index: set() for index in RECYCLED}
    all_refs: Counter[int] = Counter()
    for record_index, record in enumerate(records):
        for token in tokenize(record):
            if len(token) != 2:
                continue
            index = dynamic_glyph_index(token[0], token[1])
            if index is not None:
                all_refs[index] += 1
                if index in refs:
                    refs[index].add(record_index)
    if set(all_refs) != set(range(400)):
        raise ValueError("dynamic tail contains unreferenced or missing glyph slots")
    if any(users != {162} for users in refs.values()):
        raise ValueError(f"recycled slot escaped record 162: {refs}")
    changed_tail_slots = {
        index
        for index in range(400)
        if tail[index * GLYPH_BYTES : (index + 1) * GLYPH_BYTES]
        != source_tail[index * GLYPH_BYTES : (index + 1) * GLYPH_BYTES]
    }
    if changed_tail_slots != RECYCLED:
        raise ValueError(f"unexpected dynamic-tail changes: {changed_tail_slots}")

    original_scn = (ORIGINAL_ARCHIVE / "000_PART3C.SCN.unpacked").read_bytes()
    final_scn = SCN.read_bytes()
    if final_scn != original_scn:
        raise ValueError("PART3C.SCN is not byte-identical to retail")
    critical_chain = bytes.fromhex(
        "24 02 0E 0E 0C 27 00 A1 "
        "24 02 0E 0E 0C 27 00 A2 "
        "24 02 0E 0E 0C 27 00 A3 "
        "24 02 0E 0E 0C 27 00 A4"
    )
    if final_scn[0x0B13 : 0x0B33] != critical_chain:
        raise ValueError("critical 160-163 window chain changed")
    if [len(tokenize(records[index])) for index in range(160, 164)] != [32, 32, 32, 32]:
        raise ValueError("critical window chain is not four rows by eight cells")

    original_entries = read_lz_entries(ORIGINAL_LZ)
    output_entries = read_lz_entries(LZ)
    if len(output_entries) != 52:
        raise ValueError("archive member count changed")
    if [(item.name, item.offset) for item in output_entries] != [
        (item.name, item.offset) for item in original_entries
    ]:
        raise ValueError("archive names or offsets differ from retail")
    if LZ.stat().st_size != ORIGINAL_LZ.stat().st_size:
        raise ValueError("archive byte length differs from retail")
    original_members = member_hashes(ORIGINAL_ARCHIVE)
    output_members = member_hashes(UNPACKED)
    changed_members = sorted(
        name for name in original_members if original_members[name] != output_members[name]
    )
    if set(original_members) != set(output_members) or changed_members != [
        "001_PART3C.MES.unpacked"
    ]:
        raise ValueError(f"archive scope changed: {changed_members}")
    if (UNPACKED / "001_PART3C.MES.unpacked").read_bytes() != data:
        raise ValueError("archive MES round trip failed")
    protected_members = [
        "002_SCREEN0.BS.unpacked",
        "003_SCREEN1.BS.unpacked",
        "016_120.BG.unpacked",
        "017_121.BG.unpacked",
        "018_122.BG.unpacked",
    ]
    for name in protected_members:
        if (UNPACKED / name).read_bytes() != (ORIGINAL_ARCHIVE / name).read_bytes():
            raise ValueError(f"protected member changed: {name}")

    source_iso = iso_payload_facts(
        SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7.iso"
    )
    output_iso = iso_payload_facts(ISO)
    changed_iso = sorted(name for name in source_iso if source_iso[name] != output_iso[name])
    if set(source_iso) != set(output_iso) or changed_iso != ["PART3C.LZ"]:
        raise ValueError(f"ISO scope changed: {changed_iso}")

    chapter_roots = [
        path
        for path in REGRESSION.iterdir()
        if path.is_dir()
        and path.name not in {"reflow_source_unpack", "reflow_rebuilt_unpack"}
    ]
    chunks = [path for root in chapter_roots for path in root.rglob("*.unpacked")]
    mes_files = [
        path
        for path in REGRESSION.rglob("*.unpacked")
        if path.name.upper().endswith(".MES.UNPACKED")
    ]
    if len(chunks) != 564 or len(mes_files) != 21:
        raise ValueError("full regression inventory changed")
    for path in mes_files:
        item, _ = parse_mes(path.read_bytes(), path)
        if not item.valid:
            raise ValueError(f"invalid regression MES: {path}")
    if (REGRESSION / "PART3C" / "001_PART3C.MES.unpacked").read_bytes() != data:
        raise ValueError("regression PART3C MES differs from delivery")

    test_stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(TOOLS), pattern="test_*.py")
    test_count = suite.countTestCases()
    test_result = unittest.TextTestRunner(stream=test_stream, verbosity=1).run(suite)
    if test_count != 12 or not test_result.wasSuccessful():
        raise ValueError(f"tool unit tests failed: {test_stream.getvalue()}")

    disc = inspect_standard_mega_cd_cue(CUE, ORIGINAL_TRACK1)
    if (
        disc["track_count"] != 2
        or not disc["template_boot_match"]
        or disc["cue_line_endings"] != "CRLF"
    ):
        raise ValueError("disc boot/geometry/CUE contract failed")
    raw = verify_raw_payload(TRACK1, ISO)
    source_track2 = SOURCE / "Nostalgia1907_Act3C_000_223_slotpreservefix7_Track2.bin"
    if TRACK2.read_bytes() != source_track2.read_bytes():
        raise ValueError("audio track changed")

    report = {
        "status": "PASS",
        "release_candidate": True,
        "delivery": {
            "mes": facts(MES),
            "scn": facts(SCN),
            "font": facts(FONT),
            "lz": facts(LZ),
            "iso": facts(ISO),
            "track_1": facts(TRACK1),
            "track_2": facts(TRACK2),
            "cue": facts(CUE),
        },
        "mes_structure": {
            "pointer_count": len(pointers),
            "strictly_increasing_pointers": True,
            "records_with_one_final_terminator": len(records),
            "size": len(data),
            "size_hex": f"0x{len(data):X}",
            "hard_limit": WHOLE_MES_LIMIT,
            "headroom": WHOLE_MES_LIMIT - len(data),
            "text_split": info.split_offset,
            "text_split_limit": TEXT_SPLIT_LIMIT,
            "dynamic_glyphs": len(tail) // GLYPH_BYTES,
            "all_dynamic_slots_referenced": True,
        },
        "content_guards": {
            "changed_records": changed,
            "all_224_records_present": True,
            "records_112_123_byte_identical": True,
            "records_163_223_byte_identical": True,
            "control_streams_preserved": True,
            "safe_reflows": reflow_checks,
            "record_159_retail_padding_restored": True,
            "record_162_prose_preserved": True,
            "record_162_geometry": "4 rows x 8 cells",
            "critical_records_160_163_each_32_cells": True,
            "record_162_below_high_f1_boundary": True,
            "first_high_f1_record_unchanged": first_high_f1(records),
        },
        "runtime_assets": {
            "scn_byte_identical_to_retail": True,
            "critical_chain_byte_identical_at_0x0B13": True,
            "fixed_font_byte_identical": True,
            "recycled_dynamic_slots": sorted(RECYCLED),
            "tail_changed_only_in_recycled_slots": True,
            "recycled_slots_owned_only_by_record_162": True,
            "protected_members_byte_identical_to_retail": protected_members,
        },
        "archive": {
            "members": len(output_entries),
            "names_and_offsets_match_retail": True,
            "byte_length_matches_retail": True,
            "changed_members_from_retail": changed_members,
        },
        "iso": {"changed_files": changed_iso},
        "regression": {
            "unpacked_chunks": len(chunks),
            "validated_mes_files": len(mes_files),
            "unit_tests": f"{test_count}/{test_count} PASS",
        },
        "disc": {
            "boot_system_matches_supplied_original": True,
            "audio_track_byte_identical": True,
            "cue_line_endings": disc["cue_line_endings"],
            **raw,
        },
        "source_mes_sha256": digest(source_data),
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

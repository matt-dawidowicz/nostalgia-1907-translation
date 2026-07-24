#!/usr/bin/env python3
"""Package translated STAFF credits into a fresh guarded BIN/CUE."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"

SOURCE = WORKSPACE / "outputs" / "Nostalgia1907_Act4_firstpass_speakerfix"
SOURCE_ISO = SOURCE / "Nostalgia1907_Act4_firstpass_speakerfix.iso"
SOURCE_TRACK1 = SOURCE / "Nostalgia1907_Act4_firstpass_speakerfix_Track1.bin"
SOURCE_TRACK2 = SOURCE / "Nostalgia1907_Act4_firstpass_speakerfix_Track2.bin"
SOURCE_REPORT = SOURCE / "final_verification.json"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)

STAFF_SOURCE_LZ = PROJECT / "work" / "nostalgia1907" / "iso_files" / "STAFF.LZ"
STAFF_SOURCE_ARCHIVE = PROJECT / "work" / "nostalgia1907" / "unpacked" / "STAFF"
STAFF_MES = HERE / "built" / "STAFF.MES"
STAFF_SCN = HERE / "built" / "STAFF.SCN"
STAFF_MANIFEST = HERE / "built" / "STAFF_manifest.json"

DELIVERY = WORKSPACE / "outputs" / "Nostalgia1907_Act4_firstpass_credits"
ARCHIVE_AUDIT = DELIVERY / "archive_audit"
REGRESSION = DELIVERY / "regression"
OUTPUT_LZ = DELIVERY / "STAFF_firstpass.LZ"
OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act4_firstpass_credits.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act4_firstpass_credits_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act4_firstpass_credits_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act4_firstpass_credits.cue"
OUTPUT_REPORT = DELIVERY / "final_verification.json"
OUTPUT_NOTES = DELIVERY / "TEST_NOTES.md"

SCRIPT_ARCHIVES = {
    "START", "PART1A", "PART1B", "PART1C", "PART1D", "PART2A", "PART2B",
    "PART2C", "PART2D", "PART2E", "PART2F", "PART3A", "PART3B", "PART3B_",
    "PART3C", "PART4A", "PART4B", "PART4C", "STAFF",
}
PATCHED_MES = {
    "PART3C": SOURCE / "PART3C.MES",
    "PART4A": WORKSPACE / "work" / "act4_translation" / "built" / "PART4A" / "PART4A.MES",
    "PART4B": WORKSPACE / "work" / "act4_translation" / "built" / "PART4B" / "PART4B.MES",
    "PART4C": WORKSPACE / "work" / "act4_translation" / "built" / "PART4C" / "PART4C.MES",
    "STAFF": STAFF_MES,
}
PATCHED_COUNTS = {"PART3C": 224, "PART4A": 63, "PART4B": 293, "PART4C": 60, "STAFF": 62}

sys.path.insert(0, str(TOOLS))

from mes_probe import parse_mes, segments_for  # noqa: E402
from nostalgia1907 import (  # noqa: E402
    extract_iso,
    inspect_standard_mega_cd_cue,
    patch_iso_replacements,
    raw_mode1_2352_from_iso,
    raw_mode1_2352_to_iso,
    read_iso_entries,
    read_lz_entries,
    repack_lz_compressed_slots,
    unpack_lz,
    write_standard_mega_cd_cue,
)


def digest(data: bytes) -> str:
    """Return uppercase SHA-256."""
    return hashlib.sha256(data).hexdigest().upper()


def facts(path: Path) -> dict[str, object]:
    """Return file size and SHA-256."""
    data = path.read_bytes()
    return {"size": len(data), "sha256": digest(data)}


def strict_mes(path: Path, expected_count: int | None = None) -> dict[str, object]:
    """Validate MES pointers, records, terminators, and dynamic-bank alignment."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid:
        raise ValueError(f"invalid MES: {path}")
    if expected_count is not None and info.pointer_count != expected_count:
        raise ValueError(f"unexpected MES count for {path}: {info.pointer_count}")
    if any(left >= right for left, right in zip(pointers, pointers[1:])):
        raise ValueError(f"non-monotonic MES pointers: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    for index, record in enumerate(records):
        if not record or record[-1] != 0 or record.count(0) != 1:
            raise ValueError(f"{path.name} record {index} lacks one final terminator")
    tail = data[info.split_offset :]
    if len(tail) % 18:
        raise ValueError(f"{path.name} dynamic bank is not 18-byte aligned")
    return {
        "records": len(records),
        "size": len(data),
        "split_offset": info.split_offset,
        "dynamic_glyphs": len(tail) // 18,
        "sha256": digest(data),
    }


def member_hashes(directory: Path) -> dict[str, str]:
    """Hash unpacked LZ members by archive name."""
    result: dict[str, str] = {}
    for path in directory.glob("*.unpacked"):
        member = path.name.split("_", 1)[1].removesuffix(".unpacked")
        result[member] = digest(path.read_bytes())
    return result


def iso_hashes(path: Path) -> dict[str, tuple[int, str]]:
    """Hash every ISO file without extracting it."""
    data = path.read_bytes()
    result: dict[str, tuple[int, str]] = {}
    for entry in read_iso_entries(path):
        if entry.is_dir:
            continue
        start = entry.extent * 2048
        payload = data[start : start + entry.size]
        result[entry.path] = (entry.size, digest(payload))
    return result


def build_staff_lz() -> dict[str, object]:
    """Repack only STAFF.MES into unchanged retail compressed slots."""
    repack_lz_compressed_slots(STAFF_SOURCE_LZ, OUTPUT_LZ, {"STAFF.MES": STAFF_MES})
    source_entries = read_lz_entries(STAFF_SOURCE_LZ)
    output_entries = read_lz_entries(OUTPUT_LZ)
    if [(x.name, x.offset) for x in source_entries] != [(x.name, x.offset) for x in output_entries]:
        raise ValueError("STAFF archive names or offsets changed")
    if OUTPUT_LZ.stat().st_size != STAFF_SOURCE_LZ.stat().st_size:
        raise ValueError("STAFF archive size changed")
    unpack_lz(OUTPUT_LZ, ARCHIVE_AUDIT)
    if (ARCHIVE_AUDIT / "001_STAFF.MES.unpacked").read_bytes() != STAFF_MES.read_bytes():
        raise ValueError("STAFF MES archive round trip failed")
    if (ARCHIVE_AUDIT / "000_STAFF.SCN.unpacked").read_bytes() != STAFF_SCN.read_bytes():
        raise ValueError("STAFF SCN archive round trip failed")
    before = member_hashes(STAFF_SOURCE_ARCHIVE)
    after = member_hashes(ARCHIVE_AUDIT)
    changed = sorted(name for name in before if before[name] != after.get(name))
    if set(before) != set(after) or changed != ["STAFF.MES"]:
        raise ValueError(f"unexpected STAFF archive changes: {changed}")
    mes_entry = next(item for item in output_entries if item.name == "STAFF.MES")
    slot_end = output_entries[mes_entry.index + 1].offset
    return {
        "status": "PASS",
        "members": len(output_entries),
        "changed_members_from_retail": changed,
        "names_and_offsets_match_retail": True,
        "archive_size_matches_retail": True,
        "mes_compressed_size": mes_entry.compressed_size,
        "mes_fixed_slot_size": slot_end - mes_entry.offset,
        "mes_fixed_slot_headroom": slot_end - mes_entry.offset - mes_entry.compressed_size,
        "lz": facts(OUTPUT_LZ),
    }


def run_regression() -> dict[str, object]:
    """Extract the final ISO, validate all scripts, and round-trip patched MES files."""
    iso_dir = REGRESSION / "iso_files"
    extract_iso(OUTPUT_ISO, iso_dir)
    archives = sorted(path for path in iso_dir.glob("*.LZ") if path.stem in SCRIPT_ARCHIVES)
    if len(archives) != len(SCRIPT_ARCHIVES) or {path.stem for path in archives} != SCRIPT_ARCHIVES:
        raise ValueError("final script archive inventory drifted")
    mes_files: list[Path] = []
    for archive in archives:
        out_dir = REGRESSION / "unpacked" / archive.stem
        unpack_lz(archive, out_dir)
        mes_files.extend(out_dir.glob("*.MES.unpacked"))
    if len(mes_files) != len(SCRIPT_ARCHIVES):
        raise ValueError(f"final MES inventory drifted: {len(mes_files)}")
    for path in mes_files:
        strict_mes(path)
    for chapter, source_mes in PATCHED_MES.items():
        final_mes = REGRESSION / "unpacked" / chapter / f"001_{chapter}.MES.unpacked"
        if final_mes.read_bytes() != source_mes.read_bytes():
            raise ValueError(f"final {chapter}.MES differs from the approved build")
        strict_mes(final_mes, PATCHED_COUNTS[chapter])

    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(TOOLS), pattern="test_*.py")
    count = suite.countTestCases()
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise ValueError(f"tool unit tests failed: {stream.getvalue()}")
    return {
        "script_archives": len(archives),
        "validated_mes_files": len(mes_files),
        "strict_pointers_terminators_and_dynamic_banks": True,
        "patched_mes_round_trips": list(PATCHED_MES),
        "tool_unit_tests": f"{count}/{count} PASS",
    }


def main() -> None:
    """Build one fresh credits-translated test disc and its audit report."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse delivery directory: {DELIVERY}")
    source_report = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    if source_report.get("status") != "PASS" or not source_report.get("release_candidate"):
        raise ValueError("source Act 4 build is not an approved release candidate")
    staff_manifest = json.loads(STAFF_MANIFEST.read_text(encoding="utf-8"))
    coverage = staff_manifest.get("translation_coverage", {})
    if staff_manifest.get("status") != "PASS" or not coverage.get("complete"):
        raise ValueError("STAFF translation manifest did not pass")
    staff_mes_audit = strict_mes(STAFF_MES, PATCHED_COUNTS["STAFF"])
    if staff_mes_audit["size"] > 0x3FFF:
        raise ValueError("STAFF MES exceeds its hard boundary")

    DELIVERY.mkdir(parents=True)
    ARCHIVE_AUDIT.mkdir()
    archive_report = build_staff_lz()
    plans = patch_iso_replacements(SOURCE_ISO, OUTPUT_ISO, {"STAFF.LZ": OUTPUT_LZ})
    if OUTPUT_ISO.stat().st_size != SOURCE_ISO.stat().st_size:
        raise ValueError("final ISO size changed")
    before_iso = iso_hashes(SOURCE_ISO)
    after_iso = iso_hashes(OUTPUT_ISO)
    changed_iso = sorted(Path(path).name for path in before_iso if before_iso[path] != after_iso.get(path))
    if set(before_iso) != set(after_iso) or changed_iso != ["STAFF.LZ"]:
        raise ValueError(f"unexpected ISO patch scope: {changed_iso}")

    raw_mode1_2352_from_iso(SOURCE_TRACK1, OUTPUT_ISO, OUTPUT_TRACK1)
    shutil.copyfile(SOURCE_TRACK2, OUTPUT_TRACK2)
    write_standard_mega_cd_cue(OUTPUT_CUE, OUTPUT_TRACK1, OUTPUT_TRACK2)
    roundtrip = DELIVERY / "_track1_roundtrip.iso"
    raw_mode1_2352_to_iso(OUTPUT_TRACK1, roundtrip)
    if roundtrip.read_bytes() != OUTPUT_ISO.read_bytes():
        raise ValueError("raw Track 1 does not reconstruct the final ISO")
    roundtrip.unlink()
    disc = inspect_standard_mega_cd_cue(OUTPUT_CUE, ORIGINAL_TRACK1)
    if disc["track_count"] != 2 or not disc["template_boot_match"] or disc["cue_line_endings"] != "CRLF":
        raise ValueError("final disc boot or CUE geometry failed")
    if OUTPUT_TRACK2.read_bytes() != SOURCE_TRACK2.read_bytes():
        raise ValueError("audio track changed")

    regression = run_regression()
    report = {
        "status": "PASS",
        "release_candidate": True,
        "purpose": "Complete English STAFF cast, Mega-CD, and soundtrack credits after Act 4",
        "source_act4_build": {"status": source_report["status"], "iso": facts(SOURCE_ISO)},
        "staff_translation": {
            "records": 62,
            "translated_records": 62,
            "coverage_complete": True,
            "credit_draw_commands": staff_manifest["scn"]["credit_draw_commands"],
            "all_records_referenced": staff_manifest["scn"]["all_records_referenced"],
            "scn_byte_identical_to_retail": STAFF_SCN.read_bytes() == (
                STAFF_SOURCE_ARCHIVE / "000_STAFF.SCN.unpacked"
            ).read_bytes(),
            "cards_exactly_20_runtime_cells": staff_manifest["centering"]["every_card_exact_width"],
            "mes": staff_mes_audit,
        },
        "archive": archive_report,
        "iso": {
            "output": facts(OUTPUT_ISO),
            "changed_files_relative_to_act4_build": changed_iso,
            "cumulative_translated_archives": ["PART3C.LZ", "PART4A.LZ", "PART4B.LZ", "PART4C.LZ", "STAFF.LZ"],
            "replacement_plans": [
                {
                    "target": plan.target,
                    "extent": plan.extent,
                    "old_size": plan.old_size,
                    "new_size": plan.new_size,
                    "allocated_size": plan.allocated_size,
                    "fits": plan.fits,
                }
                for plan in plans
            ],
        },
        "disc": {
            "track_1": facts(OUTPUT_TRACK1),
            "track_2": facts(OUTPUT_TRACK2),
            "cue": facts(OUTPUT_CUE),
            "track1_iso_round_trip": True,
            "audio_track_byte_identical": True,
            "boot_system_matches_supplied_original": True,
            "cue_line_endings": disc["cue_line_endings"],
        },
        "regression": regression,
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUTPUT_NOTES.write_text(
        "# Nostalgia 1907 Act 4 plus English credits\n\n"
        "This build preserves the approved PART3C speaker fix and complete PART4A/B/C first-pass "
        "translation, then translates all 62 STAFF cast, Mega-CD, and soundtrack credit cards.\n\n"
        "Test the bomb-explosion ending through the final 1991 card. The same unchanged STAFF SCN "
        "remains safe if another ending invokes the shared credits.\n\n"
        "Static checks cover credit-card width, SCN references, MES pointers and terminators, dynamic "
        "font alignment, fixed LZ slots, archive round trips, ISO patch scope, raw-sector reconstruction, "
        "boot geometry, audio identity, all 19 game scripts, and the tool unit suite.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

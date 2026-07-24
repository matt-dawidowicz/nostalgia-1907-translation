#!/usr/bin/env python3
"""Build the PART3C speaker fix plus complete Act 4 first-pass BIN/CUE."""

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
PART3_ROOT = WORKSPACE / "work" / "part3c_original_compare"
PART3_ORIGINAL_ARCHIVE = PART3_ROOT / "original_part3c"
PART3_ORIGINAL_LZ = PART3_ROOT / "original_extract" / "PART3C.LZ"
PART3_SOURCE = WORKSPACE / "outputs" / "PART3C_transitionfix10_full_fresh"
PART3_SOURCE_MES = PART3_SOURCE / "PART3C.MES"
PART3_SOURCE_SCN = PART3_SOURCE / "PART3C.SCN"
SOURCE_ISO = PART3_SOURCE / "Nostalgia1907_Act3C_transitionfix10_full.iso"
SOURCE_TRACK1 = PART3_SOURCE / "Nostalgia1907_Act3C_transitionfix10_full_Track1.bin"
SOURCE_TRACK2 = PART3_SOURCE / "Nostalgia1907_Act3C_transitionfix10_full_Track2.bin"
ORIGINAL_TRACK1 = Path(
    r"D:\Sega CD Games\Nostalgia 1907 (Japan)\Nostalgia 1907 (Japan) (Track 1).bin"
)
BUILT_MES = HERE / "built"
DELIVERY = WORKSPACE / "outputs" / "Nostalgia1907_Act4_firstpass_speakerfix"
UNPACKED = DELIVERY / "archive_audit"
REGRESSION = DELIVERY / "regression"

OUTPUT_ISO = DELIVERY / "Nostalgia1907_Act4_firstpass_speakerfix.iso"
OUTPUT_TRACK1 = DELIVERY / "Nostalgia1907_Act4_firstpass_speakerfix_Track1.bin"
OUTPUT_TRACK2 = DELIVERY / "Nostalgia1907_Act4_firstpass_speakerfix_Track2.bin"
OUTPUT_CUE = DELIVERY / "Nostalgia1907_Act4_firstpass_speakerfix.cue"
OUTPUT_REPORT = DELIVERY / "final_verification.json"
OUTPUT_NOTES = DELIVERY / "TEST_NOTES.md"
PART3_MES = DELIVERY / "PART3C.MES"
PART3_SCN = DELIVERY / "PART3C.SCN"
FIXED_FONT = DELIVERY / "FIX_CODE.FNT"

CHAPTERS = ("PART3C", "PART4A", "PART4B", "PART4C")
EXPECTED_RECORDS = {"PART3C": 224, "PART4A": 63, "PART4B": 293, "PART4C": 60}
MAX_ACT4_MES_SIZE = 0x7FFF

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
    """Return size and SHA-256 for one artifact."""
    data = path.read_bytes()
    return {"size": len(data), "sha256": digest(data)}


def load_mes(path: Path, expected: int) -> tuple[bytes, object, list[int], list[bytes], bytes]:
    """Load one strictly monotonic, fully terminated MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or info.pointer_count != expected:
        raise ValueError(f"invalid MES structure/count: {path}")
    if any(left >= right for left, right in zip(pointers, pointers[1:])):
        raise ValueError(f"non-monotonic pointers: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    for index, record in enumerate(records):
        if not record or record[-1] != 0 or record.count(0) != 1:
            raise ValueError(f"{path.name} record {index} lacks one final terminator")
    tail = data[info.split_offset :]
    if len(tail) % 18:
        raise ValueError(f"{path.name} dynamic tail is not 18-byte aligned")
    return data, info, pointers, records, tail


def serialize_mes(records: list[bytes], tail: bytes) -> bytes:
    """Serialize records with a fresh pointer table and unchanged dynamic tail."""
    split = 2 + 2 * len(records) + sum(map(len, records))
    if split > 0xFFFF:
        raise ValueError("MES split exceeds its 16-bit field")
    output = bytearray()
    output.extend(split.to_bytes(2, "big"))
    cursor = 2 + 2 * len(records)
    for record in records:
        output.extend(cursor.to_bytes(2, "big"))
        cursor += len(record)
    output.extend(b"".join(records))
    output.extend(tail)
    return bytes(output)


def build_part3_speaker_fix() -> dict[str, object]:
    """Restore the Yamada Kasuke speaker slot without touching SCN geometry."""
    source, source_info, _, source_records, source_tail = load_mes(PART3_SOURCE_MES, 224)
    if source_records[147] != source_records[194]:
        raise ValueError("PART3C no longer has the reviewed duplicate-Dunant bug signature")
    if source_records[146] == source_records[147]:
        raise ValueError("PART3C Yamada and Dunant source renderings unexpectedly match")
    records = list(source_records)
    records[194] = records[146]
    output = serialize_mes(records, source_tail)
    if len(output) > 0x3FFF:
        raise ValueError("PART3C speaker fix crossed the proven 0x3FFF limit")
    PART3_MES.write_bytes(output)
    shutil.copyfile(PART3_SOURCE_SCN, PART3_SCN)
    parsed, info, _, output_records, tail = load_mes(PART3_MES, 224)
    changed = [i for i, pair in enumerate(zip(source_records, output_records)) if pair[0] != pair[1]]
    if changed != [194] or output_records[194] != output_records[146]:
        raise ValueError(f"PART3C speaker fix scope failed: {changed}")
    if output_records[147] != source_records[147] or tail != source_tail:
        raise ValueError("PART3C speaker fix altered Dunant or the dynamic bank")
    original_scn = (PART3_ORIGINAL_ARCHIVE / "000_PART3C.SCN.unpacked").read_bytes()
    if PART3_SCN.read_bytes() != original_scn:
        raise ValueError("PART3C SCN no longer matches retail")
    expected_pairs = [
        (0x0D8E, 194, 195),
        (0x0D9E, 147, 196),
        (0x0DAE, 194, 197),
        (0x0DBE, 147, 198),
        (0x0DCE, 194, 199),
        (0x0DDE, 147, 200),
        (0x0DEE, 194, 201),
        (0x0DFE, 147, 202),
        (0x0E0E, 194, 203),
        (0x0E1E, 147, 204),
        (0x0E2E, 194, 205),
        (0x0E3E, 147, 206),
    ]
    for offset, speaker_index, dialogue_index in expected_pairs:
        command = original_scn[offset : offset + 5]
        expected_command = bytes((0x21,)) + (speaker_index + 1).to_bytes(2, "big") + (dialogue_index + 1).to_bytes(2, "big")
        if command != expected_command:
            raise ValueError(f"PART3C speaker alternation drifted at SCN 0x{offset:X}")
    if info.split_offset != source_info.split_offset + 7 or len(parsed) != len(source) + 7:
        raise ValueError("PART3C speaker fix size delta is not the reviewed seven bytes")
    return {
        "status": "PASS",
        "changed_records": changed,
        "record_147": "Dunant",
        "record_194": "Yamada Kasuke (copied from proven record 146 rendering)",
        "alternating_scn_commands_verified": len(expected_pairs),
        "scn_byte_identical_to_retail": True,
        "dynamic_tail_byte_identical": True,
        "source_size": len(source),
        "output_size": len(parsed),
        "output_size_hex": f"0x{len(parsed):X}",
        "hard_limit": "0x3FFF",
        "headroom": 0x3FFF - len(parsed),
        "source_split": source_info.split_offset,
        "output_split": info.split_offset,
        "sha256": digest(parsed),
    }


def original_lz(chapter: str) -> Path:
    """Return the retail source LZ for one patched chapter."""
    if chapter == "PART3C":
        return PART3_ORIGINAL_LZ
    return PROJECT / "work" / "nostalgia1907" / "iso_files" / f"{chapter}.LZ"


def original_archive(chapter: str) -> Path:
    """Return the retail unpacked archive for one chapter."""
    if chapter == "PART3C":
        return PART3_ORIGINAL_ARCHIVE
    return PROJECT / "work" / "nostalgia1907" / "unpacked" / chapter


def chapter_mes(chapter: str) -> Path:
    """Return the final translated MES path for one chapter."""
    if chapter == "PART3C":
        return PART3_MES
    return BUILT_MES / chapter / f"{chapter}.MES"


def member_hashes(directory: Path) -> dict[str, str]:
    """Hash every unpacked archive member by its member name."""
    result: dict[str, str] = {}
    for path in directory.glob("*.unpacked"):
        member = path.name.split("_", 1)[1].removesuffix(".unpacked")
        result[member] = digest(path.read_bytes())
    return result


def build_chapter_lz(chapter: str) -> dict[str, object]:
    """Repack one MES into unchanged retail archive slots and audit scope."""
    source = original_lz(chapter)
    output = DELIVERY / f"{chapter}_firstpass.LZ"
    replacements = {f"{chapter}.MES": chapter_mes(chapter)}
    if chapter == "PART3C":
        replacements[f"{chapter}.SCN"] = PART3_SCN
    repack_lz_compressed_slots(source, output, replacements)
    source_entries = read_lz_entries(source)
    output_entries = read_lz_entries(output)
    if [(x.name, x.offset) for x in source_entries] != [(x.name, x.offset) for x in output_entries]:
        raise ValueError(f"{chapter} archive names/offsets changed")
    if output.stat().st_size != source.stat().st_size:
        raise ValueError(f"{chapter} archive byte length changed")
    audit_dir = UNPACKED / chapter
    unpack_lz(output, audit_dir)
    target_name = f"001_{chapter}.MES.unpacked"
    if (audit_dir / target_name).read_bytes() != chapter_mes(chapter).read_bytes():
        raise ValueError(f"{chapter} MES archive round trip failed")
    before = member_hashes(original_archive(chapter))
    after = member_hashes(audit_dir)
    changed = sorted(name for name in before if before[name] != after.get(name))
    if set(before) != set(after) or changed != [f"{chapter}.MES"]:
        raise ValueError(f"{chapter} unexpected archive scope: {changed}")
    mes_entry = next(item for item in output_entries if item.name == f"{chapter}.MES")
    slot_end = output_entries[mes_entry.index + 1].offset if mes_entry.index + 1 < len(output_entries) else output.stat().st_size
    return {
        "status": "PASS",
        "members": len(output_entries),
        "names_and_offsets_match_retail": True,
        "archive_size_matches_retail": True,
        "changed_members_from_retail": changed,
        "mes_compressed_size": mes_entry.compressed_size,
        "mes_fixed_slot_size": slot_end - mes_entry.offset,
        "mes_fixed_slot_headroom": slot_end - mes_entry.offset - mes_entry.compressed_size,
        "lz": facts(output),
    }


def iso_hashes(path: Path) -> dict[str, tuple[int, str]]:
    """Hash every ISO file by normalized path without extracting it."""
    data = path.read_bytes()
    result: dict[str, tuple[int, str]] = {}
    for entry in read_iso_entries(path):
        if entry.is_dir:
            continue
        start = entry.extent * 2048
        payload = data[start : start + entry.size]
        result[entry.path] = (entry.size, digest(payload))
    return result


def run_full_regression() -> dict[str, object]:
    """Extract the final ISO and validate every MES plus the unit suite."""
    extract_iso(OUTPUT_ISO, REGRESSION / "iso_files")
    lz_files = sorted((REGRESSION / "iso_files").glob("*.LZ"))
    script_archives = [path for path in lz_files if path.stem in {
        "START", "PART1A", "PART1B", "PART1C", "PART1D", "PART2A", "PART2B",
        "PART2C", "PART2D", "PART2E", "PART2F", "PART3A", "PART3B", "PART3B_",
        "PART3C", "PART4A", "PART4B", "PART4C", "STAFF",
    }]
    mes_files: list[Path] = []
    for lz_path in script_archives:
        out_dir = REGRESSION / "unpacked" / lz_path.stem
        unpack_lz(lz_path, out_dir)
        mes_files.extend(path for path in out_dir.glob("*.MES.unpacked"))
    if len(script_archives) != 19 or len(mes_files) != 19:
        raise ValueError(f"regression inventory drifted: LZ={len(script_archives)}, MES={len(mes_files)}")
    for path in mes_files:
        data = path.read_bytes()
        info, pointers = parse_mes(data, path)
        if not info.valid or len(pointers) != info.pointer_count:
            raise ValueError(f"invalid regression MES: {path}")
        if any(left >= right for left, right in zip(pointers, pointers[1:])):
            raise ValueError(f"non-monotonic regression MES: {path}")
    for chapter in CHAPTERS:
        final_mes = REGRESSION / "unpacked" / chapter / f"001_{chapter}.MES.unpacked"
        if final_mes.read_bytes() != chapter_mes(chapter).read_bytes():
            raise ValueError(f"regression {chapter} differs from delivery")

    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(TOOLS), pattern="test_*.py")
    count = suite.countTestCases()
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise ValueError(f"tool unit tests failed: {stream.getvalue()}")
    return {
        "script_archives": len(script_archives),
        "validated_mes_files": len(mes_files),
        "patched_mes_round_trips": list(CHAPTERS),
        "tool_unit_tests": f"{count}/{count} PASS",
    }


def main() -> None:
    """Build, package, and independently verify one fresh test disc."""
    if DELIVERY.exists():
        raise FileExistsError(f"refusing to reuse delivery directory: {DELIVERY}")
    for chapter, expected in EXPECTED_RECORDS.items():
        if chapter == "PART3C":
            continue
        mes_path = chapter_mes(chapter)
        data, info, _, records, _ = load_mes(mes_path, expected)
        if len(data) > MAX_ACT4_MES_SIZE:
            raise ValueError(f"{chapter} MES exceeds hard 0x7FFF guard")
        manifest = json.loads((BUILT_MES / chapter / f"{chapter}_manifest.json").read_text(encoding="utf-8"))
        coverage = manifest.get("translation_coverage", {})
        if coverage.get("translated_records") != expected or not coverage.get("complete"):
            raise ValueError(f"{chapter} translation coverage guard failed")
        if len(records) != expected or info.split_offset > 0xFFFF:
            raise ValueError(f"{chapter} structural guard failed")

    DELIVERY.mkdir(parents=True)
    UNPACKED.mkdir()
    shutil.copyfile(PART3_SOURCE / "FIX_CODE.FNT", FIXED_FONT)
    speaker_report = build_part3_speaker_fix()
    archive_reports = {chapter: build_chapter_lz(chapter) for chapter in CHAPTERS}
    lz_paths = {f"{chapter}.LZ": DELIVERY / f"{chapter}_firstpass.LZ" for chapter in CHAPTERS}
    plans = patch_iso_replacements(SOURCE_ISO, OUTPUT_ISO, lz_paths)
    if OUTPUT_ISO.stat().st_size != SOURCE_ISO.stat().st_size:
        raise ValueError("final ISO size changed")
    source_files = iso_hashes(SOURCE_ISO)
    output_files = iso_hashes(OUTPUT_ISO)
    changed_iso = sorted(
        Path(path).name for path in source_files if source_files[path] != output_files.get(path)
    )
    expected_changed = [f"{chapter}.LZ" for chapter in CHAPTERS]
    if set(source_files) != set(output_files) or changed_iso != sorted(expected_changed):
        raise ValueError(f"unexpected final ISO scope: {changed_iso}")

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
        raise ValueError("final disc boot/CUE geometry failed")
    if OUTPUT_TRACK2.read_bytes() != SOURCE_TRACK2.read_bytes():
        raise ValueError("audio track changed")

    regression = run_full_regression()
    act4 = {}
    for chapter in ("PART4A", "PART4B", "PART4C"):
        data, info, pointers, records, tail = load_mes(chapter_mes(chapter), EXPECTED_RECORDS[chapter])
        act4[chapter] = {
            "records": len(records),
            "translated_records": len(records),
            "coverage_complete": True,
            "size": len(data),
            "size_hex": f"0x{len(data):X}",
            "hard_limit": "0x7FFF",
            "headroom": MAX_ACT4_MES_SIZE - len(data),
            "split_offset": info.split_offset,
            "strictly_increasing_pointers": all(a < b for a, b in zip(pointers, pointers[1:])),
            "dynamic_glyphs": len(tail) // 18,
            "sha256": digest(data),
        }
    report = {
        "status": "PASS",
        "release_candidate": True,
        "purpose": "PART3C Yamada/Dunant speaker correction plus complete Act 4 first-pass translation",
        "part3c_speaker_fix": speaker_report,
        "act4": act4,
        "archives": archive_reports,
        "iso": {
            "source": facts(SOURCE_ISO),
            "output": facts(OUTPUT_ISO),
            "changed_files": changed_iso,
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
        "fixed_font": {
            **facts(FIXED_FONT),
            "byte_identical_to_proven_transitionfix10": True,
        },
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUTPUT_NOTES.write_text(
        "# Nostalgia 1907 Act 4 first-pass test build\n\n"
        "This disc fixes PART3C speaker record 194 so the Royal Suite A confrontation alternates "
        "between Yamada Kasuke and Dunant, then translates all 416 records in PART4A/B/C.\n\n"
        "Test from the late PART3C confrontation through the end of Act 4. Please watch for speaker "
        "labels, the bomb-disposal item choices, every background transition, and both endgame choices.\n\n"
        "The build passed pointer, terminator, row-boundary, floating-window, choice-cell, fixed-slot, "
        "archive-round-trip, ISO-scope, raw-sector, boot, audio, and full-game MES regressions.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

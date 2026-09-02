#!/usr/bin/env python3
"""Prove cross-layer invariants for one complete clean rebuild.

This module is the binary release gate after compilation. It reconciles
canonical inventory, MES/font reports, archive contents, ISO directory records,
raw Track 1, untouched Track 2, and CUE syntax. It also streams both retail and
rebuilt ISO images to prove that bytes outside declared allocations and
directory-size fields are unchanged.

A successful result is evidence for one build, not a determinism proof by
itself. ``rebuild.py`` runs the entire pipeline twice and compares artifact
hashes before publishing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .iso9660 import SECTOR_SIZE, extract_file, read_entries, unique_file
from .lz_format import parse_archive, read_member
from .main_patch import PATCHED_SHA256, RETAIL_SHA256
from .mes_compiler import FIXED_ENGLISH_UNITS
from .mes_format import read_mes
from .prepare_retail import RETAIL_TRACK1_SHA256
from .source_json import load_json_array, load_json_object
from .scn_patch import patch_part1a_scn
from .raw_cd import verify_track


HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
DYNAMIC_LIMIT = 1020
PART3C_LIMIT = 0x3FFF
EXPECTED_CHAPTERS = 19
EXPECTED_RECORDS = 2905
TRACK2_SIZE = 24_710_112
TRACK2_SHA256 = "F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991"


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _assert_unchanged_outside(
    retail_iso: Path, output_iso: Path, allowed: list[tuple[int, int]]
) -> None:
    """Prove the rebuilt ISO differs only inside declared byte intervals."""
    if retail_iso.stat().st_size != output_iso.stat().st_size:
        raise ValueError("rebuilt ISO size differs from retail")
    merged: list[list[int]] = []
    for start, end in sorted(allowed):
        if not 0 <= start <= end <= retail_iso.stat().st_size:
            raise ValueError("allowed ISO mutation interval is out of bounds")
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    with retail_iso.open("rb") as retail, output_iso.open("rb") as output:
        cursor = 0
        for start, end in merged:
            if start > cursor:
                retail.seek(cursor)
                output.seek(cursor)
                remaining = start - cursor
                while remaining:
                    size = min(1024 * 1024, remaining)
                    if retail.read(size) != output.read(size):
                        raise ValueError(
                            f"ISO changed outside declared patches at 0x{cursor:X}"
                        )
                    cursor += size
                    remaining -= size
            cursor = max(cursor, end)
        if cursor < retail_iso.stat().st_size:
            retail.seek(cursor)
            output.seek(cursor)
            while True:
                left = retail.read(1024 * 1024)
                right = output.read(1024 * 1024)
                if left != right:
                    raise ValueError(
                        f"ISO changed outside declared patches after 0x{cursor:X}"
                    )
                if not left:
                    break
                cursor += len(left)


def validate_build(
    build_root: Path,
    output_root: Path,
    retail_track1: Path,
    retail_track2: Path,
    basename: str,
) -> dict[str, object]:
    """Validate compiler, archive, ISO, raw-track, audio, and CUE invariants.

    Raises immediately on the first unsafe boundary or stale report. The return
    value contains review metrics and hashes only after every layer passes.
    """
    index = load_json_object(SOURCES / "index.json")
    if index["chapter_count"] != EXPECTED_CHAPTERS:
        raise ValueError("canonical chapter count changed")
    mes_report = load_json_object(build_root / "mes_report.json")
    archive_report = load_json_object(build_root / "archive_report.json")
    patch_report = load_json_array(build_root / "iso_patch_report.json")
    if mes_report["status"] != "PASS" or archive_report["status"] != "PASS":
        raise ValueError("a prerequisite build report did not pass")

    total_records = 0
    max_dynamic = 0
    mes_results: list[dict[str, object]] = []
    mes_report_by_chapter = {item["chapter"]: item for item in mes_report["chapters"]}
    for item in index["chapters"]:
        chapter = item["chapter"]
        canonical = load_json_object(SOURCES / item["source"])
        records = canonical.get("records")
        if not isinstance(records, list) or len(records) != canonical["record_count"]:
            raise ValueError(f"{chapter}: canonical record coverage is incomplete")
        if any(record.get("index") != index for index, record in enumerate(records)):
            raise ValueError(f"{chapter}: canonical record indexes are not contiguous")
        if any(
            record.get("policy") not in {"translate", "preserve"} for record in records
        ):
            raise ValueError(f"{chapter}: canonical record policy is invalid")
        translated_count = sum(
            record.get("policy") == "translate" for record in records
        )
        preserved_count = sum(record.get("policy") == "preserve" for record in records)
        if canonical.get("text_mode") == "preserve":
            raise ValueError(
                f"{chapter}: a playable script reverted to preserve-only mode"
            )
        if (
            item.get("translated_records") != translated_count
            or item.get("preserved_records") != preserved_count
        ):
            raise ValueError(f"{chapter}: source index policy counts are stale")
        reported = mes_report_by_chapter.get(chapter)
        if not isinstance(reported, dict) or (
            reported.get("translated_records") != translated_count
            or reported.get("preserved_records") != preserved_count
        ):
            raise ValueError(
                f"{chapter}: compiler policy counts do not match canonical source"
            )
        if chapter == "PART3B_":
            preserved_indexes = {
                index
                for index, record in enumerate(records)
                if record.get("policy") == "preserve"
            }
            if canonical.get("text_mode") != "prose":
                raise ValueError(
                    "PART3B_ unexpectedly reverted to retail-preserve mode"
                )
            if preserved_indexes != {4, 15}:
                raise ValueError(
                    f"PART3B_ preserve scope changed: {sorted(preserved_indexes)}"
                )
            if translated_count != 209:
                raise ValueError(
                    "PART3B_ does not contain all 209 translated text records"
                )

        mes_path = build_root / "mes" / f"{chapter}.MES"
        mes = read_mes(mes_path)
        if mes.record_count != canonical["record_count"]:
            raise ValueError(f"{chapter}: output record count changed")
        if any(not record or record[-1] != 0 for record in mes.records):
            raise ValueError(f"{chapter}: a record lacks its terminator")
        if len(mes.glyphs) > DYNAMIC_LIMIT:
            raise ValueError(f"{chapter}: dynamic glyph bank exceeds runtime RAM")
        if chapter == "PART3C" and mes_path.stat().st_size > PART3C_LIMIT:
            raise ValueError("PART3C crossed the hard 0x3FFF boundary")
        total_records += mes.record_count
        max_dynamic = max(max_dynamic, len(mes.glyphs))
        mes_results.append(
            {
                "chapter": chapter,
                "records": mes.record_count,
                "size": mes_path.stat().st_size,
                "dynamic_glyphs": len(mes.glyphs),
                "sha256": sha256(mes_path),
            }
        )
    if total_records != EXPECTED_RECORDS:
        raise ValueError(f"total record count changed: {total_records}")

    part3c = read_mes(build_root / "mes" / "PART3C.MES")
    part3c_source = load_json_object(SOURCES / "PART3C.json")
    if part3c_source["records"][194].get("text") != "Ashby":
        raise ValueError(
            "PART3C record 194 no longer follows source アッシュビー -> Ashby"
        )
    if part3c.records[194] in {part3c.records[146], part3c.records[147]}:
        raise ValueError("PART3C Ashby speaker label collapsed into Yamada or Dunant")

    retail_font = build_root / "retail_files" / "FIX_CODE.FNT"
    output_font = build_root / "FIX_CODE.FNT"
    before_font = retail_font.read_bytes()
    after_font = output_font.read_bytes()
    if len(before_font) != len(after_font) or len(after_font) % 18:
        raise ValueError("fixed-font size or glyph alignment changed")
    patched_codes = {
        int(value, 16) for value in mes_report["fixed_font"]["patched_codes"]
    }
    expected_fixed_codes = {code for code, _style, _unit in FIXED_ENGLISH_UNITS}
    if patched_codes != expected_fixed_codes:
        raise ValueError("generated fixed-font dictionary does not match the compiler")
    changed_codes = {
        code
        for code in range(1, len(after_font) // 18 + 1)
        if before_font[(code - 1) * 18 : code * 18]
        != after_font[(code - 1) * 18 : code * 18]
    }
    if changed_codes != patched_codes:
        raise ValueError("fixed font changed outside the declared spill glyphs")
    retail_iso = build_root / "retail.iso"
    output_iso = build_root / "translated.iso"
    retail_iso_entries = read_entries(retail_iso)
    output_iso_entries = read_entries(output_iso)
    target_names = {item["target"] for item in patch_report}
    expected_targets = {f"{item['chapter']}.LZ" for item in index["chapters"]} | {
        "FIX_CODE.FNT",
        "MAIN.BIN",
    }
    if target_names != expected_targets:
        raise ValueError("ISO replacement set is incomplete or contains extras")

    allowed: list[tuple[int, int]] = []
    for patch in patch_report:
        target = patch["target"]
        retail_entry = unique_file(retail_iso_entries, target)
        output_entry = unique_file(output_iso_entries, target)
        if output_entry.extent != retail_entry.extent:
            raise ValueError(f"{target}: ISO extent moved")
        if output_entry.size != patch["output_size"]:
            raise ValueError(f"{target}: ISO logical size is stale")
        if output_entry.size > retail_entry.allocated_size:
            raise ValueError(f"{target}: ISO allocation overflow")
        allowed.append(
            (
                retail_entry.extent * SECTOR_SIZE,
                retail_entry.extent * SECTOR_SIZE + retail_entry.allocated_size,
            )
        )
        normalized = target.upper()
        records = [
            entry
            for entry in retail_iso_entries
            if entry.path.split("/", 1)[-1].split(";", 1)[0].upper() == normalized
        ]
        if not records:
            raise ValueError(f"{target}: no retail directory record")
        allowed.extend(
            (entry.record_offset + 10, entry.record_offset + 18) for entry in records
        )
    _assert_unchanged_outside(retail_iso, output_iso, allowed)

    for item in index["chapters"]:
        chapter = item["chapter"]
        retail_archive = build_root / "retail_archives" / f"{chapter}.LZ"
        output_archive = build_root / "archives" / f"{chapter}.LZ"
        installed_archive = extract_file(output_iso, f"{chapter}.LZ")
        if installed_archive != output_archive.read_bytes():
            raise ValueError(f"{chapter}: ISO archive differs from built archive")
        original = retail_archive.read_bytes()
        rebuilt = output_archive.read_bytes()
        original_entries = parse_archive(original, source=str(retail_archive))
        rebuilt_entries = parse_archive(rebuilt, source=str(output_archive))
        if [entry.name for entry in original_entries] != [
            entry.name for entry in rebuilt_entries
        ]:
            raise ValueError(f"{chapter}: archive member order/names changed")
        mes_name = f"{chapter}.MES"
        if (
            read_member(output_archive, mes_name)
            != (build_root / "mes" / mes_name).read_bytes()
        ):
            raise ValueError(f"{chapter}: compressed MES round-trip differs")
        retail_scn = (
            build_root / "retail_unpacked" / chapter / f"{chapter}.SCN"
        ).read_bytes()
        expected_scn = (
            patch_part1a_scn(retail_scn) if chapter == "PART1A" else retail_scn
        )
        if read_member(output_archive, f"{chapter}.SCN") != expected_scn:
            raise ValueError(f"{chapter}: SCN payload is outside the guarded contract")
        for old_entry, new_entry in zip(original_entries, rebuilt_entries, strict=True):
            if old_entry.name == mes_name or (
                chapter == "PART1A" and old_entry.name == "PART1A.SCN"
            ):
                continue
            old_payload = original[
                old_entry.offset : old_entry.offset + old_entry.compressed_size
            ]
            new_payload = rebuilt[
                new_entry.offset : new_entry.offset + new_entry.compressed_size
            ]
            if old_payload != new_payload:
                raise ValueError(
                    f"{chapter}:{old_entry.index}:{old_entry.name}: non-MES payload changed"
                )
        if chapter == "PART3B_" and rebuilt == original:
            raise ValueError("PART3B_ translation was not installed into its archive")

    main_bin = build_root / "MAIN.BIN"
    if sha256(build_root / "retail_files" / "MAIN.BIN") != RETAIL_SHA256:
        raise ValueError("retail MAIN.BIN hash changed")
    if (
        sha256(main_bin) != PATCHED_SHA256
        or extract_file(output_iso, "MAIN.BIN") != main_bin.read_bytes()
    ):
        raise ValueError("guarded MAIN.BIN patch did not install exactly")
    if extract_file(output_iso, "FIX_CODE.FNT") != output_font.read_bytes():
        raise ValueError("rebuilt fixed font did not install exactly")

    track1 = output_root / f"{basename}_Track1.bin"
    track2 = output_root / f"{basename}_Track2.bin"
    cue = output_root / f"{basename}.cue"
    track_report = verify_track(
        track1,
        compare_boot_to=retail_track1,
        trusted_reference=retail_track1,
        trusted_reference_sha256=RETAIL_TRACK1_SHA256,
    )
    if track_report["sector_count"] != retail_track1.stat().st_size // 2352:
        raise ValueError("raw Track 1 sector geometry changed")
    if track2.stat().st_size != TRACK2_SIZE or sha256(track2) != TRACK2_SHA256:
        raise ValueError("output Track 2 is not the exact retail audio track")
    if (
        sha256(retail_track2) != TRACK2_SHA256
        or retail_track2.stat().st_size != TRACK2_SIZE
    ):
        raise ValueError("input Track 2 is not the expected retail audio track")
    expected_cue = (
        f'FILE "{track1.name}" BINARY\r\n'
        "  TRACK 01 MODE1/2352\r\n"
        "    INDEX 01 00:00:00\r\n"
        f'FILE "{track2.name}" BINARY\r\n'
        "  TRACK 02 AUDIO\r\n"
        "    INDEX 00 00:00:00\r\n"
        "    INDEX 01 00:02:00\r\n"
    ).encode("ascii")
    if cue.read_bytes() != expected_cue:
        raise ValueError("CUE contents or CRLF line endings differ")

    result = {
        "status": "PASS",
        "chapter_count": len(index["chapters"]),
        "total_records": total_records,
        "max_dynamic_glyphs": max_dynamic,
        "part3c_size": (build_root / "mes" / "PART3C.MES").stat().st_size,
        "part3c_headroom": PART3C_LIMIT
        - (build_root / "mes" / "PART3C.MES").stat().st_size,
        "fixed_font_codes_changed": len(changed_codes),
        "iso_size": output_iso.stat().st_size,
        "iso_sha256": sha256(output_iso),
        "track1": {**track_report, "sha256": sha256(track1)},
        "track2": {"size": track2.stat().st_size, "sha256": sha256(track2)},
        "cue_sha256": sha256(cue),
        "mes": mes_results,
    }
    return result

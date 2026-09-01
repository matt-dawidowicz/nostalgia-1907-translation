#!/usr/bin/env python3
"""Create the ignored, hash-locked retail reference used by clean builds.

Preparation is the only path from the original Japanese Track 1 into the
compiler. It verifies the complete raw-track size/hash and every sector,
extracts a frozen logical ISO, walks its retail extents once, extracts all 19
chapter archives, and verifies each MES/SCN member against canonical guards.

The resulting directory is disposable evidence, not tracked source. No
translated artifact is consulted, and no retail byte is modified. Downstream
stages consume this reference to ensure renderer analysis and compilation are
always tied to the exact supported disc.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .source_json import load_json_object

from .iso9660 import SECTOR_SIZE, IsoEntry, read_entries, unique_file
from .lz_format import LzError, member_bytes, parse_archive
from .raw_cd import raw_to_iso


HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
RETAIL_TRACK1_SIZE = 192_649_968
RETAIL_TRACK1_SHA256 = (
    "EFE9A453849F52DC72B7E72EE98D8644882655536E59991C2C85C5A35A41D0E5"
)
RETAIL_ISO_SIZE = 167_749_632
RETAIL_ISO_SHA256 = "7944AF20FD802A43BEFBFA97734993EB63A3803F76D4AFBCEF315E41D4459ECC"


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _read_iso_entry(iso: object, entry: IsoEntry, label: str) -> bytes:
    """Read one already-resolved ISO entry without reparsing the filesystem."""
    iso.seek(entry.extent * SECTOR_SIZE)
    data = iso.read(entry.size)
    if len(data) != entry.size:
        raise ValueError(f"{label}: short read from retail ISO")
    return data


def _unique_member(data: bytes, entries: tuple[object, ...], name: str) -> bytes:
    """Return one uniquely named archive member from already-parsed bytes."""
    matches = [entry for entry in entries if entry.name == name]
    if len(matches) != 1:
        raise LzError(f"expected one archive member named {name!r}")
    return member_bytes(data, matches[0])


def prepare_retail(track1: Path, build_root: Path) -> dict[str, object]:
    """Verify retail Track 1 and extract every guarded compiler input.

    Args:
        track1: Original Japanese MODE1/2352 Track 1.
        build_root: Disposable destination for the prepared retail reference.

    Returns:
        A report containing source hashes, sector count, chapter member guards,
        duplicate archive names, and the fixed-font/executable hashes.

    Raises:
        ValueError: If the disc, logical ISO, archive, MES, or SCN violates a
            frozen size/hash/structure contract.
        OSError: If an input cannot be read or an output cannot be written.

    Side Effects:
        Creates the logical ISO, extracted archives, unpacked MES/SCN members,
        fixed font, MAIN.BIN, and ``retail_report.json`` below ``build_root``.
        It never writes to ``track1``.
    """
    track_size = track1.stat().st_size
    if track_size != RETAIL_TRACK1_SIZE:
        raise ValueError(
            f"retail Track 1 size mismatch: expected {RETAIL_TRACK1_SIZE}, "
            f"got {track_size}"
        )
    track_hash = sha256(track1)
    if track_hash != RETAIL_TRACK1_SHA256:
        raise ValueError(
            f"retail Track 1 hash mismatch: expected {RETAIL_TRACK1_SHA256}, "
            f"got {track_hash}"
        )

    build_root.mkdir(parents=True, exist_ok=True)
    retail_iso = build_root / "retail.iso"
    sector_count = raw_to_iso(track1, retail_iso, verify=True)
    iso_hash = sha256(retail_iso)
    iso_size = retail_iso.stat().st_size
    if iso_size != RETAIL_ISO_SIZE or iso_hash != RETAIL_ISO_SHA256:
        raise ValueError("retail ISO extraction does not match its frozen size/hash")

    source_index = load_json_object(SOURCES / "index.json")
    iso_entries = read_entries(retail_iso)
    archive_root = build_root / "retail_archives"
    unpacked_root = build_root / "retail_unpacked"
    file_root = build_root / "retail_files"
    archive_root.mkdir(parents=True, exist_ok=True)
    unpacked_root.mkdir(parents=True, exist_ok=True)
    file_root.mkdir(parents=True, exist_ok=True)
    chapters: list[dict[str, object]] = []

    with retail_iso.open("rb") as iso:
        for item in source_index["chapters"]:
            chapter = item["chapter"]
            canonical = load_json_object(SOURCES / item["source"])
            archive_name = f"{chapter}.LZ"
            archive_entry = unique_file(iso_entries, archive_name)
            archive_data = _read_iso_entry(iso, archive_entry, archive_name)
            archive_path = archive_root / archive_name
            archive_path.write_bytes(archive_data)
            members = parse_archive(archive_data, source=str(archive_path))
            name_counts = Counter(entry.name for entry in members)
            duplicate_names = sorted(
                name for name, count in name_counts.items() if count > 1
            )
            chapter_root = unpacked_root / chapter
            chapter_root.mkdir(parents=True, exist_ok=True)
            extracted: dict[str, dict[str, object]] = {}
            for kind in ("MES", "SCN"):
                member_name = f"{chapter}.{kind}"
                payload = _unique_member(archive_data, members, member_name)
                output_path = chapter_root / member_name
                output_path.write_bytes(payload)
                guard = canonical[f"retail_{kind.lower()}"]
                digest = hashlib.sha256(payload).hexdigest().upper()
                if len(payload) != guard["size"] or digest != guard["sha256"]:
                    raise ValueError(
                        f"{member_name}: retail member failed canonical guard"
                    )
                extracted[kind.lower()] = {"size": len(payload), "sha256": digest}
            chapters.append(
                {
                    "chapter": chapter,
                    "archive_size": len(archive_data),
                    "archive_extent": archive_entry.extent,
                    "archive_allocation": archive_entry.allocated_size,
                    "member_count": len(members),
                    "duplicate_member_names": duplicate_names,
                    **extracted,
                }
            )

        fixed_entry = unique_file(iso_entries, "FIX_CODE.FNT")
        main_entry = unique_file(iso_entries, "MAIN.BIN")
        fixed_font = _read_iso_entry(iso, fixed_entry, "FIX_CODE.FNT")
        main_bin = _read_iso_entry(iso, main_entry, "MAIN.BIN")

    (file_root / "FIX_CODE.FNT").write_bytes(fixed_font)
    (file_root / "MAIN.BIN").write_bytes(main_bin)
    payload = {
        "status": "PASS",
        "track1_size": track_size,
        "track1_sha256": track_hash,
        "iso_size": iso_size,
        "iso_sha256": iso_hash,
        "sector_count": sector_count,
        "chapter_count": len(chapters),
        "chapters": chapters,
        "fixed_font_sha256": hashlib.sha256(fixed_font).hexdigest().upper(),
        "main_bin_sha256": hashlib.sha256(main_bin).hexdigest().upper(),
    }
    (build_root / "retail_report.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track1", type=Path)
    parser.add_argument("--build-root", type=Path, default=HERE / "build")
    args = parser.parse_args()
    result = prepare_retail(args.track1, args.build_root)
    print(
        json.dumps(
            {
                "status": result["status"],
                "sector_count": result["sector_count"],
                "chapter_count": result["chapter_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

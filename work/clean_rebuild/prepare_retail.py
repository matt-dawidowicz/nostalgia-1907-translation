#!/usr/bin/env python3
"""Create the ignored, hash-locked retail reference used by clean builds.

Preparation is the only path from the original Japanese Track 1 into the
compiler. It verifies the complete raw-track size/hash and every sector,
extracts a frozen logical ISO, walks its retail extents, extracts all 19 chapter
archives, and verifies each MES/SCN member against canonical guards.

The resulting directory is disposable evidence, not tracked source. No
translated artifact is consulted, and no retail byte is modified. Downstream
stages consume this reference to ensure renderer analysis and compilation are
always tied to the exact supported disc.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from iso9660 import extract_file, read_entries, unique_file
from lz_format import parse_archive, read_member
from raw_cd import raw_to_iso


HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
RETAIL_TRACK1_SIZE = 192_649_968
RETAIL_TRACK1_SHA256 = "EFE9A453849F52DC72B7E72EE98D8644882655536E59991C2C85C5A35A41D0E5"
RETAIL_ISO_SIZE = 167_749_632
RETAIL_ISO_SHA256 = "7944AF20FD802A43BEFBFA97734993EB63A3803F76D4AFBCEF315E41D4459ECC"


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def prepare_retail(track1: Path, build_root: Path) -> dict[str, object]:
    """Verify retail Track 1 and extract all guarded compiler inputs."""
    if track1.stat().st_size != RETAIL_TRACK1_SIZE:
        raise ValueError(
            f"retail Track 1 size mismatch: expected {RETAIL_TRACK1_SIZE}, "
            f"got {track1.stat().st_size}"
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
    if retail_iso.stat().st_size != RETAIL_ISO_SIZE or iso_hash != RETAIL_ISO_SHA256:
        raise ValueError("retail ISO extraction does not match its frozen size/hash")

    source_index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
    iso_entries = read_entries(retail_iso)
    archive_root = build_root / "retail_archives"
    unpacked_root = build_root / "retail_unpacked"
    file_root = build_root / "retail_files"
    archive_root.mkdir(parents=True, exist_ok=True)
    unpacked_root.mkdir(parents=True, exist_ok=True)
    file_root.mkdir(parents=True, exist_ok=True)
    chapters: list[dict[str, object]] = []
    for item in source_index["chapters"]:
        chapter = item["chapter"]
        canonical = json.loads((SOURCES / item["source"]).read_text(encoding="utf-8"))
        archive_name = f"{chapter}.LZ"
        archive_entry = unique_file(iso_entries, archive_name)
        archive_path = archive_root / archive_name
        archive_path.write_bytes(extract_file(retail_iso, archive_name))
        members = parse_archive(archive_path.read_bytes(), source=str(archive_path))
        duplicate_names = sorted(
            {entry.name for entry in members if sum(x.name == entry.name for x in members) > 1}
        )
        chapter_root = unpacked_root / chapter
        chapter_root.mkdir(parents=True, exist_ok=True)
        extracted: dict[str, dict[str, object]] = {}
        for kind in ("MES", "SCN"):
            member_name = f"{chapter}.{kind}"
            payload = read_member(archive_path, member_name)
            output_path = chapter_root / member_name
            output_path.write_bytes(payload)
            guard = canonical[f"retail_{kind.lower()}"]
            digest = hashlib.sha256(payload).hexdigest().upper()
            if len(payload) != guard["size"] or digest != guard["sha256"]:
                raise ValueError(f"{member_name}: retail member failed canonical guard")
            extracted[kind.lower()] = {"size": len(payload), "sha256": digest}
        chapters.append(
            {
                "chapter": chapter,
                "archive_size": archive_path.stat().st_size,
                "archive_extent": archive_entry.extent,
                "archive_allocation": archive_entry.allocated_size,
                "member_count": len(members),
                "duplicate_member_names": duplicate_names,
                **extracted,
            }
        )

    fixed_font = extract_file(retail_iso, "FIX_CODE.FNT")
    main_bin = extract_file(retail_iso, "MAIN.BIN")
    (file_root / "FIX_CODE.FNT").write_bytes(fixed_font)
    (file_root / "MAIN.BIN").write_bytes(main_bin)
    payload = {
        "status": "PASS",
        "track1_size": track1.stat().st_size,
        "track1_sha256": track_hash,
        "iso_size": retail_iso.stat().st_size,
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

#!/usr/bin/env python3
"""Install generated MES files into retail chapter-archive allocations.

Each chapter archive is re-extracted from the verified retail ISO. The writer
first attempts an exact member-slot replacement. Only when the generated MES
does not fit may it reflow member payloads, and that fallback is bounded by the
archive's existing ISO sector allocation.

Member names and order always remain retail-authored. Fixed-slot mode also
preserves offsets and archive size; guarded-reflow mode preserves every
untouched payload and reports remaining outer-allocation headroom. The
generated ``archive_report.json`` records which strategy each chapter used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from iso9660 import extract_file, read_entries, unique_file
from lz_format import LzError, parse_archive, replace_members_fixed, replace_members_reflow


HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build_archives(build_root: Path) -> dict[str, object]:
    """Replace MES members while preserving each retail ISO allocation."""
    retail_iso = build_root / "retail.iso"
    mes_root = build_root / "mes"
    source_root = build_root / "retail_archives"
    output_root = build_root / "archives"
    report = build_root / "archive_report.json"
    source_index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
    source_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    iso_entries = read_entries(retail_iso)
    chapters: list[dict[str, object]] = []
    for item in source_index["chapters"]:
        chapter = item["chapter"]
        archive_name = f"{chapter}.LZ"
        iso_entry = unique_file(iso_entries, archive_name)
        retail_path = source_root / archive_name
        retail_path.write_bytes(extract_file(retail_iso, archive_name))
        output_path = output_root / archive_name
        replacements = {f"{chapter}.MES": mes_root / f"{chapter}.MES"}
        try:
            replacement_report = replace_members_fixed(
                retail_path, output_path, replacements
            )
            archive_mode = "fixed-slot"
            archive_headroom = replacement_report[0]["headroom"]
        except LzError as error:
            if "but retail slot is" not in str(error):
                raise
            reflow = replace_members_reflow(
                retail_path,
                output_path,
                replacements,
                maximum_archive_size=iso_entry.allocated_size,
            )
            replacement_report = reflow["replacements"]
            archive_mode = "guarded-reflow"
            archive_headroom = reflow["headroom"]
        if archive_mode == "fixed-slot" and output_path.stat().st_size != retail_path.stat().st_size:
            raise ValueError(f"{chapter}: fixed-slot archive size changed")
        if output_path.stat().st_size > iso_entry.allocated_size:
            raise ValueError(f"{chapter}: archive exceeds its retail ISO allocation")
        retail_entries = parse_archive(retail_path.read_bytes(), source=str(retail_path))
        output_entries = parse_archive(output_path.read_bytes(), source=str(output_path))
        if [entry.name for entry in output_entries] != [
            entry.name for entry in retail_entries
        ]:
            raise ValueError(f"{chapter}: member order or names changed")
        if archive_mode != "guarded-reflow" and [
            entry.offset for entry in output_entries
        ] != [entry.offset for entry in retail_entries]:
            raise ValueError(f"{chapter}: fixed-slot member offsets moved")
        chapters.append(
            {
                "chapter": chapter,
                "archive": archive_name,
                "size": output_path.stat().st_size,
                "iso_allocated_size": iso_entry.allocated_size,
                "retail_sha256": sha256(retail_path),
                "output_sha256": sha256(output_path),
                "byte_identical_to_retail": sha256(retail_path) == sha256(output_path),
                "members": len(output_entries),
                "mode": archive_mode,
                "headroom": archive_headroom,
                "replacement": replacement_report,
            }
        )
    payload = {
        "status": "PASS",
        "archive_count": len(chapters),
        "minimum_archive_headroom": min(
            chapter["headroom"]
            for chapter in chapters
            if chapter["headroom"] is not None
        ),
        "chapters": chapters,
    }
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, default=HERE / "build")
    args = parser.parse_args()
    payload = build_archives(args.build_root)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "archive_count": payload["archive_count"],
                "minimum_archive_headroom": payload["minimum_archive_headroom"],
                "modes": {
                    mode: sum(
                        1
                        for chapter in payload["chapters"]
                        if chapter["mode"] == mode
                    )
                    for mode in sorted(
                        {chapter["mode"] for chapter in payload["chapters"]}
                    )
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

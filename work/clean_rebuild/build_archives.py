#!/usr/bin/env python3
"""Install generated MES files into retail chapter-archive allocations.

Each chapter archive is extracted directly from the already-indexed retail ISO.
The writer first attempts an exact member-slot replacement. Only when the
generated MES does not fit may it reflow member payloads, and that fallback is
bounded by the archive's existing ISO sector allocation.

Member names and order always remain retail-authored. Fixed-slot mode also
preserves offsets and archive size; guarded-reflow mode preserves every
untouched payload and reports remaining outer-allocation headroom. The
generated ``archive_report.json`` records which strategy each chapter used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from .iso9660 import SECTOR_SIZE, read_entries, unique_file
from .lz_format import (
    LzSlotOverflowError,
    parse_archive,
    replace_members_fixed,
    replace_members_reflow,
    read_member,
)
from .scn_patch import patch_part1a_scn
from .source_json import load_json_object


HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"


def _sha256(data: bytes) -> str:
    """Return an uppercase SHA-256 digest for in-memory bytes."""
    return hashlib.sha256(data).hexdigest().upper()


def _minimum_fixed_headroom(replacements: list[dict[str, object]]) -> int:
    """Return the tightest fixed member-slot headroom in one archive."""
    if not replacements:
        raise ValueError("fixed-slot replacement report is empty")
    headrooms = [item.get("headroom") for item in replacements]
    if not all(isinstance(value, int) for value in headrooms):
        raise ValueError("fixed-slot replacement report has invalid headroom")
    return min(headrooms)


def _replace_archive(
    retail_path: Path,
    output_path: Path,
    replacements: dict[str, Path],
    allocation_size: int,
) -> tuple[list[dict[str, object]], str, int]:
    """Use fixed slots when possible and reflow only for typed capacity failure."""
    try:
        replacement_report = replace_members_fixed(
            retail_path, output_path, replacements
        )
        return replacement_report, "fixed-slot", _minimum_fixed_headroom(
            replacement_report
        )
    except LzSlotOverflowError:
        reflow = replace_members_reflow(
            retail_path,
            output_path,
            replacements,
            maximum_archive_size=allocation_size,
        )
        replacement_report = reflow.get("replacements")
        headroom = reflow.get("headroom")
        if not isinstance(replacement_report, list) or not all(
            isinstance(item, dict) for item in replacement_report
        ):
            raise ValueError("guarded-reflow report has invalid replacements")
        if not isinstance(headroom, int):
            raise ValueError("guarded-reflow report has invalid headroom")
        return replacement_report, "guarded-reflow", headroom


def build_archives(build_root: Path) -> dict[str, object]:
    """Replace MES members while preserving each retail ISO allocation.

    Fixed-slot replacement is attempted first. Reflow is permitted only for
    the specific typed capacity failure that means a compressed member no
    longer fits its retail slot, and it remains bounded by the archive's retail
    ISO sector allocation.

    Returns:
        A report recording mode, hashes, member count, replacement details, and
        remaining allocation headroom for every chapter.

    Side Effects:
        Extracts retail archives and writes rebuilt archives plus
        ``archive_report.json`` below ``build_root``.
    """
    retail_iso = build_root / "retail.iso"
    mes_root = build_root / "mes"
    source_root = build_root / "retail_archives"
    output_root = build_root / "archives"
    report = build_root / "archive_report.json"
    source_index = load_json_object(SOURCES / "index.json")
    source_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    iso_entries = read_entries(retail_iso)
    chapters: list[dict[str, object]] = []

    with retail_iso.open("rb") as iso:
        for item in source_index["chapters"]:
            chapter = item["chapter"]
            archive_name = f"{chapter}.LZ"
            iso_entry = unique_file(iso_entries, archive_name)
            iso.seek(iso_entry.extent * SECTOR_SIZE)
            retail_data = iso.read(iso_entry.size)
            if len(retail_data) != iso_entry.size:
                raise ValueError(f"{chapter}: short read from retail ISO")

            retail_path = source_root / archive_name
            retail_path.write_bytes(retail_data)
            output_path = output_root / archive_name
            replacements = {f"{chapter}.MES": mes_root / f"{chapter}.MES"}
            if chapter == "PART1A":
                with tempfile.TemporaryDirectory(
                    prefix="nostalgia1907-scn-"
                ) as temporary:
                    patched_scn = Path(temporary) / "PART1A.SCN"
                    patched_scn.write_bytes(
                        patch_part1a_scn(read_member(retail_path, "PART1A.SCN"))
                    )
                    replacements["PART1A.SCN"] = patched_scn
                    replacement_report, archive_mode, archive_headroom = (
                        _replace_archive(
                            retail_path,
                            output_path,
                            replacements,
                            iso_entry.allocated_size,
                        )
                    )
            else:
                replacement_report, archive_mode, archive_headroom = _replace_archive(
                    retail_path,
                    output_path,
                    replacements,
                    iso_entry.allocated_size,
                )

            output_data = output_path.read_bytes()
            if archive_mode == "fixed-slot" and len(output_data) != len(retail_data):
                raise ValueError(f"{chapter}: fixed-slot archive size changed")
            if len(output_data) > iso_entry.allocated_size:
                raise ValueError(f"{chapter}: archive exceeds its retail ISO allocation")

            retail_entries = parse_archive(retail_data, source=str(retail_path))
            output_entries = parse_archive(output_data, source=str(output_path))
            if [entry.name for entry in output_entries] != [
                entry.name for entry in retail_entries
            ]:
                raise ValueError(f"{chapter}: member order or names changed")
            if archive_mode != "guarded-reflow" and [
                entry.offset for entry in output_entries
            ] != [entry.offset for entry in retail_entries]:
                raise ValueError(f"{chapter}: fixed-slot member offsets moved")

            retail_hash = _sha256(retail_data)
            output_hash = _sha256(output_data)
            chapters.append(
                {
                    "chapter": chapter,
                    "archive": archive_name,
                    "size": len(output_data),
                    "iso_allocated_size": iso_entry.allocated_size,
                    "retail_sha256": retail_hash,
                    "output_sha256": output_hash,
                    "byte_identical_to_retail": retail_hash == output_hash,
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
                        1 for chapter in payload["chapters"] if chapter["mode"] == mode
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

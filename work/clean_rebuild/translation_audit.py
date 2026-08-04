#!/usr/bin/env python3
"""Fingerprint retail Japanese records and audit canonical English consistency.

Japanese identity is derived from the ordered retail glyph bitmaps rather than
from OCR or mutable English. Leading and trailing blank glyphs are removed only
for duplicate-source grouping; exact record bytes and exact bitmap fingerprints
remain in the report. The audit is read-only until the CLI writes its derived
JSON and Markdown reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from source_json import load_json_object

from mes_format import DYNAMIC_GLYPHS_PER_PREFIX, DYNAMIC_PREFIX_START, read_mes


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
SOURCES = HERE / "sources"
DEFAULT_RETAIL_ROOT = HERE / "retail_reference"
DEFAULT_OUTPUT = WORKSPACE / "outputs" / "Nostalgia1907_Translation_Audit"
EXEMPTIONS = HERE / "translation_exemptions.json"
GLYPH_BYTES = 18
FIXED_FONT_SHA256 = "0204DBCA3D3DC2C1B23CCC3FC10FC61DD2F1054805619B2E953247E61A1C954A"


def _sha256(data: bytes) -> str:
    """Return an uppercase SHA-256 digest for an in-memory byte sequence."""
    return hashlib.sha256(data).hexdigest().upper()


def _load_json(path: Path) -> dict[str, object]:
    """Load one UTF-8 JSON object or reject an incompatible top level."""
    return load_json_object(path)


def _glyphs(
    record: bytes, fixed: tuple[bytes, ...], dynamic: tuple[bytes, ...]
) -> tuple[bytes, ...]:
    """Resolve one retail record to its exact visible glyph bitmap sequence."""
    output: list[bytes] = []
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value in {0, 0xEE}:
            offset += 1
            continue
        if value >= DYNAMIC_PREFIX_START:
            if offset + 1 >= len(record) or record[offset + 1] == 0:
                raise ValueError("truncated retail dynamic-glyph reference")
            index = (
                (value - DYNAMIC_PREFIX_START) * DYNAMIC_GLYPHS_PER_PREFIX
                + record[offset + 1]
                - 1
            )
            if index >= len(dynamic):
                raise ValueError(f"dynamic glyph {index} exceeds retail bank")
            output.append(dynamic[index])
            offset += 2
            continue
        index = value - 1
        if not 0 <= index < len(fixed):
            raise ValueError(f"fixed glyph 0x{value:02X} exceeds retail font")
        output.append(fixed[index])
        offset += 1
    return tuple(output)


def _trim_blank(glyphs: tuple[bytes, ...]) -> tuple[bytes, ...]:
    """Remove only leading and trailing all-zero glyph cells."""
    start = 0
    end = len(glyphs)
    while start < end and not any(glyphs[start]):
        start += 1
    while end > start and not any(glyphs[end - 1]):
        end -= 1
    return glyphs[start:end]


def _fingerprint(glyphs: tuple[bytes, ...]) -> str:
    """Hash an ordered glyph sequence with an explicit length prefix."""
    payload = len(glyphs).to_bytes(4, "big") + b"".join(glyphs)
    return _sha256(payload)


def normalize_english_for_semantic_comparison(value: object) -> str:
    """Ignore presentation-only spaces and line wrapping, not wording."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _category(nonblank_count: int, english: str, policy: str) -> str:
    """Assign a review category without altering policy or canonical text."""
    if nonblank_count == 0:
        return "control_record"
    if policy == "preserve":
        return "reviewed_nonprose_or_unclassified"
    if nonblank_count <= 12 and len(english) <= 40 and "\n" not in english:
        return "short_label_or_choice_candidate"
    return "ordinary_dialogue_or_long_text"


def audit(retail_root: Path) -> dict[str, object]:
    """Return a stable-ID and retail-bitmap audit of all canonical records.

    Args:
        retail_root: Prepared Japanese reference containing the guarded fixed
            font and unpacked retail MES files.

    Returns:
        A JSON-serializable report with exact and normalized source
        fingerprints, duplicate groups, policy categories, and missing-text
        findings for every canonical record.

    Raises:
        ValueError: If fonts, MES references, source indexes, or exemption
            tables violate the validated project contract.
        OSError: If a required source or retail artifact cannot be read.

    Side Effects:
        Reads canonical and retail files; writes nothing.
    """
    index = _load_json(SOURCES / "index.json")
    exemptions = _load_json(EXEMPTIONS)
    visible_exemptions = exemptions["reviewed_visible_translation_exemptions"]
    control_exemptions = exemptions["reviewed_control_records"]
    if not isinstance(visible_exemptions, dict) or not isinstance(
        control_exemptions, dict
    ):
        raise ValueError("translation exemption tables are invalid")

    fixed_path = retail_root / "retail_files" / "FIX_CODE.FNT"
    fixed_data = fixed_path.read_bytes()
    if len(fixed_data) % GLYPH_BYTES or _sha256(fixed_data) != FIXED_FONT_SHA256:
        raise ValueError("retail fixed font failed its size/hash guard")
    fixed = tuple(
        fixed_data[offset : offset + GLYPH_BYTES]
        for offset in range(0, len(fixed_data), GLYPH_BYTES)
    )

    all_records: list[dict[str, object]] = []
    by_fingerprint: dict[str, list[dict[str, object]]] = defaultdict(list)
    chapter_order: list[str] = []
    for chapter_item in index["chapters"]:
        chapter = chapter_item["chapter"]
        chapter_order.append(chapter)
        canonical = _load_json(SOURCES / chapter_item["source"])
        records = canonical.get("records")
        if not isinstance(records, list) or len(records) != canonical.get(
            "record_count"
        ):
            raise ValueError(f"{chapter}: incomplete canonical record table")
        mes_path = retail_root / "retail_unpacked" / chapter / f"{chapter}.MES"
        mes = read_mes(mes_path)
        if mes.record_count != len(records):
            raise ValueError(f"{chapter}: retail/canonical record-count mismatch")
        for expected_index, (source_record, english_record) in enumerate(
            zip(mes.records, records, strict=True)
        ):
            record_id = f"{chapter}:{expected_index:03d}"
            if (
                not isinstance(english_record, dict)
                or english_record.get("index") != expected_index
            ):
                raise ValueError(f"{record_id}: canonical numeric ID is not stable")
            policy = english_record.get("policy")
            if policy not in {"translate", "preserve"}:
                raise ValueError(f"{record_id}: invalid canonical policy")
            resolved = _glyphs(source_record, fixed, mes.glyphs)
            normalized = _trim_blank(resolved)
            rendered_english = english_record.get("text")
            english = normalize_english_for_semantic_comparison(rendered_english)
            item = {
                "id": record_id,
                "chapter": chapter,
                "record_index": expected_index,
                "policy": policy,
                "source_record_sha256": _sha256(source_record),
                "source_record_hex": source_record.hex().upper(),
                "exact_bitmap_sha256": _fingerprint(resolved),
                "normalized_bitmap_sha256": _fingerprint(normalized),
                "visible_glyph_count": len(resolved),
                "normalized_visible_glyph_count": len(normalized),
                "english": english,
                "english_rendered": (
                    rendered_english if isinstance(rendered_english, str) else ""
                ),
                "category": _category(len(normalized), english, policy),
            }
            all_records.append(item)
            if normalized:
                by_fingerprint[item["normalized_bitmap_sha256"]].append(item)

    duplicate_groups: list[dict[str, object]] = []
    for fingerprint, members in sorted(by_fingerprint.items()):
        if len(members) < 2:
            continue
        english_values = sorted({member["english"] for member in members})
        rendered_values = sorted({member["english_rendered"] for member in members})
        categories = sorted({member["category"] for member in members})
        duplicate_groups.append(
            {
                "normalized_bitmap_sha256": fingerprint,
                "record_ids": [member["id"] for member in members],
                "english_values": english_values,
                "conflict": len(english_values) > 1,
                "formatting_only_variants": len(english_values) == 1
                and len(rendered_values) > 1,
                "category": (
                    categories[0] if len(categories) == 1 else "mixed_or_unresolved"
                ),
                "records": [
                    {
                        "id": member["id"],
                        "english": member["english"],
                        "english_rendered": member["english_rendered"],
                        "exact_bitmap_sha256": member["exact_bitmap_sha256"],
                        "source_record_sha256": member["source_record_sha256"],
                    }
                    for member in members
                ],
            }
        )

    missing_visible = [
        item["id"]
        for item in all_records
        if item["normalized_visible_glyph_count"]
        and not item["english"]
        and item["id"] not in visible_exemptions
    ]
    false_prose = [
        item["id"]
        for item in all_records
        if not item["normalized_visible_glyph_count"]
        and item["policy"] == "translate"
        and item["id"] not in control_exemptions
    ]
    return {
        "schema_version": 2,
        "status": "PASS",
        "fingerprint_method": {
            "primary": "SHA-256 of ordered original retail glyph bitmaps",
            "normalization": "leading and trailing all-zero padding glyphs removed",
            "fallback": "SHA-256 of exact retail source record bytes",
        },
        "english_comparison_normalization": "collapse all whitespace and line wrapping to one space before duplicate-source semantic comparison",
        "canonical_english_source": str(SOURCES),
        "japanese_record_source": str(retail_root / "retail_unpacked"),
        "chapter_order": chapter_order,
        "record_count": len(all_records),
        "duplicate_source_group_count": len(duplicate_groups),
        "conflicting_duplicate_group_count": sum(
            group["conflict"] for group in duplicate_groups
        ),
        "formatting_only_duplicate_group_count": sum(
            group["formatting_only_variants"] for group in duplicate_groups
        ),
        "missing_visible_translation_count": len(missing_visible),
        "missing_visible_translation_ids": missing_visible,
        "blank_source_marked_translate_count": len(false_prose),
        "blank_source_marked_translate_ids": false_prose,
        "duplicate_source_groups": duplicate_groups,
        "records": all_records,
    }


def _markdown(payload: dict[str, object]) -> str:
    """Render the audit payload as a deterministic Markdown review table."""
    lines = [
        "# Nostalgia 1907 exact-source translation audit",
        "",
        f"- Records: {payload['record_count']}",
        f"- Duplicate Japanese source groups: {payload['duplicate_source_group_count']}",
        f"- Conflicting duplicate-source groups: {payload['conflicting_duplicate_group_count']}",
        f"- Formatting-only duplicate variants (not conflicts): {payload['formatting_only_duplicate_group_count']}",
        f"- Missing visible translations: {payload['missing_visible_translation_count']}",
        f"- Blank/control sources marked as prose: {payload['blank_source_marked_translate_count']}",
        "",
        "## Duplicate Japanese source groups",
        "",
    ]
    for group in payload["duplicate_source_groups"]:
        conflict = (
            "CONFLICT"
            if group["conflict"]
            else (
                "formatting variants only"
                if group["formatting_only_variants"]
                else "consistent"
            )
        )
        lines.extend(
            [
                f"### {group['normalized_bitmap_sha256']} ({conflict})",
                "",
                f"Category: `{group['category']}`",
                "",
                "| Record ID | Current English |",
                "|---|---|",
            ]
        )
        for record in group["records"]:
            english = (
                str(record["english_rendered"]).replace("\n", " ↵ ").replace("|", "\\|")
                or "[missing]"
            )
            lines.append(f"| {record['id']} | {english} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Write JSON and Markdown audit reports for command-line review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--label", default="translation_conflicts")
    args = parser.parse_args()
    payload = audit(args.retail_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    json_path = args.output_root / f"{args.label}.json"
    md_path = args.output_root / f"{args.label}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "record_count": payload["record_count"],
                "duplicate_source_group_count": payload["duplicate_source_group_count"],
                "conflicting_duplicate_group_count": payload[
                    "conflicting_duplicate_group_count"
                ],
                "formatting_only_duplicate_group_count": payload[
                    "formatting_only_duplicate_group_count"
                ],
                "missing_visible_translation_count": payload[
                    "missing_visible_translation_count"
                ],
                "blank_source_marked_translate_count": payload[
                    "blank_source_marked_translate_count"
                ],
                "json": str(json_path),
                "markdown": str(md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

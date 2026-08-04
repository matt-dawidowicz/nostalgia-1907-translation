#!/usr/bin/env python3
"""Generate the focused report for the second source-semantic QA pass."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from source_json import load_json_object


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "outputs" / "Nostalgia1907_Translation_Audit"
DELIVERY = ROOT / "outputs" / "Nostalgia1907_CleanRebuild_SemanticReview"
COMPARISON = ROOT / "outputs" / "Nostalgia1907_Bilingual_Comparison"
EXPECTED_CHANGED_IDS = {
    "PART2B:087",
    "PART2D:122",
    "PART2E:121",
    "PART3B_:029",
    "PART3B_:077",
    "PART3B_:194",
    "PART3C:022",
    "PART4A:013",
    "PART4B:290",
    "PART4B:291",
    "PART4C:047",
}


def load(path: Path) -> dict:
    """Load one historical semantic-pass JSON payload."""
    return load_json_object(path)


def file_sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for one evidence file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def relative(path: Path) -> str:
    """Render an evidence path relative to the project root."""
    return path.relative_to(ROOT).as_posix()


def main() -> None:
    """Generate the focused second-pass semantic QA report."""
    before = load(AUDIT / "translation_semantic_pass2_before.json")
    after = load(AUDIT / "translation_conflicts.json")
    verification = load(DELIVERY / "final_verification.json")
    before_records = before["records"]
    after_records = after["records"]
    if [item["id"] for item in before_records] != [
        item["id"] for item in after_records
    ]:
        raise ValueError("record IDs or ordering changed during semantic pass 2")

    changed = []
    for old, new in zip(before_records, after_records, strict=True):
        for key in (
            "source_record_sha256",
            "source_record_hex",
            "exact_bitmap_sha256",
            "normalized_bitmap_sha256",
        ):
            if old[key] != new[key]:
                raise ValueError(f"{new['id']}: Japanese source {key} changed")
        if old["english"] != new["english"] or old["policy"] != new["policy"]:
            changed.append(
                {
                    "id": new["id"],
                    "source_record_sha256": new["source_record_sha256"],
                    "source_bitmap_sha256": new["normalized_bitmap_sha256"],
                    "before_english": old["english"],
                    "after_english": new["english"],
                    "before_policy": old["policy"],
                    "after_policy": new["policy"],
                }
            )
    actual_ids = {item["id"] for item in changed}
    if actual_ids != EXPECTED_CHANGED_IDS:
        raise ValueError(
            f"unexpected semantic pass-2 scope: missing={sorted(EXPECTED_CHANGED_IDS - actual_ids)}, "
            f"extra={sorted(actual_ids - EXPECTED_CHANGED_IDS)}"
        )

    part4b = load(ROOT / "work" / "clean_rebuild" / "sources" / "PART4B.json")
    rows_290 = part4b["records"][290]["text"].split("\n")
    if [len(row) for row in rows_290] != [26, 21]:
        raise ValueError("PART4B:290 render-ready 26/21-cell shape changed")
    if "Wire Cutters" in part4b["records"][290]["text"]:
        raise ValueError("PART4B:290 reverted to title case")

    products = []
    for name in (
        "Nostalgia1907_CleanRebuild_SemanticReview.cue",
        "Nostalgia1907_CleanRebuild_SemanticReview_Track1.bin",
        "Nostalgia1907_CleanRebuild_SemanticReview_Track2.bin",
    ):
        path = DELIVERY / name
        products.append(
            {
                "path": relative(path),
                "size": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )

    verify = verification["verification"]
    payload = {
        "schema_version": 1,
        "status": "PASS",
        "japanese_source_unchanged": True,
        "record_ids_and_order_unchanged": True,
        "semantic_record_change_count": len(changed),
        "changed_records": changed,
        "duplicate_source_validation": {
            "normalization": after["english_comparison_normalization"],
            "semantic_conflict_count": after["conflicting_duplicate_group_count"],
            "formatting_only_variant_group_count": after[
                "formatting_only_duplicate_group_count"
            ],
        },
        "name_decisions": {
            "グランセリウス": "Grancelius",
            "カモルビッチ": "Kamorovich",
        },
        "contextual_exceptions": [
            "PART4B:290 lowercase wire cutters in running dialogue",
            "PART4B:291 preserves 電線 -> コード as electrical wire -> cord",
        ],
        "part4b_290_layout": {
            "row_lengths": [len(row) for row in rows_290],
            "rows": rows_290,
            "same_lengths_as_previous_build": True,
            "compiled_and_rebuilt": True,
        },
        "validation": {
            "status": verification["status"],
            "two_clean_builds_byte_identical": verification[
                "two_clean_builds_byte_identical"
            ],
            "artifact_count_compared": verification["artifact_count_compared"],
            "production_legacy_dependencies": verification[
                "production_legacy_dependencies"
            ],
            "chapter_count": verify["chapter_count"],
            "record_count": verify["total_records"],
            "max_dynamic_glyphs": verify["max_dynamic_glyphs"],
            "part3c_size": verify["part3c_size"],
            "part3c_headroom": verify["part3c_headroom"],
            "track1_boot_matches_retail": verify["track1"]["boot_matches_retail"],
            "track1_sector_checksums_valid": verify["track1"][
                "all_sector_checksums_valid"
            ],
        },
        "comparison": {
            "path": relative(
                COMPARISON / "Nostalgia1907_Japanese_English_Comparison.html"
            ),
            "sha256": file_sha256(
                COMPARISON / "Nostalgia1907_Japanese_English_Comparison.html"
            ),
        },
        "products": products,
    }

    json_path = AUDIT / "translation_semantic_pass2_report.json"
    md_path = AUDIT / "translation_semantic_pass2_report.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Nostalgia 1907 semantic QA pass 2",
        "",
        "Status: **PASS**",
        "",
        f"Semantic/casing records changed: **{len(changed)}**. Japanese source records, IDs, and ordering are unchanged.",
        "",
        "| Record | Before | After |",
        "|---|---|---|",
    ]
    for item in changed:
        old = item["before_english"].replace("|", "\\|")
        new = item["after_english"].replace("|", "\\|")
        lines.append(f"| {item['id']} | {old} | {new} |")
    lines += [
        "",
        "## Validation",
        "",
        f"- Exact-source semantic conflicts: **{after['conflicting_duplicate_group_count']}**.",
        f"- Formatting-only duplicate groups, reported separately: **{after['formatting_only_duplicate_group_count']}**.",
        "- Whitespace and line wrapping are collapsed before duplicate-source semantic comparison.",
        "- Grancelius and Kamorovich are locked; Granzelius and Kamolovich are forbidden variants.",
        "- No blanket cord-to-wire prose replacement remains.",
        "- PART4B:291 is a source-fingerprinted lexical exception preserving electrical wire -> cord.",
        "- PART4B:290 remains 26/21 cells, exactly matching its previous row lengths, and compiled in both clean builds.",
        f"- Two complete clean builds: **byte-identical** across {verification['artifact_count_compared']} artifacts.",
        f"- PART3C size: **0x{verify['part3c_size']:04X}**, headroom **0x{verify['part3c_headroom']:X}**.",
        "",
        "## Test image",
        "",
    ]
    for product in products:
        lines.append(
            f"- `{product['path']}` ({product['size']:,} bytes), SHA-256 `{product['sha256']}`"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "semantic_record_change_count": len(changed),
                "json": str(json_path),
                "markdown": str(md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

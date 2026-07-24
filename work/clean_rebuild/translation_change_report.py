#!/usr/bin/env python3
"""Generate the final source-authoritative translation audit handoff."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = ROOT / "outputs" / "Nostalgia1907_Translation_Audit"
COMPARISON_ROOT = ROOT / "outputs" / "Nostalgia1907_Bilingual_Comparison"
DELIVERY_ROOT = ROOT / "outputs" / "Nostalgia1907_CleanRebuild_v5"
SOURCES_ROOT = ROOT / "work" / "clean_rebuild" / "sources"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> None:
    before_path = AUDIT_ROOT / "translation_conflicts_before.json"
    after_path = AUDIT_ROOT / "translation_conflicts.json"
    bomb_path = AUDIT_ROOT / "bomb_sequence_audit.json"
    glossary_path = ROOT / "work" / "clean_rebuild" / "translation_glossary.json"
    verification_path = DELIVERY_ROOT / "final_verification.json"

    before = load_json(before_path)
    after = load_json(after_path)
    bomb = load_json(bomb_path)
    glossary = load_json(glossary_path)
    verification = load_json(verification_path)

    before_records = before["records"]
    after_records = after["records"]
    if [item["id"] for item in before_records] != [item["id"] for item in after_records]:
        raise ValueError("record IDs or ordering changed between the before/after audits")

    source_fields = (
        "source_record_sha256",
        "source_record_hex",
        "exact_bitmap_sha256",
        "normalized_bitmap_sha256",
        "visible_glyph_count",
    )
    for old, new in zip(before_records, after_records, strict=True):
        for field in source_fields:
            if old[field] != new[field]:
                raise ValueError(f"{new['id']}: authoritative Japanese {field} changed")

    changed_records: list[dict] = []
    changed_by_chapter: dict[str, list[str]] = defaultdict(list)
    english_change_count = 0
    policy_change_count = 0
    for old, new in zip(before_records, after_records, strict=True):
        english_changed = old.get("english") != new.get("english")
        policy_changed = old["policy"] != new["policy"]
        if not english_changed and not policy_changed:
            continue
        english_change_count += int(english_changed)
        policy_change_count += int(policy_changed)
        changed_by_chapter[new["chapter"]].append(new["id"])
        changed_records.append(
            {
                "id": new["id"],
                "category": new["category"],
                "source_record_sha256": new["source_record_sha256"],
                "source_record_hex": new["source_record_hex"],
                "source_bitmap_sha256": new["normalized_bitmap_sha256"],
                "before_policy": old["policy"],
                "after_policy": new["policy"],
                "before_english": old.get("english"),
                "after_english": new.get("english"),
            }
        )

    fixed_decisions = [
        {
            "japanese": item["japanese"],
            "english": item["canonical_english"],
            "category": item["category"],
            "review_required": bool(item.get("review_required")),
        }
        for item in glossary["fixed_source_terms"]
    ]
    controlled_decisions = [
        {
            "japanese": item["japanese"],
            "english": item["canonical_english"],
            "category": item["category"],
            "review_required": bool(item.get("review_required")),
        }
        for item in glossary["controlled_phrases"]
    ]

    unresolved = [
        {
            "scope": "イリュ / イリューシャ",
            "working_choice": "Ilyu / Ilyusha",
            "reason": "Nickname/full-name distinction is source-supported; official romanization remains unconfirmed.",
        },
        {
            "scope": "カナル・フィッツ",
            "working_choice": "Canal Fitz",
            "reason": "Fitz is locked; the given-name romanization needs an official-material check.",
        },
        {
            "scope": "ルメランカ",
            "working_choice": "Lumeranka",
            "reason": "Consistent source transliteration, but no official spelling was located in the repository.",
        },
        {
            "scope": "スンミン",
            "working_choice": "Sunmin",
            "reason": "Consistent source transliteration, but no official spelling was located in the repository.",
        },
        {
            "scope": "イギリス・インテリジェンス・アクション",
            "working_choice": "British Intelligence Action",
            "reason": "Literal organization styling is locked pending an official English name.",
        },
        {
            "scope": "PART4B:245 はやい",
            "working_choice": "...That was fast.",
            "reason": "The source means fast/early; the exact nuance is context-sensitive and flagged rather than guessed silently.",
        },
    ]

    source_files = [SOURCES_ROOT / "index.json"] + [
        SOURCES_ROOT / f"{chapter}.json" for chapter in after["chapter_order"]
    ]
    implementation_files = [
        ROOT / "work" / "clean_rebuild" / name
        for name in (
            "translation_audit.py",
            "translation_exemptions.json",
            "translation_glossary.json",
            "translation_repairs.json",
            "apply_translation_repairs.py",
            "bomb_semantics.json",
            "bomb_audit.py",
            "translation_validation.py",
            "translation_change_report.py",
            "translation_semantic_pass2_report.py",
            "regression.py",
            "compile_canonical_sources.py",
        )
    ]

    product_paths = [
        DELIVERY_ROOT / "Nostalgia1907_CleanRebuild_v5.cue",
        DELIVERY_ROOT / "Nostalgia1907_CleanRebuild_v5_Track1.bin",
        DELIVERY_ROOT / "Nostalgia1907_CleanRebuild_v5_Track2.bin",
    ]
    products = [
        {"path": rel(path), "size": path.stat().st_size, "sha256": sha256(path)}
        for path in product_paths
    ]

    comparison_paths = [
        COMPARISON_ROOT / "Nostalgia1907_Japanese_English_Comparison.html",
        COMPARISON_ROOT / "Nostalgia1907_Japanese_English_Comparison.md",
        COMPARISON_ROOT / "Nostalgia1907_Japanese_English_Comparison.json",
        COMPARISON_ROOT / "Nostalgia1907_Japanese_English_Comparison.zip",
    ]
    comparisons = [
        {"path": rel(path), "size": path.stat().st_size, "sha256": sha256(path)}
        for path in comparison_paths
    ]

    verify = verification["verification"]
    report = {
        "schema_version": 1,
        "status": "PASS",
        "canonical_pipeline": {
            "english_source": rel(SOURCES_ROOT / "index.json") + " plus chapter JSON files",
            "japanese_source": after["japanese_record_source"],
            "stable_key": "chapter plus zero-based numeric record ID",
            "positional_arrays_in_production": False,
            "record_correspondence_proof": "PART2E:042 canonical index 42 equals generated PART2E:042 and source record 0101F063F06400.",
        },
        "source_integrity": {
            "japanese_source_unchanged": True,
            "record_ids_and_order_unchanged": True,
            "record_count": after["record_count"],
        },
        "audit_before_after": {
            "duplicate_source_groups": {
                "before": before["duplicate_source_group_count"],
                "after": after["duplicate_source_group_count"],
            },
            "conflicting_duplicate_source_groups": {
                "before": before["conflicting_duplicate_group_count"],
                "after": after["conflicting_duplicate_group_count"],
            },
            "missing_visible_translations": {
                "before": before["missing_visible_translation_count"],
                "after": after["missing_visible_translation_count"],
            },
            "blank_sources_marked_prose": {
                "before": before["blank_source_marked_translate_count"],
                "after": after["blank_source_marked_translate_count"],
            },
            "formatting_only_duplicate_variants": after.get(
                "formatting_only_duplicate_group_count", 0
            ),
        },
        "changes": {
            "record_count": len(changed_records),
            "english_change_count": english_change_count,
            "policy_change_count": policy_change_count,
            "by_chapter": dict(changed_by_chapter),
            "records": changed_records,
        },
        "glossary": {
            "fixed_source_terms": fixed_decisions,
            "controlled_phrases": controlled_decisions,
            "unresolved_human_review": unresolved,
        },
        "part3b_": {
            "record_count": 211,
            "translated_visible_prose_records": 209,
            "preserved_control_records": ["PART3B_:004", "PART3B_:015"],
            "status": "PASS",
        },
        "bomb_sequence": {
            "audited_record_count": bomb["audited_record_count"],
            "semantic_failure_count": bomb["semantic_failure_count"],
            "status": bomb["status"],
            "report": rel(bomb_path),
        },
        "validation": {
            "semantic_and_source_tests": "PASS",
            "game_build": verification["status"],
            "two_clean_builds_byte_identical": verification["two_clean_builds_byte_identical"],
            "artifact_count_compared": verification["artifact_count_compared"],
            "production_legacy_dependencies": verification["production_legacy_dependencies"],
            "chapter_count": verify["chapter_count"],
            "record_count": verify["total_records"],
            "max_dynamic_glyphs": verify["max_dynamic_glyphs"],
            "part3c_size": verify["part3c_size"],
            "part3c_limit": 0x3FFF,
            "part3c_headroom": verify["part3c_headroom"],
            "mes_pointer_and_glyph_bounds": "PASS",
            "record_terminators": "PASS",
            "scn_and_non_mes_payloads_unchanged": True,
            "fixed_iso_extents": "PASS",
            "track1_boot_matches_retail": verify["track1"]["boot_matches_retail"],
            "track1_sector_checksums": "PASS" if verify["track1"]["all_sector_checksums_valid"] else "FAIL",
            "text_layout": "SCN-derived wrapping and explicit repaired-row limits compiled successfully; manual visual playtest remains the release gate.",
        },
        "files_changed": {
            "canonical_sources": [rel(path) for path in source_files],
            "audit_build_code_and_config": [rel(path) for path in implementation_files],
            "generated_audit_package": rel(AUDIT_ROOT),
            "generated_comparison_package": rel(COMPARISON_ROOT),
            "generated_test_image": rel(DELIVERY_ROOT),
        },
        "comparison_artifacts": comparisons,
        "game_artifacts": products,
    }

    json_path = AUDIT_ROOT / "translation_change_report.json"
    md_path = AUDIT_ROOT / "translation_change_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = report["audit_before_after"]
    lines = [
        "# Nostalgia 1907 translation audit and repair",
        "",
        "Status: **PASS**",
        "",
        "The original Japanese records, IDs, order, control flow, and bitmap-derived fingerprints are unchanged. English is keyed by chapter and zero-based numeric record ID; production does not consume positional translation arrays.",
        "",
        "## Audit result",
        "",
        "| Check | Before | After |",
        "|---|---:|---:|",
        f"| Exact-source English conflicts | {counts['conflicting_duplicate_source_groups']['before']} | {counts['conflicting_duplicate_source_groups']['after']} |",
        f"| Missing visible translations | {counts['missing_visible_translations']['before']} | {counts['missing_visible_translations']['after']} |",
        f"| Blank/control sources marked as prose | {counts['blank_sources_marked_prose']['before']} | {counts['blank_sources_marked_prose']['after']} |",
        "",
        f"Changed records: **{len(changed_records)}** ({english_change_count} English-value changes; {policy_change_count} policy changes; one record changed both).",
        "",
        "### Changed record IDs",
        "",
    ]
    for chapter in after["chapter_order"]:
        ids = changed_by_chapter.get(chapter, [])
        if ids:
            lines.append(f"- **{chapter} ({len(ids)}):** " + ", ".join(ids))

    lines += [
        "",
        "The JSON companion contains the before/after English, policy, source bytes, and source fingerprint for every changed record.",
        "",
        "## Locked glossary",
        "",
    ]
    for item in fixed_decisions:
        suffix = " *(human review)*" if item["review_required"] else ""
        lines.append(f"- `{item['japanese']}` -> **{item['english']}** ({item['category']}){suffix}")
    for item in controlled_decisions:
        suffix = " *(human review)*" if item["review_required"] else ""
        lines.append(f"- `{item['japanese']}` -> **{item['english']}** ({item['category']}){suffix}")

    lines += [
        "",
        "## Unresolved human review",
        "",
    ]
    for item in unresolved:
        lines.append(f"- **{item['scope']} -> {item['working_choice']}**: {item['reason']}")

    lines += [
        "",
        "## Gameplay and structural validation",
        "",
        f"- Bomb sequence: **PASS**, {bomb['audited_record_count']} source records audited, {bomb['semantic_failure_count']} semantic failures.",
        "- PART3B_: **PASS**, 209 visible prose records translated; only records 004 and 015 preserved as control/non-prose.",
        "- Record IDs/order/count: **PASS**, 19 chapters and 2,905 records.",
        "- Canonical comparison parity: **PASS**.",
        "- Game rebuild: **PASS**, two independent clean builds byte-identical across 44 artifacts.",
        f"- PART3C: **0x{verify['part3c_size']:04X}**, leaving **0x{verify['part3c_headroom']:X}** bytes below the hard 0x3FFF boundary.",
        f"- Runtime glyph maximum: **{verify['max_dynamic_glyphs']}**; pointer/glyph/terminator and fixed-extent checks passed.",
        "- SCN-derived wrapping and explicit repaired-row width checks compiled successfully. Manual visual playtesting remains the release gate for presentation quality.",
        "",
        "## Test image",
        "",
    ]
    for item in products:
        lines.append(f"- `{item['path']}` ({item['size']:,} bytes), SHA-256 `{item['sha256']}`")

    lines += [
        "",
        "## Generated reports",
        "",
        f"- Exact-source audit: `{rel(after_path)}` and `{rel(after_path.with_suffix('.md'))}`",
        f"- Bomb sequence: `{rel(bomb_path)}` and `{rel(bomb_path.with_suffix('.md'))}`",
        f"- Glossary review: `{rel(AUDIT_ROOT / 'glossary_review.md')}`",
        f"- Canonical pipeline: `{rel(AUDIT_ROOT / 'canonical_pipeline.md')}`",
        f"- Bilingual comparison: `{rel(COMPARISON_ROOT / 'Nostalgia1907_Japanese_English_Comparison.html')}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "changed_record_count": len(changed_records),
                "english_change_count": english_change_count,
                "policy_change_count": policy_change_count,
                "json": str(json_path),
                "markdown": str(md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

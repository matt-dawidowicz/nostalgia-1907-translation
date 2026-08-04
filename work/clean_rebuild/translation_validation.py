#!/usr/bin/env python3
"""Enforce semantic, policy, layout, and generated-comparison consistency.

This gate combines source-bitmap auditing, glossary and contextual rules,
reviewed preserve/exemption tables, bomb terminology checks, whole-game
renderer auditing, canonical ID/order checks, and comparison-package freshness.
It detects meaning/policy regressions that a byte-valid MES compiler cannot.

Rules are keyed by stable record IDs and Japanese source fingerprints rather
than by mutable English alone. Layout whitespace is normalized only for
semantic comparison; canonical adaptive/fixed ownership is checked separately
by ``translation_formatter.audit_layouts``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from bomb_audit import run_audit as run_bomb_audit
from export_bilingual_comparison import validate_comparison_package
from mes_compiler import CompileError, compile_mes
from translation_formatter import audit_layouts
from translation_audit import (
    DEFAULT_RETAIL_ROOT,
    SOURCES,
    audit,
    normalize_english_for_semantic_comparison,
)


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
GLOSSARY = HERE / "translation_glossary.json"
REPAIRS = HERE / "translation_repairs.json"
EXEMPTIONS = HERE / "translation_exemptions.json"
DEFAULT_COMPARISON = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Bilingual_Comparison"
    / "Nostalgia1907_Japanese_English_Comparison.json"
)
EXPECTED_CHAPTERS = 19
EXPECTED_RECORDS = 2905


def _load(path: Path) -> dict[str, object]:
    """Load a tracked UTF-8 JSON object used by semantic validation."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _audit_compiled_renderer_contracts() -> dict[str, object]:
    """Compile every chapter in memory and verify its emitted cursor stream.

    ``audit_layouts`` checks semantic rows.  This companion gate also executes
    the compiler's emitted-byte audit, so a build cannot silently differ from
    the preview because fixed and dynamic MES references have different byte
    lengths but identical cursor width.
    """
    index = _load(SOURCES / "index.json")
    failures: list[str] = []
    totals = {
        "chapter_count": 0,
        "record_count": 0,
        "row_count": 0,
        "cell_count": 0,
        "row_edge_count": 0,
    }
    for item in index["chapters"]:
        chapter = item["chapter"]
        retail = DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter
        try:
            result = compile_mes(
                (retail / f"{chapter}.MES").read_bytes(),
                (retail / f"{chapter}.SCN").read_bytes(),
                _load(SOURCES / item["source"]),
            )
        except (CompileError, OSError, ValueError) as error:
            failures.append(f"{chapter}: emitted renderer contract: {error}")
            continue
        totals["chapter_count"] += 1
        totals["record_count"] += result.renderer_contract_records
        totals["row_count"] += result.renderer_contract_rows
        totals["cell_count"] += result.renderer_contract_cells
        totals["row_edge_count"] += result.renderer_contract_row_edges
    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        **totals,
    }


def _normalized(value: object) -> str:
    """Collapse presentation whitespace for configured phrase comparisons."""
    return re.sub(r"\s+", " ", value if isinstance(value, str) else "").strip()


def validate(
    comparison_json: Path, *, require_comparison: bool = True
) -> dict[str, object]:
    """Validate canonical meaning, policy, layout, and comparison freshness.

    Args:
        comparison_json: Generated bilingual comparison manifest to verify.
        require_comparison: Whether a missing comparison is a mandatory
            failure. Source-only diagnostic callers may disable this check.

    Returns:
        A JSON-serializable summary whose ``status`` is ``PASS`` only when all
        mandatory semantic, source, renderer, and comparison checks succeed.

    Raises:
        OSError: If required source or prepared-retail files cannot be read.
        ValueError: If a tracked rule table or source object is malformed.

    Side Effects:
        Reads source, retail, rule, and optional comparison files; writes
        nothing. Individual failures are accumulated in the returned report.
    """
    exact = audit(DEFAULT_RETAIL_ROOT)
    glossary = _load(GLOSSARY)
    repairs = _load(REPAIRS)
    exemptions = _load(EXEMPTIONS)
    failures: list[str] = []
    if normalize_english_for_semantic_comparison(
        "same\n  words"
    ) != normalize_english_for_semantic_comparison("same words"):
        failures.append("duplicate-source whitespace/line-wrap normalization is broken")
    if exact["record_count"] != EXPECTED_RECORDS:
        failures.append(f"record count changed: {exact['record_count']}")
    if len(exact["chapter_order"]) != EXPECTED_CHAPTERS:
        failures.append(f"chapter count changed: {len(exact['chapter_order'])}")
    if exact["conflicting_duplicate_group_count"]:
        failures.append(
            "identical Japanese source fingerprints have conflicting English"
        )
    if exact["missing_visible_translation_count"]:
        failures.append("visible Japanese source records are missing English")
    if exact["blank_source_marked_translate_count"]:
        failures.append("blank/control source records are marked as prose")

    records_by_id = {item["id"]: item for item in exact["records"]}
    by_fingerprint: dict[str, list[dict[str, object]]] = {}
    for record in exact["records"]:
        by_fingerprint.setdefault(record["normalized_bitmap_sha256"], []).append(record)

    for term in glossary["fixed_source_terms"]:
        representative = records_by_id.get(term["source_record_id"])
        if (
            representative is None
            or representative["normalized_bitmap_sha256"]
            != term["normalized_bitmap_sha256"]
        ):
            failures.append(f"glossary source fingerprint changed for {term['id']}")
            continue
        for record in by_fingerprint.get(term["normalized_bitmap_sha256"], []):
            if (
                record["policy"] == "translate"
                and record["english"] != term["canonical_english"]
            ):
                failures.append(
                    f"{record['id']}: glossary {term['japanese']} requires {term['canonical_english']!r}, got {record['english']!r}"
                )

    for term in glossary["controlled_phrases"]:
        for record_id in term.get("record_ids", []):
            record = records_by_id.get(record_id)
            if record is None:
                failures.append(
                    f"{term['id']}: controlled record is missing: {record_id}"
                )
            elif term["canonical_english"] not in record["english"]:
                failures.append(
                    f"{record_id}: controlled {term['japanese']} must use {term['canonical_english']!r}"
                )

    for expected in glossary.get("source_authoritative_records", []):
        record_id = expected["record_id"]
        record = records_by_id.get(record_id)
        if record is None:
            failures.append(f"source-authoritative record is missing: {record_id}")
            continue
        if record["source_record_sha256"] != expected["source_record_sha256"]:
            failures.append(f"{record_id}: Japanese source hash changed")
        expected_english = normalize_english_for_semantic_comparison(
            expected["expected_english"]
        )
        if record["english"] != expected_english:
            failures.append(
                f"{record_id}: source-authoritative English changed: {record['english']!r}"
            )

    for exception in glossary.get("reviewed_contextual_exceptions", []):
        record_id = exception["record_id"]
        record = records_by_id.get(record_id)
        if record is None:
            failures.append(f"reviewed contextual exception is missing: {record_id}")
            continue
        if record["normalized_bitmap_sha256"] != exception["normalized_bitmap_sha256"]:
            failures.append(
                f"{record_id}: contextual-exception Japanese fingerprint changed"
            )
        if not re.search(exception["required_english_pattern"], record["english"]):
            failures.append(f"{record_id}: reviewed contextual distinction disappeared")
        forbidden = exception.get("forbidden_english_pattern")
        if forbidden and re.search(forbidden, record["english"]):
            failures.append(f"{record_id}: forbidden contextual rendering returned")

    for rule in repairs["bomb_term_replacements"]:
        pattern = re.compile(rule["pattern"])
        if any(
            pattern.sub(rule["replacement"], sample) != sample
            for sample in ("cord", "cords")
        ):
            failures.append("blanket cord-to-wire prose replacement is forbidden")

    all_english = "\n".join(
        record["english"] for record in exact["records"] if record["english"]
    )
    for pattern in glossary["forbidden_english_patterns"]:
        if re.search(pattern, all_english):
            failures.append(f"known noncanonical English variant remains: {pattern}")
    if "British Intelligence Action" not in all_english:
        failures.append("canonical British Intelligence Action name disappeared")
    if "Mede" not in all_english or "Medea" not in all_english:
        failures.append("Mede/Medea source distinction disappeared")

    for record_id in repairs["preserve_records"]:
        record = records_by_id[record_id]
        if record["policy"] != "preserve" or record["english"]:
            failures.append(f"{record_id}: reviewed control/punctuation policy changed")
    for table_name in (
        "reviewed_visible_translation_exemptions",
        "reviewed_control_records",
    ):
        for record_id, item in exemptions[table_name].items():
            if records_by_id[record_id]["policy"] != item["expected_policy"]:
                failures.append(f"{record_id}: reviewed exemption policy changed")

    index = _load(SOURCES / "index.json")
    canonical_text_by_id: dict[str, object] = {}
    expected_ids: list[str] = []
    for chapter_item in index["chapters"]:
        chapter = chapter_item["chapter"]
        source = _load(SOURCES / chapter_item["source"])
        records = source.get("records")
        if not isinstance(records, list) or len(records) != source.get("record_count"):
            failures.append(f"{chapter}: canonical record table is incomplete")
            continue
        if any(
            record.get("index") != position for position, record in enumerate(records)
        ):
            failures.append(f"{chapter}: canonical IDs/order are not contiguous")
        translated = sum(record.get("policy") == "translate" for record in records)
        preserved = sum(record.get("policy") == "preserve" for record in records)
        if translated != chapter_item.get(
            "translated_records"
        ) or preserved != chapter_item.get("preserved_records"):
            failures.append(f"{chapter}: index policy counts are stale")
        for record in records:
            record_id = f"{chapter}:{record['index']:03d}"
            expected_ids.append(record_id)
            canonical_text_by_id[record_id] = record.get("text")

    part3b = _load(SOURCES / "PART3B_.json")
    part3b_preserved = {
        record["index"]
        for record in part3b["records"]
        if record["policy"] == "preserve"
    }
    if part3b.get("record_count") != 211 or part3b_preserved != {4, 15}:
        failures.append(f"PART3B_ classification changed: {sorted(part3b_preserved)}")
    if sum(record["policy"] == "translate" for record in part3b["records"]) != 209:
        failures.append("PART3B_ no longer has 209 translated prose records")
    for record_id, expected in {
        "PART3B_:001": "Cargo Hold",
        "PART3B_:005": "Ruthie",
        "PART3B_:039": "Old Karl",
        "PART3B_:078": "Second-Class Cabin",
    }.items():
        if records_by_id[record_id]["english"] != expected:
            failures.append(f"{record_id}: PART3B_ glossary regression")

    bomb = run_bomb_audit()
    failures.extend(f"bomb: {failure}" for failure in bomb["semantic_failures"])

    layout = audit_layouts(DEFAULT_RETAIL_ROOT)
    failures.extend(f"layout: {failure}" for failure in layout["failures"])

    emitted_renderer = _audit_compiled_renderer_contracts()
    failures.extend(
        f"emitted-renderer: {failure}" for failure in emitted_renderer["failures"]
    )

    comparison_checked = False
    comparison_package_checked = False
    comparison_package: dict[str, object] = {
        "status": "NOT_CHECKED",
        "failure_count": 0,
        "failures": [],
        "member_count": 0,
    }
    if comparison_json.exists():
        comparison = _load(comparison_json)
        generated = [
            record
            for chapter in comparison["chapters"]
            for record in chapter["records"]
        ]
        generated_ids = [record["id"] for record in generated]
        if generated_ids != expected_ids:
            failures.append(
                "generated comparison record IDs/order differ from canonical source"
            )
        for record in generated:
            record_id = record["id"]
            if record.get("english") != canonical_text_by_id.get(record_id):
                failures.append(f"{record_id}: generated comparison English is stale")
            if (
                record.get("source_record_hex")
                != records_by_id[record_id]["source_record_hex"]
            ):
                failures.append(
                    f"{record_id}: generated comparison Japanese source is stale"
                )
        comparison_checked = True
        comparison_package = validate_comparison_package(comparison_json.parent)
        comparison_package_checked = True
        failures.extend(
            f"comparison-package: {failure}"
            for failure in comparison_package["failures"]
        )
    elif require_comparison:
        failures.append(f"generated comparison is missing: {comparison_json}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "chapter_count": len(exact["chapter_order"]),
        "record_count": exact["record_count"],
        "exact_source_conflicts": exact["conflicting_duplicate_group_count"],
        "formatting_only_duplicate_variants": exact[
            "formatting_only_duplicate_group_count"
        ],
        "missing_visible_translations": exact["missing_visible_translation_count"],
        "blank_sources_marked_prose": exact["blank_source_marked_translate_count"],
        "glossary_fixed_terms": len(glossary["fixed_source_terms"]),
        "reviewed_contextual_exceptions": len(
            glossary.get("reviewed_contextual_exceptions", [])
        ),
        "bomb_records_audited": bomb["audited_record_count"],
        "bomb_semantic_failures": bomb["semantic_failure_count"],
        "layout_classified_records": layout["classified_record_count"],
        "adaptive_layout_records": layout["adaptive_record_count"],
        "legacy_layout_issues": layout["legacy_issue_count"],
        "emitted_renderer_contract_status": emitted_renderer["status"],
        "emitted_renderer_contract_failures": emitted_renderer["failure_count"],
        "emitted_renderer_contract_records": emitted_renderer["record_count"],
        "emitted_renderer_contract_rows": emitted_renderer["row_count"],
        "emitted_renderer_contract_cells": emitted_renderer["cell_count"],
        "emitted_renderer_contract_row_edges": emitted_renderer["row_edge_count"],
        "comparison_checked": comparison_checked,
        "comparison_package_checked": comparison_package_checked,
        "comparison_package_status": comparison_package["status"],
        "comparison_package_member_count": comparison_package["member_count"],
        "comparison_package_failure_count": comparison_package["failure_count"],
    }


def main() -> None:
    """Run validation and exit nonzero when any mandatory rule fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-json", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--allow-missing-comparison", action="store_true")
    args = parser.parse_args()
    payload = validate(
        args.comparison_json, require_comparison=not args.allow_missing_comparison
    )
    print(json.dumps(payload, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

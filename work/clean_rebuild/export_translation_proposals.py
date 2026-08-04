#!/usr/bin/env python3
"""Export pending translation-polish proposals without applying them.

Japanese wording comes only from the tracked, human-reviewed
``bomb_semantics.json`` evidence. Retail MES bytes and glyph-preview hashes bind
an active proposal to an exact record; they are never used to invent Unicode
readings. When no proposal is pending, the exporter returns a source-only,
explicit empty report without requiring retail fixtures. No canonical source,
translated archive, or game BIN/CUE is written.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from iso9660 import read_entries, unique_file
from lz_format import parse_archive
from mes_compiler import _measure_literal, compile_mes
from mes_format import changed_record_indexes, parse_mes
from translation_formatter import _contracts, _record_audit, _rules_by_role
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
EVIDENCE = HERE / "bomb_semantics.json"
DEFAULT_COMPARISON = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Bilingual_Comparison"
    / "Nostalgia1907_Japanese_English_Comparison.json"
)
DEFAULT_JSON = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Translation_Audit"
    / "translation_polish_proposals.json"
)
DEFAULT_MARKDOWN = DEFAULT_JSON.with_suffix(".md")
PROPOSALS: dict[str, dict[str, str]] = {}


def _sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _sha256_bytes(payload: bytes) -> str:
    """Return an uppercase SHA-256 digest for in-memory bytes."""
    return hashlib.sha256(payload).hexdigest().upper()


def _canonical_chapters() -> dict[str, tuple[Path, dict[str, object]]]:
    """Load canonical chapter files in index order without modifying them."""
    index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
    return {
        item["chapter"]: (
            SOURCES / item["source"],
            json.loads((SOURCES / item["source"]).read_text(encoding="utf-8")),
        )
        for item in index["chapters"]
    }


def _comparison_records(path: Path) -> dict[str, dict[str, object]]:
    """Return comparison records keyed by exact stable ID."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        record["id"]: record
        for chapter in payload["chapters"]
        for record in chapter["records"]
    }


def _archive_boundary_context(
    retail_root: Path,
    chapter: str,
    current_mes: bytes,
    proposed_mes: bytes,
) -> dict[str, object]:
    """Prove conservative archive capacity without creating archive bytes.

    Production stores the smaller of its compressed payload and unpacked MES.
    The proposed MES byte length is therefore a hard upper bound on replacement
    payload size. Using that upper bound proves a lower bound on fixed-slot and
    guarded-reflow headroom without running the expensive compressor or writing
    a translated LZ artifact. Exact final compressed bytes are not claimed.
    """
    retail_archive = retail_root / "retail_archives" / f"{chapter}.LZ"
    archive_data = retail_archive.read_bytes()
    entries = parse_archive(archive_data, source=str(retail_archive))
    member_name = f"{chapter}.MES"
    matches = [entry for entry in entries if entry.name == member_name]
    if len(matches) != 1:
        raise ValueError(
            f"{retail_archive}: expected one member named {member_name!r}, "
            f"found {len(matches)}"
        )
    entry = matches[0]
    slot_end = (
        entries[entry.index + 1].offset
        if entry.index + 1 < len(entries)
        else len(archive_data)
    )
    slot_size = slot_end - entry.offset
    iso_entry = unique_file(
        read_entries(retail_root / "retail.iso"),
        f"{chapter}.LZ",
    )
    untouched_stored_bytes = sum(
        item.compressed_size for item in entries if item.index != entry.index
    )
    payload_start = entries[0].offset
    conservative_payload_end = (
        payload_start + untouched_stored_bytes + len(proposed_mes)
    )
    conservative_archive_size = max(len(archive_data), conservative_payload_end)
    fixed_raw_fit = len(proposed_mes) <= slot_size
    reflow_raw_fit = conservative_archive_size <= iso_entry.allocated_size
    if fixed_raw_fit:
        assessment = "PASS_FIXED_SLOT_WITHOUT_COMPRESSION"
        reason = (
            "The complete proposed MES fits its retail member slot even if stored "
            "uncompressed; production compression can only improve headroom."
        )
    elif reflow_raw_fit:
        assessment = "PASS_GUARDED_REFLOW_WITHOUT_COMPRESSION"
        reason = (
            "The complete proposed MES fits the ISO allocation under guarded reflow "
            "even if stored uncompressed; production compression can only improve "
            "headroom."
        )
    else:
        assessment = "INCONCLUSIVE_REQUIRES_PRODUCTION_COMPRESSION"
        reason = (
            "The uncompressed upper bound exceeds the guarded allocation. Exact fit "
            "depends on production compression and is intentionally not claimed in "
            "this no-build proposal pass."
        )
    return {
        "assessment": assessment,
        "method": "uncompressed proposed MES as replacement-payload upper bound",
        "reason": reason,
        "retail_archive_path": retail_archive.relative_to(retail_root).as_posix(),
        "retail_archive_sha256": _sha256(retail_archive),
        "retail_archive_size": len(archive_data),
        "iso_logical_size": iso_entry.size,
        "iso_allocated_size": iso_entry.allocated_size,
        "iso_allocation_headroom_over_retail_archive": (
            iso_entry.allocated_size - len(archive_data)
        ),
        "member": member_name,
        "member_index": entry.index,
        "member_offset": entry.offset,
        "member_slot_end": slot_end,
        "member_slot_size": slot_size,
        "retail_member_stored_size": entry.compressed_size,
        "retail_member_unpacked_size": entry.unpacked_size,
        "retail_member_slot_headroom": slot_size - entry.compressed_size,
        "current_compiled_mes_size": len(current_mes),
        "proposed_compiled_mes_size": len(proposed_mes),
        "uncompressed_mes_delta": len(proposed_mes) - len(current_mes),
        "fixed_slot_fit_without_compression": fixed_raw_fit,
        "fixed_slot_headroom_if_stored_uncompressed": (slot_size - len(proposed_mes)),
        "conservative_reflow_payload_end": conservative_payload_end,
        "conservative_reflow_archive_size_upper_bound": conservative_archive_size,
        "guarded_reflow_fit_without_compression": reflow_raw_fit,
        "guarded_reflow_headroom_lower_bound": (
            iso_entry.allocated_size - conservative_archive_size
        ),
        "production_recompression_performed": False,
        "archive_written": False,
        "disc_build_performed": False,
        "exact_final_archive_size_or_hash_claimed": False,
        "limit": (
            "The exact compressed member/archive size and archive SHA-256 remain "
            "unknown until an approved production recompression. A false raw-fit "
            "result is inconclusive, not a predicted build failure."
        ),
    }


def build_proposals(
    retail_root: Path,
    comparison_json: Path,
) -> dict[str, object]:
    """Compile and measure every proposal while leaving canonical sources intact."""
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    expectations = evidence["record_expectations"]
    evidence_hash = _sha256(EVIDENCE)
    reports: list[dict[str, object]] = []

    if not PROPOSALS:
        return {
            "status": "NO_PENDING_PROPOSALS",
            "proposal_count": 0,
            "canonical_sources_modified": False,
            "bin_cue_built": False,
            "authoritative_evidence_file": EVIDENCE.relative_to(WORKSPACE).as_posix(),
            "authoritative_evidence_sha256": evidence_hash,
            "proposals": reports,
        }

    comparison = _comparison_records(comparison_json)
    comparison_root = comparison_json.parent
    chapters = _canonical_chapters()
    rules = _rules_by_role()

    for record_id, proposal in PROPOSALS.items():
        chapter, index_text = record_id.split(":", 1)
        record_index = int(index_text)
        source_path, canonical = chapters[chapter]
        canonical_record = canonical["records"][record_index]
        current = canonical_record["text"]
        if not isinstance(current, str):
            raise ValueError(f"{record_id}: canonical current text is not a string")
        authoritative = expectations.get(record_id)
        if not isinstance(authoritative, dict):
            raise ValueError(f"{record_id}: reviewed Japanese evidence is missing")
        if authoritative.get("corrected_english") != current:
            raise ValueError(
                f"{record_id}: evidence no longer matches canonical English"
            )
        comparison_record = comparison.get(record_id)
        if comparison_record is None:
            raise ValueError(
                f"{record_id}: exact retail comparison evidence is missing"
            )

        retail_mes_path = retail_root / "retail_unpacked" / chapter / f"{chapter}.MES"
        retail_scn_path = retail_root / "retail_unpacked" / chapter / f"{chapter}.SCN"
        retail_mes = retail_mes_path.read_bytes()
        retail_scn = retail_scn_path.read_bytes()
        current_result = compile_mes(retail_mes, retail_scn, canonical)
        proposed_canonical = copy.deepcopy(canonical)
        proposed_canonical["records"][record_index]["text"] = proposal["proposed"]
        proposed_result = compile_mes(retail_mes, retail_scn, proposed_canonical)
        current_parsed = parse_mes(current_result.data, source=f"current {chapter}")
        proposed_parsed = parse_mes(proposed_result.data, source=f"proposal {chapter}")
        changed_indexes = changed_record_indexes(current_parsed, proposed_parsed)

        contract = _contracts(canonical, retail_root).get(record_index)
        current_audit = _record_audit(
            record_id,
            current,
            canonical["text_mode"] == "adaptive"
            or canonical_record.get("layout_policy") == "adaptive",
            contract,
            rules,
        )
        proposed_audit = _record_audit(
            record_id,
            str(proposal["proposed"]),
            canonical["text_mode"] == "adaptive"
            or canonical_record.get("layout_policy") == "adaptive",
            contract,
            rules,
        )
        if proposed_audit["failures"]:
            raise ValueError(
                f"{record_id}: proposal fails layout audit: {proposed_audit['failures']}"
            )
        current_rows = list(current_audit["preview_rows"])
        proposed_rows = list(proposed_audit["preview_rows"])
        current_cells = [_measure_literal(row) for row in current_rows]
        proposed_cells = [_measure_literal(row) for row in proposed_rows]
        image_path = comparison_root / comparison_record["japanese_image"]
        archive_impact = _archive_boundary_context(
            retail_root,
            chapter,
            current_result.data,
            proposed_result.data,
        )
        reports.append(
            {
                "record_id": record_id,
                "chapter": chapter,
                "record_index": record_index,
                "canonical_source": source_path.relative_to(WORKSPACE).as_posix(),
                "authoritative_japanese_evidence": {
                    "file": EVIDENCE.relative_to(WORKSPACE).as_posix(),
                    "file_sha256": evidence_hash,
                    "key": f"record_expectations/{record_id}",
                    "japanese": authoritative["japanese"],
                    "literal": authoritative["literal"],
                    "provenance_note": (
                        "Tracked human-reviewed Japanese/literal evidence; not decoded "
                        "from mojibake or inferred from raw bytes."
                    ),
                },
                "retail_source_binding": {
                    "record_bytes": len(
                        bytes.fromhex(str(comparison_record["source_record_hex"]))
                    ),
                    "record_sha256": _sha256_bytes(
                        bytes.fromhex(str(comparison_record["source_record_hex"]))
                    ),
                    "token_stream_sha256": _sha256_bytes(
                        str(comparison_record["source_tokens"]).encode("utf-8")
                    ),
                    "visible_glyphs": comparison_record["japanese_visible_glyphs"],
                    "preview_path": comparison_record["japanese_image"],
                    "preview_sha256": (
                        _sha256(image_path) if image_path.is_file() else "MISSING"
                    ),
                    "retail_mes_sha256": _sha256(retail_mes_path),
                    "retail_scn_sha256": _sha256(retail_scn_path),
                },
                "current_english": current,
                "proposed_english": proposal["proposed"],
                "semantic_style_rationale": proposal["rationale"],
                "recommendation": proposal["recommendation"],
                "confidence": proposal["confidence"],
                "layout": {
                    "classification": canonical_record.get("layout_policy"),
                    "roles": proposed_audit["roles"],
                    "contract": proposed_audit["layout"],
                    "max_rows": proposed_audit["max_rows"],
                    "current_preview_rows": current_rows,
                    "current_row_characters": [len(row) for row in current_rows],
                    "current_row_two_character_cells": current_cells,
                    "proposed_preview_rows": proposed_rows,
                    "proposed_row_characters": [len(row) for row in proposed_rows],
                    "proposed_row_two_character_cells": proposed_cells,
                    "proposal_failures": proposed_audit["failures"],
                    "proposal_warnings": proposed_audit["warnings"],
                    "runtime_limit": (
                        "Static renderer contract only; runtime scene capture remains "
                        "the final correctness gate."
                    ),
                },
                "encoded_size_and_boundary_impact": {
                    "current_record_bytes": len(current_parsed.records[record_index]),
                    "proposed_record_bytes": len(proposed_parsed.records[record_index]),
                    "record_byte_delta": (
                        len(proposed_parsed.records[record_index])
                        - len(current_parsed.records[record_index])
                    ),
                    "current_record_sha256": _sha256_bytes(
                        current_parsed.records[record_index]
                    ),
                    "proposed_record_sha256": _sha256_bytes(
                        proposed_parsed.records[record_index]
                    ),
                    "compiled_mes_current_size": len(current_result.data),
                    "compiled_mes_proposed_size": len(proposed_result.data),
                    "compiled_mes_size_delta": len(proposed_result.data)
                    - len(current_result.data),
                    "current_split_offset": current_result.split_offset,
                    "proposed_split_offset": proposed_result.split_offset,
                    "split_offset_delta": proposed_result.split_offset
                    - current_result.split_offset,
                    "current_dynamic_glyphs": current_result.dynamic_glyphs,
                    "proposed_dynamic_glyphs": proposed_result.dynamic_glyphs,
                    "dynamic_glyph_delta": proposed_result.dynamic_glyphs
                    - current_result.dynamic_glyphs,
                    "current_rendered_cells": current_result.rendered_cells,
                    "proposed_rendered_cells": proposed_result.rendered_cells,
                    "rendered_cell_delta": proposed_result.rendered_cells
                    - current_result.rendered_cells,
                    "encoded_records_changed_count": len(changed_indexes),
                    "encoded_records_changed": list(changed_indexes),
                    "record_count_preserved": (
                        current_parsed.record_count == proposed_parsed.record_count
                    ),
                    "scn_bytes_changed": False,
                    "part3c_hard_limit": "NOT_APPLICABLE",
                    "archive_boundary_context": archive_impact,
                    "disc_build_performed": False,
                },
            }
        )
    return {
        "status": "PASS",
        "proposal_count": len(reports),
        "canonical_sources_modified": False,
        "bin_cue_built": False,
        "authoritative_evidence_file": EVIDENCE.relative_to(WORKSPACE).as_posix(),
        "authoritative_evidence_sha256": evidence_hash,
        "proposals": reports,
    }


def write_markdown(path: Path, payload: dict[str, object]) -> None:
    """Write the proposal evidence and impact report in reviewer-friendly form."""
    lines = [
        "# Translation-polish proposals - approval required",
        "",
        "No canonical translation was changed and no game BIN/CUE was built. Japanese "
        "readings below come only from the tracked human-reviewed "
        "`bomb_semantics.json` entries identified by file hash and key. Retail record, "
        "token-stream, and preview hashes bind each note to the exact source record; "
        "raw retail records and preview images are intentionally not embedded.",
        "",
        "| ID | Current | Proposed | Confidence | Recommendation |",
        "|---|---|---|---|---|",
    ]
    if not payload["proposals"]:
        lines.extend(
            [
                "",
                "No translation-polish proposals are currently pending approval.",
            ]
        )
    for item in payload["proposals"]:
        lines.append(
            f"| `{item['record_id']}` | {item['current_english']} | "
            f"{item['proposed_english']} | {item['confidence']} | "
            f"{item['recommendation']} |"
        )
    for item in payload["proposals"]:
        evidence = item["authoritative_japanese_evidence"]
        binding = item["retail_source_binding"]
        layout = item["layout"]
        impact = item["encoded_size_and_boundary_impact"]
        archive = impact["archive_boundary_context"]
        lines.extend(
            [
                "",
                f"## {item['record_id']}",
                "",
                f"- **Authoritative evidence:** `{evidence['file']}` "
                f"SHA-256 `{evidence['file_sha256']}`, key `{evidence['key']}`.",
                f"- **Reviewed Japanese:** {evidence['japanese']}",
                f"- **Reviewed literal:** {evidence['literal']}",
                f"- **Evidence provenance:** {evidence['provenance_note']}",
                f"- **Retail source binding:** MES SHA-256 `{binding['retail_mes_sha256']}`; "
                f"record {binding['record_bytes']} bytes / SHA-256 "
                f"`{binding['record_sha256']}`; token-stream SHA-256 "
                f"`{binding['token_stream_sha256']}`; visible glyphs "
                f"`{binding['visible_glyphs']}`; "
                f"preview `{binding['preview_path']}` SHA-256 "
                f"`{binding['preview_sha256']}`.",
                f"- **Current English:** `{item['current_english']}`",
                f"- **Proposed English:** `{item['proposed_english']}`",
                f"- **Rationale:** {item['semantic_style_rationale']}",
                f"- **Layout classification:** `{layout['classification']}`; roles "
                f"`{layout['roles']}`; max rows `{layout['max_rows']}`.",
                f"- **Current preview / widths:** `{layout['current_preview_rows']}`; "
                f"characters `{layout['current_row_characters']}`; two-character cells "
                f"`{layout['current_row_two_character_cells']}`.",
                f"- **Proposed preview / widths:** `{layout['proposed_preview_rows']}`; "
                f"characters `{layout['proposed_row_characters']}`; two-character cells "
                f"`{layout['proposed_row_two_character_cells']}`; failures "
                f"`{layout['proposal_failures']}`; warnings `{layout['proposal_warnings']}`.",
                f"- **Encoded record impact:** {impact['current_record_bytes']} -> "
                f"{impact['proposed_record_bytes']} bytes "
                f"({impact['record_byte_delta']:+d}); compiled MES "
                f"{impact['compiled_mes_current_size']} -> "
                f"{impact['compiled_mes_proposed_size']} bytes "
                f"({impact['compiled_mes_size_delta']:+d}); split offset "
                f"{impact['current_split_offset']} -> {impact['proposed_split_offset']} "
                f"({impact['split_offset_delta']:+d}); dynamic glyphs "
                f"{impact['current_dynamic_glyphs']} -> {impact['proposed_dynamic_glyphs']} "
                f"({impact['dynamic_glyph_delta']:+d}).",
                f"- **Archive/boundary capacity proof:** proposed MES upper bound "
                f"`{archive['proposed_compiled_mes_size']}` bytes; retail member slot "
                f"`{archive['member_slot_size']}`; fixed-slot fit without compression "
                f"`{archive['fixed_slot_fit_without_compression']}`. Guarded-reflow "
                f"allocation `{archive['iso_allocated_size']}`; fit even if stored "
                f"uncompressed `{archive['guarded_reflow_fit_without_compression']}`; "
                f"headroom lower bound "
                f"`{archive['guarded_reflow_headroom_lower_bound']}` bytes. Record "
                f"count preserved `{impact['record_count_preserved']}`; SCN changed "
                f"`{impact['scn_bytes_changed']}`; archive written "
                f"`{archive['archive_written']}`; disc build performed "
                f"`{impact['disc_build_performed']}`.",
                f"- **Archive-test limit:** {archive['limit']}",
                f"- **Recommendation / confidence:** {item['recommendation']} "
                f"**{item['confidence']}**.",
                f"- **Limit:** {layout['runtime_limit']}",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines).rstrip() + "\n").encode("utf-8"))


def main() -> None:
    """Generate proposal JSON and Markdown without modifying canonical sources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--comparison-json", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    payload = build_proposals(args.retail_root, args.comparison_json)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    write_markdown(args.markdown, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "proposal_count": payload["proposal_count"],
                "canonical_sources_modified": False,
                "bin_cue_built": False,
                "json": str(args.json),
                "markdown": str(args.markdown),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

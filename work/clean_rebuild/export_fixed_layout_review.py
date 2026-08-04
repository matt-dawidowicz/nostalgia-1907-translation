#!/usr/bin/env python3
"""Create a complete runtime-review queue for fixed-layout translations.

The queue does not infer missing geometry and does not rewrite canonical text.
It combines the current canonical English, the renderer audit, and exact retail
MES source evidence already represented by the bilingual comparison package.
Japanese Unicode is never reconstructed from byte streams or mojibake.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from renderer_format import measure_literal
from source_json import load_json_object
from translation_formatter import audit_layouts
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
DEFAULT_COMPARISON = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Bilingual_Comparison"
    / "Nostalgia1907_Japanese_English_Comparison.json"
)
DEFAULT_TSV = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Translation_Audit"
    / "fixed_layout_runtime_review.tsv"
)
DEFAULT_MARKDOWN = DEFAULT_TSV.with_suffix(".md")
PRIORITY_PART4C = {f"PART4C:{index:03d}" for index in range(51, 60)}
EXPECTED_FIXED_RECORDS = 123


def _sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for one evidence file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _sha256_bytes(data: bytes) -> str:
    """Return an uppercase SHA-256 digest for in-memory source evidence."""
    return hashlib.sha256(data).hexdigest().upper()


def _load_canonical() -> dict[str, dict[str, object]]:
    """Return current canonical records keyed by stable record ID."""
    index = load_json_object(SOURCES / "index.json")
    records: dict[str, dict[str, object]] = {}
    for item in index["chapters"]:
        chapter = item["chapter"]
        source = load_json_object(SOURCES / item["source"])
        for record in source["records"]:
            records[f"{chapter}:{record['index']:03d}"] = record
    return records


def _comparison_records(path: Path) -> dict[str, dict[str, object]]:
    """Load exact retail source representations from one comparison JSON."""
    comparison = load_json_object(path)
    return {
        record["id"]: record
        for chapter in comparison["chapters"]
        for record in chapter["records"]
    }


def _risk(record_id: str, text: str, row_cells: list[int]) -> tuple[int, str, str]:
    """Assign a review priority without pretending to know runtime geometry."""
    if record_id in PRIORITY_PART4C:
        return (
            1,
            "HIGH",
            (
                "Contiguous PART4C ending-sequence record with no SCN-derived "
                "geometry immediately after ordinary adaptive dialogue. The nine "
                "records may share special transition/placement behavior, and "
                "PART4C:054 reaches 41 characters in one fixed row."
            ),
        )
    if len(row_cells) > 1 or max(row_cells, default=0) >= 18 or text != text.strip():
        return (
            2,
            "ELEVATED",
            (
                "No proven width/row/placement contract, with length, explicit "
                "line structure, or edge whitespace that could affect clipping "
                "or alignment."
            ),
        )
    return (
        3,
        "UNRESOLVED",
        "Fixed presentation remains statically unproven and requires runtime evidence.",
    )


def _runtime_evidence(record_id: str) -> str:
    """Describe the exact replay evidence still required for one record."""
    sequence = (
        " Capture PART4C:051 through PART4C:059 in one uninterrupted replay to "
        "verify transitions and shared placement."
        if record_id in PRIORITY_PART4C
        else ""
    )
    return (
        f"Replay the exact scene/branch that displays {record_id}. Record a full-frame "
        "capture before text appears, at complete display, and at dismissal/advance; "
        "identify text origin, available horizontal cells/pixels, row count and stride, "
        "centering/leading-space behavior, clipping, overwrite/page behavior, and input "
        "timing. Compare the retail Japanese display with the current playtest candidate."
        + sequence
    )


def build_queue(
    retail_root: Path,
    comparison_json: Path,
) -> list[dict[str, object]]:
    """Build all fixed-layout review rows without changing project sources."""
    layout = audit_layouts(retail_root)
    if layout["status"] != "PASS":
        raise ValueError(
            "layout audit must pass before creating the fixed-layout queue"
        )
    canonical = _load_canonical()
    comparison = _comparison_records(comparison_json)
    comparison_root = comparison_json.parent
    rows: list[dict[str, object]] = []
    for item in layout["records"]:
        if item.get("layout_policy") != "fixed":
            continue
        record_id = str(item["id"])
        if item.get("roles") or item.get("layout"):
            raise ValueError(
                f"{record_id}: fixed queue unexpectedly has proven geometry"
            )
        source = comparison.get(record_id)
        record = canonical.get(record_id)
        if source is None or record is None:
            raise ValueError(f"{record_id}: comparison/canonical evidence is missing")
        text = record.get("text")
        if not isinstance(text, str):
            raise ValueError(f"{record_id}: fixed translated text is not a string")
        exact_rows = text.split("\n")
        row_cells = [measure_literal(row) for row in exact_rows]
        image_relative = str(source["japanese_image"])
        image_path = comparison_root / image_relative
        image_hash = _sha256(image_path) if image_path.is_file() else "MISSING"
        record_bytes = bytes.fromhex(str(source["source_record_hex"]))
        token_stream = str(source["source_tokens"]).encode("utf-8")
        priority, risk, rationale = _risk(record_id, text, row_cells)
        chapter, index_text = record_id.split(":", 1)
        rows.append(
            {
                "priority": priority,
                "risk": risk,
                "record_id": record_id,
                "chapter_resource": f"{chapter}.LZ / {chapter}.MES record {int(index_text)}",
                "japanese_source_authority": (
                    "Hash-locked retail MES record rendered with retail FIX_CODE.FNT/"
                    "dynamic glyph bank; no OCR or inferred Unicode. Raw retail bytes, "
                    "token streams, and preview images are intentionally not embedded "
                    "in this delivery queue."
                ),
                "japanese_source_record_bytes": len(record_bytes),
                "japanese_source_record_sha256": _sha256_bytes(record_bytes),
                "japanese_source_token_stream_sha256": _sha256_bytes(token_stream),
                "japanese_visible_glyphs": source["japanese_visible_glyphs"],
                "japanese_image_reference": image_relative,
                "japanese_image_sha256": image_hash,
                "current_english": text,
                "renderer_layout_classification": (
                    "fixed; no safe SCN-derived role or Layout contract"
                ),
                "available_width": "UNKNOWN - not proven by static SCN inference",
                "available_rows": "UNKNOWN - no safe maximum row count inferred",
                "placement_information": (
                    "UNKNOWN - origin, alignment, row stride, clear/redraw behavior, "
                    "and page timing require runtime capture"
                ),
                "adaptive_unavailable_reason": (
                    "The hash-locked retail SCN yielded neither a renderer role nor "
                    "shared geometry for this record. Adaptive wrapping would invent "
                    "width, row, and placement rules."
                ),
                "static_preview": " | ".join(exact_rows),
                "measured_exact_rows": len(exact_rows),
                "measured_row_characters": ",".join(
                    str(len(row)) for row in exact_rows
                ),
                "measured_row_two_character_cells": ",".join(
                    str(value) for value in row_cells
                ),
                "static_result": (
                    "Canonical fixed text is structurally measurable only; no static "
                    "preview proves runtime fit, centering, clipping, or timing."
                ),
                "risk_assessment": rationale,
                "runtime_scene_or_replay_evidence_needed": _runtime_evidence(record_id),
            }
        )
    if len(rows) != EXPECTED_FIXED_RECORDS:
        raise ValueError(
            f"fixed-layout queue contains {len(rows)} records, expected {EXPECTED_FIXED_RECORDS}"
        )
    rows.sort(key=lambda row: (int(row["priority"]), str(row["record_id"])))
    return rows


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write the complete review queue as UTF-8 tab-separated values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)


def _escape_table(value: object) -> str:
    """Escape one compact value for a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def write_markdown(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a prioritized human-readable fixed-layout review document."""
    high = [row for row in rows if row["priority"] == 1]
    elevated = [row for row in rows if row["priority"] == 2]
    lines = [
        "# Fixed-layout runtime review queue",
        "",
        f"This queue contains all **{len(rows)}** translated records whose canonical "
        "layout policy is `fixed` because static SCN analysis did not prove a safe "
        "renderer geometry. It is a runtime-review queue, not evidence that any line "
        "fits or fails in the game.",
        "",
        "Japanese evidence is identified by cryptographic digests of the exact retail "
        "MES record and decoded token stream, plus the hash of the separately generated "
        "retail-glyph preview. Raw retail records and preview images are intentionally "
        "not embedded. No Japanese reading is inferred from undecoded bytes.",
        "",
        "## Priority summary",
        "",
        f"- Priority 1 / high risk: **{len(high)}** records (`PART4C:051` through "
        "`PART4C:059`).",
        f"- Priority 2 / elevated static indicators: **{len(elevated)}** records.",
        f"- Remaining unresolved runtime reviews: **{len(rows) - len(high) - len(elevated)}** records.",
        "",
        "### Why PART4C:051-PART4C:059 are first",
        "",
        "These nine records form a contiguous ending-sequence block immediately after "
        "ordinary adaptive dialogue, but every record lacks a safe SCN-derived role, "
        "width, row count, or placement contract. Their adjacency suggests that they "
        "may share transition or placement behavior that static analysis cannot see, "
        "while `PART4C:054` contains 41 English characters in one fixed row. "
        "Converting or rewrapping them automatically would guess at centering, timing, "
        "and overwrite behavior. They need one uninterrupted retail-versus-candidate capture.",
        "",
        "| Priority | ID | Current English | Cells by exact row | Risk |",
        "|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['priority']} | `{row['record_id']}` | "
            f"{_escape_table(row['current_english'])} | "
            f"{row['measured_row_two_character_cells']} | {row['risk']} |"
        )
    lines.extend(["", "## Complete record details", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['record_id']} - priority {row['priority']} / {row['risk']}",
                "",
                f"- **Resource:** {row['chapter_resource']}",
                f"- **Japanese authority:** {row['japanese_source_authority']}",
                f"- **Retail record binding:** {row['japanese_source_record_bytes']} "
                f"bytes; SHA-256 `{row['japanese_source_record_sha256']}`; token-stream "
                f"SHA-256 `{row['japanese_source_token_stream_sha256']}`; visible glyphs "
                f"`{row['japanese_visible_glyphs']}`.",
                f"- **Preview reference/hash:** `{row['japanese_image_reference']}` / "
                f"`{row['japanese_image_sha256']}`",
                f"- **Current English:** `{row['current_english']}`",
                f"- **Classification:** {row['renderer_layout_classification']}",
                f"- **Width / rows / placement:** {row['available_width']}; "
                f"{row['available_rows']}; {row['placement_information']}",
                f"- **Why adaptive formatting is unavailable:** "
                f"{row['adaptive_unavailable_reason']}",
                f"- **Static measurement:** {row['measured_exact_rows']} exact row(s); "
                f"characters `{row['measured_row_characters']}`; two-character cells "
                f"`{row['measured_row_two_character_cells']}`; preview "
                f"`{row['static_preview']}`.",
                f"- **Risk:** {row['risk_assessment']}",
                f"- **Runtime evidence still needed:** "
                f"{row['runtime_scene_or_replay_evidence_needed']}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines).rstrip() + "\n").encode("utf-8"))


def main() -> None:
    """Run the fixed-layout review export without modifying canonical sources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--comparison-json", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--tsv", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    rows = build_queue(args.retail_root, args.comparison_json)
    write_tsv(args.tsv, rows)
    write_markdown(args.markdown, rows)
    print(
        json.dumps(
            {
                "status": "PASS",
                "fixed_record_count": len(rows),
                "priority_part4c_count": sum(
                    row["record_id"] in PRIORITY_PART4C for row in rows
                ),
                "tsv": str(args.tsv),
                "markdown": str(args.markdown),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

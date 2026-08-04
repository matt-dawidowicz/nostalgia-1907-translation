#!/usr/bin/env python3
"""Apply source-authoritative, stable-ID translation repairs to canonical JSON."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

from source_json import load_json_object

from renderer_format import normalize_ellipsis_style
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES, audit


HERE = Path(__file__).resolve().parent
GLOSSARY = HERE / "translation_glossary.json"
REPAIRS = HERE / "translation_repairs.json"


def _load(path: Path) -> dict[str, object]:
    """Load one canonical JSON object while rejecting incompatible roots."""
    return load_json_object(path)


def _normalized(value: str) -> str:
    """Collapse prose whitespace for semantic adaptive-text comparisons."""
    return re.sub(r"\s+", " ", value).strip()


def _canonical_text(value: str, *, adaptive: bool) -> str:
    """Apply global prose style without discarding fixed renderer boundaries.

    Args:
        value: A reviewed repair string, optionally with fixed-layout newlines.
        adaptive: Whether SCN proves that the compiler owns row wrapping.

    Returns:
        Semantic adaptive prose or fixed-layout text with the canonical
        no-space ellipsis style applied.

    Side Effects:
        None.
    """
    return normalize_ellipsis_style(_normalized(value) if adaptive else value)


def _fit_like(old: str, new: str) -> str:
    """Preserve existing render-ready line count and widths when they are explicit."""
    old_lines = old.split("\n")
    explicit_shape = len(old_lines) > 1 or any(
        line != line.rstrip(" ") for line in old_lines
    )
    if not explicit_shape:
        return new
    widths = [len(line) for line in old_lines]
    words = new.split()
    rows: list[str] = []
    cursor = 0
    for width in widths:
        if cursor >= len(words):
            rows.append("")
            continue
        row = words[cursor]
        cursor += 1
        while cursor < len(words) and len(row) + 1 + len(words[cursor]) <= width:
            row += " " + words[cursor]
            cursor += 1
        if len(row) > width:
            raise ValueError(
                f"replacement word does not fit render row {width}: {row!r}"
            )
        rows.append(row)
    if cursor != len(words):
        raise ValueError(f"replacement needs more render rows: {new!r} versus {widths}")
    return "\n".join(row.ljust(width) for row, width in zip(rows, widths, strict=True))


def main() -> None:
    """Apply reviewed source repairs and print a deterministic change report."""
    repairs = _load(REPAIRS)
    glossary = _load(GLOSSARY)
    source_audit = audit(DEFAULT_RETAIL_ROOT)
    records_by_id = {item["id"]: item for item in source_audit["records"]}
    glossary_by_fingerprint = {
        item["normalized_bitmap_sha256"]: item
        for item in glossary["fixed_source_terms"]
    }
    preserve_ids = set(repairs["preserve_records"])
    explicit = repairs["record_replacements"]
    global_rules = [
        (re.compile(item["pattern"]), item["replacement"])
        for item in repairs["english_replacements"]
    ]
    bomb_rules = [
        (re.compile(item["pattern"]), item["replacement"])
        for item in repairs["bomb_term_replacements"]
    ]

    index = _load(SOURCES / "index.json")
    changed: list[dict[str, object]] = []
    pending_writes: list[tuple[Path, dict[str, object]]] = []
    for chapter_item in index["chapters"]:
        chapter = chapter_item["chapter"]
        path = SOURCES / chapter_item["source"]
        canonical = _load(path)
        records = canonical["records"]
        profile = canonical.get("profile")
        required_exact = (
            profile.get("required_text_exact") if isinstance(profile, dict) else None
        )
        for record in records:
            record_id = f"{chapter}:{record['index']:03d}"
            before_policy = record["policy"]
            before_text = record.get("text")
            if record_id in preserve_ids:
                record["policy"] = "preserve"
                record["text"] = None
                if isinstance(required_exact, dict):
                    required_exact.pop(str(record["index"]), None)
            else:
                fingerprint = records_by_id[record_id]["normalized_bitmap_sha256"]
                term = glossary_by_fingerprint.get(fingerprint)
                requested: str | None = None
                preserve_shape = True
                if term is not None:
                    requested = term["canonical_english"]
                if record_id in explicit:
                    requested = explicit[record_id]["text"]
                    preserve_shape = explicit[record_id].get(
                        "preserve_render_shape", True
                    )
                if record["policy"] == "translate" and isinstance(
                    record.get("text"), str
                ):
                    adaptive = record.get("layout_policy") == "adaptive"
                    working = _canonical_text(record["text"], adaptive=adaptive)
                    for pattern, replacement in global_rules:
                        working = pattern.sub(replacement, working)
                    if chapter in {"PART2E", "PART4B"}:
                        for pattern, replacement in bomb_rules:
                            working = pattern.sub(replacement, working)
                    if requested is not None:
                        render_width = explicit.get(record_id, {}).get("render_width")
                        if adaptive:
                            # Adaptive records store semantic text only.  The
                            # MES compiler derives all line wrapping and
                            # runtime padding from the original SCN renderer.
                            working = _normalized(requested)
                        elif isinstance(render_width, int):
                            requested_lines = requested.split("\n")
                            if render_width <= 0 or any(
                                len(line) > render_width for line in requested_lines
                            ):
                                raise ValueError(
                                    f"{record_id}: explicit render width is invalid"
                                )
                            working = "\n".join(
                                line.ljust(render_width) for line in requested_lines
                            )
                        else:
                            working = (
                                _fit_like(working, requested)
                                if preserve_shape
                                else requested
                            )
                    record["text"] = _canonical_text(working, adaptive=adaptive)
                    if (
                        isinstance(required_exact, dict)
                        and str(record["index"]) in required_exact
                    ):
                        required_exact[str(record["index"])] = _canonical_text(
                            working,
                            adaptive=adaptive,
                        )
                elif requested is not None:
                    raise ValueError(
                        f"{record_id}: requested replacement is not a translated record"
                    )
            if before_policy != record["policy"] or before_text != record.get("text"):
                changed.append(
                    {
                        "id": record_id,
                        "before_policy": before_policy,
                        "after_policy": record["policy"],
                        "before": before_text,
                        "after": record.get("text"),
                        "source_fingerprint": records_by_id[record_id][
                            "normalized_bitmap_sha256"
                        ],
                    }
                )
        chapter_item["translated_records"] = sum(
            r["policy"] == "translate" for r in records
        )
        chapter_item["preserved_records"] = sum(
            r["policy"] == "preserve" for r in records
        )
        pending_writes.append((path, canonical))

    for path, canonical in pending_writes:
        path.write_text(
            json.dumps(canonical, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (SOURCES / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "status": "PASS",
        "changed_record_count": len(changed),
        "changed_records": changed,
    }
    report_path = (
        HERE.parents[1]
        / "outputs"
        / "Nostalgia1907_Translation_Audit"
        / "translation_repairs_applied.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "changed_record_count": len(changed),
                "report": str(report_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

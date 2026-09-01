"""Audit bomb instructions directly from original Japanese glyph sequences.

The bomb sequence is branch-sensitive, so ordinary English search is not
sufficient evidence. Reviewed Japanese bitmap slices identify semantic terms
such as wire colors, positions, and actions. Canonical English is then checked
against required and forbidden patterns without modifying any translation.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from source_json import load_json_object

from mes_format import read_mes
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES, _glyphs, _trim_blank


HERE = Path(__file__).resolve().parent
SEMANTICS = HERE / "bomb_semantics.json"
GLYPH_BYTES = 18


def _load(path: Path) -> dict[str, object]:
    """Load one strict UTF-8 JSON object used by bomb semantic rules."""
    return load_json_object(path)


def _normalize(text: object) -> str:
    """Collapse renderer whitespace for English semantic comparisons."""
    return re.sub(r"\s+", " ", text if isinstance(text, str) else "").strip()


def _contains(haystack: tuple[bytes, ...], needle: tuple[bytes, ...]) -> bool:
    """Return whether an exact ordered glyph subsequence is present."""
    return bool(needle) and any(
        haystack[offset : offset + len(needle)] == needle
        for offset in range(len(haystack) - len(needle) + 1)
    )


def run_audit() -> dict[str, object]:
    """Validate bomb-sequence English against reviewed Japanese bitmap terms.

    Returns:
        A JSON-serializable report containing every candidate stable ID,
        source evidence, semantic interpretation, branch notes, and failures.

    Raises:
        ValueError: If rule data, canonical records, or representative glyph
            slices are missing or malformed.
        OSError: If tracked or prepared-retail inputs cannot be read.

    Side Effects:
        Reads canonical source, semantic rules, prepared fonts, and MES files.
        It does not alter canonical English or game data.
    """
    config = _load(SEMANTICS)
    fixed_data = (DEFAULT_RETAIL_ROOT / "retail_files" / "FIX_CODE.FNT").read_bytes()
    fixed = tuple(
        fixed_data[i : i + GLYPH_BYTES] for i in range(0, len(fixed_data), GLYPH_BYTES)
    )
    index = _load(SOURCES / "index.json")
    canonical_by_id: dict[str, str] = {}
    glyphs_by_id: dict[str, tuple[bytes, ...]] = {}
    source_hex_by_id: dict[str, str] = {}
    for chapter_item in index["chapters"]:
        chapter = chapter_item["chapter"]
        canonical = _load(SOURCES / chapter_item["source"])
        mes = read_mes(
            DEFAULT_RETAIL_ROOT / "retail_unpacked" / chapter / f"{chapter}.MES"
        )
        for number, (source_record, english_record) in enumerate(
            zip(mes.records, canonical["records"], strict=True)
        ):
            record_id = f"{chapter}:{number:03d}"
            canonical_by_id[record_id] = _normalize(english_record.get("text"))
            glyphs_by_id[record_id] = _trim_blank(
                _glyphs(source_record, fixed, mes.glyphs)
            )
            source_hex_by_id[record_id] = source_record.hex().upper()

    patterns: list[dict[str, object]] = []
    for item in config["glyph_terms"]:
        start, end = item["slice"]
        pattern = glyphs_by_id[item["representative"]][start:end]
        if not pattern:
            raise ValueError(f"empty Japanese glyph term: {item['semantic']}")
        patterns.append({**item, "pattern": pattern})

    failures: list[str] = []
    table: list[dict[str, object]] = []
    ranges = config["chapter_ranges"]
    expectations = config["record_expectations"]
    candidate_ids: set[str] = set(expectations)
    for chapter, bounds in ranges.items():
        for number in range(bounds[0], bounds[1] + 1):
            record_id = f"{chapter}:{number:03d}"
            source_glyphs = glyphs_by_id[record_id]
            matched = [
                item
                for item in patterns
                if _contains(source_glyphs, item["pattern"])
                and record_id not in item.get("excluded_records", {})
            ]
            if not matched:
                continue
            candidate_ids.add(record_id)
            english = canonical_by_id[record_id]
            matched_names = {term["semantic"] for term in matched}
            action_signal = bool(matched_names & {"wire", "cut", "open", "bypass"})
            for term in matched:
                semantic = term["semantic"]
                if record_id not in expectations:
                    if (
                        semantic in {"upper", "lower", "left", "right", "red", "blue"}
                        and not action_signal
                    ):
                        continue
                    if semantic == "white" and not {"red", "blue"}.issubset(
                        matched_names
                    ):
                        continue
                    if (
                        semantic in {"cut", "open", "wire", "bypass"}
                        and len(
                            matched_names
                            & {
                                "wire",
                                "cut",
                                "open",
                                "bypass",
                                "upper",
                                "lower",
                                "left",
                                "right",
                                "red",
                                "blue",
                                "white",
                            }
                        )
                        < 2
                    ):
                        continue
                required = term.get("required_english")
                forbidden = term.get("forbidden_english")
                required_missing = isinstance(required, str) and not re.search(
                    required, english, re.IGNORECASE
                )
                if required_missing:
                    failures.append(
                        f"{record_id}: Japanese {term['semantic']} missing in English {english!r}"
                    )
                if (
                    required_missing
                    and isinstance(forbidden, str)
                    and re.search(forbidden, english, re.IGNORECASE)
                ):
                    failures.append(
                        f"{record_id}: Japanese {term['semantic']} reversed by English {english!r}"
                    )

    for record_id in sorted(
        candidate_ids, key=lambda value: (value.split(":")[0], int(value.split(":")[1]))
    ):
        expectation = expectations.get(record_id, {})
        english = canonical_by_id[record_id]
        expected = expectation.get("corrected_english")
        if isinstance(expected, str) and english != expected:
            failures.append(f"{record_id}: {english!r} != expected {expected!r}")
        for pattern in expectation.get("required_english", []):
            if not re.search(pattern, english, re.IGNORECASE):
                failures.append(
                    f"{record_id}: English fails semantic requirement {pattern!r}"
                )
        matched_semantics = sorted(
            {
                item["semantic"]
                for item in patterns
                if _contains(glyphs_by_id[record_id], item["pattern"])
            }
        )
        source_hex = source_hex_by_id[record_id]
        table.append(
            {
                "record_id": record_id,
                "japanese_source": expectation.get("japanese"),
                "source_record_hex": source_hex,
                "source_record_sha256": hashlib.sha256(bytes.fromhex(source_hex))
                .hexdigest()
                .upper(),
                "literal_semantic_interpretation": expectation.get("literal")
                or "; ".join(matched_semantics),
                "semantic_terms": matched_semantics,
                "corrected_english": english,
                "branch_or_consequence": expectation.get("branch_or_consequence"),
                "review_required": bool(expectation.get("review_required")),
            }
        )
    return {
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "audited_record_count": len(table),
        "semantic_failure_count": len(failures),
        "semantic_failures": failures,
        "records": table,
    }

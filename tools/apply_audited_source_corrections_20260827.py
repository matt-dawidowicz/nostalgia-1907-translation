#!/usr/bin/env python3
"""Apply the 2026-08-27 retail-Japanese source correction audit."""
from __future__ import annotations

import base64
import json
import re
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN_REBUILD = ROOT / "work" / "clean_rebuild"
SOURCES = CLEAN_REBUILD / "sources"
PAYLOAD_DIR = ROOT / "work" / "reviewed_changes" / ".source_correction_payload_20260827"
sys.path.insert(0, str(CLEAN_REBUILD))
from renderer_format import normalize_ellipsis_style


def norm(value: str) -> str:
    """Collapse prose whitespace for stable semantic comparisons."""
    return re.sub(r"\s+", " ", value).strip()


def fit_like(old: str, new: str) -> str:
    """Preserve explicit render-ready row count and widths."""
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
        raise ValueError(
            f"replacement needs more render rows: {new!r} versus {widths}"
        )
    return "\n".join(
        row.ljust(width) for row, width in zip(rows, widths, strict=True)
    )


def load_changes() -> dict[str, dict[str, str]]:
    """Load the split compressed correction payload in deterministic order."""
    parts = sorted(PAYLOAD_DIR.glob("part*.txt"))
    if [part.name for part in parts] != [f"part{i:02d}.txt" for i in range(6)]:
        raise ValueError("correction payload is incomplete")
    payload = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    return json.loads(zlib.decompress(base64.b64decode(payload)))


def load_json(path: Path) -> dict[str, object]:
    """Load JSON while rejecting duplicate object keys."""
    def no_dupes(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"{path}: duplicate key {key!r}")
            out[key] = value
        return out
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dupes)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def update_required_prefix(
    record_id: str,
    before: str,
    after: str,
    required_prefixes: dict[str, object],
    key: str,
) -> None:
    """Move a stale heading-prefix lock when the audited source changes it."""
    prefix = required_prefixes[key]
    if not isinstance(prefix, str):
        raise ValueError(f"{record_id}: required prefix is not text")
    if after.startswith(prefix):
        return
    if not before.startswith(prefix):
        raise ValueError(
            f"{record_id}: current text does not satisfy its required prefix {prefix!r}"
        )
    if ":" not in prefix or ":" not in after:
        raise ValueError(
            f"{record_id}: replacement violates required prefix {prefix!r}"
        )
    replacement_prefix = after.split(":", 1)[0] + ":"
    if not after.startswith(replacement_prefix):
        raise ValueError(
            f"{record_id}: could not derive replacement prefix from {after!r}"
        )
    required_prefixes[key] = replacement_prefix


def main() -> None:
    changes = load_changes()
    if len(changes) != 345:
        raise ValueError(f"expected 345 audited changes, found {len(changes)}")

    by_chapter: dict[str, dict[int, dict[str, str]]] = {}
    for record_id, spec in changes.items():
        chapter, raw_index = record_id.split(":", 1)
        by_chapter.setdefault(chapter, {})[int(raw_index)] = spec

    changed: list[dict[str, str]] = []
    pending: list[tuple[Path, dict[str, object]]] = []
    for chapter, chapter_changes in sorted(by_chapter.items()):
        path = SOURCES / f"{chapter}.json"
        canonical = load_json(path)
        records = canonical["records"]
        by_index = {int(record["index"]): record for record in records}
        profile = canonical.get("profile")
        required_exact = (
            profile.get("required_text_exact") if isinstance(profile, dict) else None
        )
        required_prefixes = (
            profile.get("required_text_prefixes") if isinstance(profile, dict) else None
        )

        for index, spec in sorted(chapter_changes.items()):
            record_id = f"{chapter}:{index:03d}"
            record = by_index.get(index)
            if record is None:
                raise ValueError(f"{record_id}: record missing")
            if record.get("policy") != "translate" or not isinstance(
                record.get("text"), str
            ):
                raise ValueError(f"{record_id}: expected translated text record")
            before = record["text"]
            if norm(before) != norm(spec["expected"]):
                raise ValueError(
                    f"{record_id}: current text mismatch\n"
                    f"EXPECTED: {spec['expected']!r}\nACTUAL: {before!r}"
                )

            requested = spec["text"]
            adaptive = record.get("layout_policy") == "adaptive"
            after = norm(requested) if adaptive else fit_like(before, requested)
            after = normalize_ellipsis_style(after)
            record["text"] = after

            key = str(index)
            if isinstance(required_exact, dict) and key in required_exact:
                required_exact[key] = after
            if isinstance(required_prefixes, dict) and key in required_prefixes:
                update_required_prefix(
                    record_id, before, after, required_prefixes, key
                )

            changed.append(
                {
                    "id": record_id,
                    "before": before,
                    "after": after,
                    "category": spec["category"],
                }
            )

        if canonical.get("record_count") != len(records):
            raise ValueError(f"{chapter}: record_count mismatch")
        pending.append((path, canonical))

    if len(changed) != 345:
        raise ValueError(f"changed {len(changed)} records; expected 345")

    # Only write after every audited before-text assertion has passed.
    for path, canonical in pending:
        path.write_text(
            json.dumps(canonical, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for path in sorted(SOURCES.glob("*.json")):
        obj = load_json(path)
        if "records" in obj:
            indices = [int(record["index"]) for record in obj["records"]]
            if indices != list(range(len(indices))):
                raise ValueError(f"{path.name}: non-contiguous record indices")

    report = {
        "status": "PASS",
        "changed_record_count": len(changed),
        "changed_records": changed,
    }
    report_path = (
        ROOT
        / "work"
        / "reviewed_changes"
        / "source_corrections_applied_20260827.json"
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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

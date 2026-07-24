#!/usr/bin/env python3
"""Export the canonical English translation for human and AI review."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
DEFAULT_OUTPUT = HERE.parents[1] / "outputs" / "Nostalgia1907_Translation_Review"


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _markdown_chapter(chapter: dict[str, object]) -> str:
    """Render one chapter without changing its canonical text."""
    lines = [
        f"# {chapter['chapter']}",
        "",
        f"Records: {chapter['record_count']}  ",
        f"Text mode: `{chapter['text_mode']}`  ",
        f"Canonical source SHA-256: `{chapter['canonical_sha256']}`",
        "",
    ]
    for record in chapter["records"]:
        lines.extend(
            [
                f"## Record {record['index']:03d}",
                "",
                f"Policy: `{record['policy']}`",
                "",
            ]
        )
        text = record["text"]
        if text:
            lines.extend(["```text", text, "```", ""])
        else:
            lines.extend(["_[Blank/control-only record]_", ""])
    return "\n".join(lines).rstrip() + "\n"


def export_review_script(output_root: Path) -> dict[str, object]:
    """Write consolidated, per-chapter, and lossless structured exports."""
    index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
    chapters: list[dict[str, object]] = []
    translated = 0
    preserved = 0
    blank = 0
    for item in index["chapters"]:
        source_path = SOURCES / item["source"]
        source = json.loads(source_path.read_text(encoding="utf-8"))
        records: list[dict[str, object]] = []
        for expected_index, record in enumerate(source["records"]):
            if record["index"] != expected_index:
                raise ValueError(f"{source['chapter']}: non-contiguous record indexes")
            policy = record["policy"]
            if policy == "translate":
                translated += 1
            elif policy == "preserve":
                preserved += 1
            else:
                raise ValueError(f"{source['chapter']}:{expected_index}: invalid policy")
            text = record["text"]
            if text is not None and not isinstance(text, str):
                raise ValueError(
                    f"{source['chapter']}:{expected_index}: text is not a string or null"
                )
            if text is None or not text.strip():
                blank += 1
            records.append(
                {
                    "index": expected_index,
                    "id": f"{source['chapter']}:{expected_index:03d}",
                    "policy": policy,
                    "text": text,
                    "line_count": text.count("\n") + 1 if text else 0,
                    "character_count": len(text) if text else 0,
                }
            )
        chapters.append(
            {
                "chapter": source["chapter"],
                "text_mode": source["text_mode"],
                "record_count": source["record_count"],
                "canonical_source": item["source"],
                "canonical_sha256": sha256(source_path),
                "records": records,
            }
        )

    payload = {
        "schema_version": 1,
        "title": "Nostalgia 1907 English Translation Review Script",
        "provenance": (
            "Lossless export of the canonical translation sources used by the "
            "clean retail-BIN rebuild. Record IDs and text are unchanged."
        ),
        "review_notes": [
            "Newlines and trailing spaces can be intentional screen-layout constraints.",
            "Preserve-policy and blank entries are non-prose/control records.",
            "This export contains the English translation, not a parallel Japanese transcript.",
            "Proposed revisions should cite the stable chapter:record ID.",
        ],
        "chapter_count": len(chapters),
        "record_count": sum(chapter["record_count"] for chapter in chapters),
        "translated_records": translated,
        "preserved_records": preserved,
        "blank_or_control_records": blank,
        "chapters": chapters,
    }
    if payload["chapter_count"] != 19 or payload["record_count"] != 2905:
        raise ValueError("canonical export coverage changed unexpectedly")

    output_root.mkdir(parents=True, exist_ok=True)
    chapter_root = output_root / "chapters"
    chapter_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "Nostalgia1907_English_Script.json"
    markdown_path = output_root / "Nostalgia1907_English_Script.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    consolidated = [
        "# Nostalgia 1907 English Translation Review Script",
        "",
        "This is the canonical English source used by the clean BIN rebuild.",
        "Record IDs are stable: please cite changes as `CHAPTER:NNN`.",
        "Line breaks and trailing spaces may be constrained by the game interface.",
        "Blank/preserved entries are control records, not missing prose.",
        "This is not a parallel Japanese transcript, so it supports English editing directly;",
        "source-fidelity review still requires comparison with the Japanese game.",
        "",
        f"Chapters: {payload['chapter_count']}  ",
        f"Total records: {payload['record_count']}  ",
        f"Translated records: {payload['translated_records']}  ",
        f"Preserved records: {payload['preserved_records']}",
        "",
    ]
    for chapter in chapters:
        chapter_markdown = _markdown_chapter(chapter)
        (chapter_root / f"{chapter['chapter']}.md").write_text(
            chapter_markdown, encoding="utf-8"
        )
        consolidated.append(chapter_markdown)
    markdown_path.write_text("\n".join(consolidated), encoding="utf-8")

    reconstructed = json.loads(json_path.read_text(encoding="utf-8"))
    for chapter, original in zip(reconstructed["chapters"], chapters, strict=True):
        if [
            (record["index"], record["policy"], record["text"])
            for record in chapter["records"]
        ] != [
            (record["index"], record["policy"], record["text"])
            for record in original["records"]
        ]:
            raise AssertionError(f"{chapter['chapter']}: JSON export was not lossless")

    readme = (
        "# Review package\n\n"
        "- `Nostalgia1907_English_Script.md`: one readable consolidated script.\n"
        "- `Nostalgia1907_English_Script.json`: lossless machine-readable script.\n"
        "- `chapters/`: smaller chapter files for reviewers and limited-context AI tools.\n\n"
        "Ask reviewers to return proposed changes using `CHAPTER:NNN` record IDs. "
        "Do not remove or reorder records. Formatting changes must respect the game layout.\n"
    )
    (output_root / "README.md").write_text(readme, encoding="utf-8")
    zip_path = output_root / "Nostalgia1907_Translation_Review.zip"
    package_files = [
        output_root / "README.md",
        markdown_path,
        json_path,
        *sorted(chapter_root.glob("*.md")),
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in package_files:
            relative = path.relative_to(output_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return {
        "status": "PASS",
        "output_root": str(output_root),
        "chapter_count": payload["chapter_count"],
        "record_count": payload["record_count"],
        "translated_records": translated,
        "preserved_records": preserved,
        "markdown_sha256": sha256(markdown_path),
        "json_sha256": sha256(json_path),
        "zip_sha256": sha256(zip_path),
    }


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export_review_script(args.output_root), indent=2))


if __name__ == "__main__":
    main()

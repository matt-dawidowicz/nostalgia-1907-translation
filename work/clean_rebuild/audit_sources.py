#!/usr/bin/env python3
"""Match playable MES files to historical builders and text-bearing manifests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
OLD_PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
GOLDEN = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Act4_firstpass_credits"
    / "regression"
    / "unpacked"
)
REPORT = HERE / "source_provenance.json"

CHAPTERS = (
    "START", "PART1A", "PART1B", "PART1C", "PART1D", "PART2A", "PART2B",
    "PART2C", "PART2D", "PART2E", "PART2F", "PART3A", "PART3B", "PART3B_",
    "PART3C", "PART4A", "PART4B", "PART4C", "STAFF",
)


def digest(path: Path) -> str:
    """Return uppercase SHA-256 for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def iter_mes(root: Path):
    """Yield generated MES files while skipping bulky verification copies."""
    ignored = {
        "_pep_quality_tools", "nostalgia1907_tools", "regression", "regression_output",
        "verify_all_unpacked", "verify_unpacked", "iso_extract", "iso_extract_verify",
        "archive_candidate_unpacked", "profile_verification",
    }
    for directory, subdirs, files in os.walk(root, topdown=True, onerror=lambda _: None):
        subdirs[:] = [name for name in subdirs if name not in ignored]
        base = Path(directory)
        for name in files:
            if name.upper().endswith(".MES"):
                yield base / name


def manifest_candidates(mes_path: Path, size: int, count: int) -> list[dict[str, object]]:
    """Return adjacent JSON manifests that describe a complete MES build."""
    matches: list[dict[str, object]] = []
    for path in mes_path.parent.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(segments, list) or len(segments) != count:
            continue
        if payload.get("new_size") != size:
            continue
        texts = [item.get("text") for item in segments if isinstance(item, dict)]
        matches.append({
            "path": str(path),
            "segments": len(segments),
            "all_segments_have_text": len(texts) == count and all(isinstance(text, str) for text in texts),
            "profile": payload.get("translation_profile"),
            "output": payload.get("output"),
        })
    return matches


def main() -> None:
    """Write a deterministic provenance report for all 19 playable scripts."""
    golden: dict[str, dict[str, object]] = {}
    hashes: dict[str, str] = {}
    for chapter in CHAPTERS:
        path = GOLDEN / chapter / f"001_{chapter}.MES.unpacked"
        if not path.exists():
            raise FileNotFoundError(path)
        data = path.read_bytes()
        if len(data) < 4:
            raise ValueError(f"truncated golden MES: {path}")
        pointer_count = (int.from_bytes(data[2:4], "big") - 2) // 2
        sha = digest(path)
        golden[chapter] = {
            "path": str(path),
            "size": len(data),
            "sha256": sha,
            "pointer_count": pointer_count,
            "matching_generated_mes": [],
        }
        hashes[sha] = chapter

    roots = [
        OLD_PROJECT / "outputs",
        WORKSPACE / "work" / "act4_translation" / "built",
        WORKSPACE / "work" / "staff_translation" / "built",
        WORKSPACE / "outputs" / "PART3C_transitionfix10_full_fresh",
        WORKSPACE / "outputs" / "Nostalgia1907_Act4_firstpass_credits",
    ]
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in iter_mes(root):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                sha = digest(path)
            except OSError:
                continue
            chapter = hashes.get(sha)
            if chapter is None:
                continue
            info = golden[chapter]
            info["matching_generated_mes"].append({
                "path": str(path),
                "manifests": manifest_candidates(
                    path,
                    int(info["size"]),
                    int(info["pointer_count"]),
                ),
            })

    for chapter in CHAPTERS:
        matches = golden[chapter]["matching_generated_mes"]
        golden[chapter]["has_byte_identical_generated_source"] = bool(matches)
        golden[chapter]["has_text_bearing_manifest"] = any(
            manifest.get("all_segments_have_text")
            for match in matches
            for manifest in match["manifests"]
        )

    report = {
        "status": "PASS",
        "golden_build": str(GOLDEN),
        "chapter_count": len(CHAPTERS),
        "chapters": golden,
        "summary": {
            "byte_identical_generated_sources": sum(
                bool(golden[name]["has_byte_identical_generated_source"]) for name in CHAPTERS
            ),
            "text_bearing_manifests": sum(
                bool(golden[name]["has_text_bearing_manifest"]) for name in CHAPTERS
            ),
        },
    }
    HERE.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        **report["summary"],
        "missing_generated_sources": [
            name for name in CHAPTERS if not golden[name]["has_byte_identical_generated_source"]
        ],
        "missing_text_manifests": [
            name for name in CHAPTERS if not golden[name]["has_text_bearing_manifest"]
        ],
    }, indent=2))


if __name__ == "__main__":
    main()

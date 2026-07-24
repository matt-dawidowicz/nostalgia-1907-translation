#!/usr/bin/env python3
"""Rank PART3C-only global font codes for safe spill-slot recycling."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE = HERE.parent / "part3c_globalfontfix3" / "PART3C_globalfontfix3.MES"
REGRESSION = WORKSPACE / "outputs" / "PART3C_cursorparityfix4_fresh" / "regression_full"
V3_CONFIG = (
    PROJECT
    / "outputs"
    / "nostalgia1907_act3c_000_223_visualfix3"
    / "PART3C_000_223_visualfix3_build_config.json"
)
REPORT = HERE / "recyclable_spill_report.json"
CHAPTERS = {
    "START",
    "PART1A",
    "PART1B",
    "PART1C",
    "PART1D",
    "PART2A",
    "PART2B",
    "PART2C",
    "PART2D",
    "PART2E",
    "PART2F",
    "PART3A",
    "PART3B",
    "PART3B_",
    "PART3C",
    "PART4A",
    "PART4B",
    "PART4C",
    "STAFF",
}

sys.path.insert(0, str(TOOLS))

from mes_probe import parse_mes, segments_for  # noqa: E402


def usage(path: Path) -> Counter[int]:
    """Count one-byte fixed glyph tokens in an MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    spans = segments_for(data, pointers, info.split_offset)
    result: Counter[int] = Counter()
    for span in spans:
        record = data[span.offset : span.offset + span.size]
        offset = 0
        while offset < len(record) - 1:
            value = record[offset]
            if value >= 0xF0:
                offset += 2
            else:
                if 1 <= value <= 0xED:
                    result[value] += 1
                offset += 1
    return result


def main() -> None:
    """Write candidate-only code ownership and occurrence counts."""
    source_usage = usage(SOURCE)
    other_usage: Counter[int] = Counter()
    files = []
    for path in sorted(REGRESSION.glob("*/*.MES.unpacked")):
        chapter = path.parent.name
        if chapter not in CHAPTERS or chapter == "PART3C":
            continue
        counts = usage(path)
        other_usage.update(counts)
        files.append(str(path.relative_to(REGRESSION)))
    config = json.loads(V3_CONFIG.read_text(encoding="utf-8"))
    translation_spills = {
        int(item["code"], 0): item for item in config["fixed_spill_units"]
    }
    candidates = []
    for code in range(1, 0xEE):
        if other_usage[code] or code not in translation_spills:
            continue
        item = translation_spills[code]
        candidates.append(
            {
                "code": f"0x{code:02X}",
                "part3c_occurrences": source_usage[code],
                "other_chapter_occurrences": other_usage[code],
                "visualfix3_unit": item["unit"],
                "visualfix3_declared_occurrences": item["occurrences"],
            }
        )
    candidates.sort(key=lambda item: (item["part3c_occurrences"], item["code"]))
    report = {
        "audited_other_chapters": files,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

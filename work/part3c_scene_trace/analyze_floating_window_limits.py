#!/usr/bin/env python3
"""Compare original and translated byte/cell sizes for PART3C 0x24 windows."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
ORIGINAL_DIR = HERE.parent / "part3c_original_compare" / "original_part3c"
SCN = ORIGINAL_DIR / "000_PART3C.SCN.unpacked"
ORIGINAL_MES = ORIGINAL_DIR / "001_PART3C.MES.unpacked"
CURRENT_MES = HERE / "PART3C_boundarypadfix5.MES"
V4_CONFIG = (
    PROJECT
    / "outputs"
    / "nostalgia1907_act3c_000_223_visualfix4"
    / "PART3C_000_223_visualfix4_build_config.json"
)
REPORT = HERE / "floating_window_limit_report.json"
CELL_WIDTHS = {
    0x07: 4,
    0x08: 5,
    0x09: 5,
    0x0A: 5,
    0x0B: 6,
    0x0C: 7,
    0x0D: 7,
    0x0E: 8,
    0x0F: 8,
    0x10: 9,
    0x12: 10,
}

sys.path.insert(0, str(TOOLS))

from mes_probe import pack_text_pairs, parse_mes, segments_for  # noqa: E402


def records(path: Path) -> list[bytes]:
    """Return exact MES record byte strings."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid:
        raise ValueError(f"invalid MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    return [data[item.offset : item.offset + item.size] for item in spans]


def cells(record: bytes) -> int:
    """Count fixed and dynamic glyph tokens before the terminator."""
    count = 0
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value == 0:
            offset += 1
            continue
        offset += 2 if value in (0xF0, 0xF1) else 1
        count += 1
    return count


def main() -> None:
    """Write a compact audit ordered by SCN offset."""
    original = records(ORIGINAL_MES)
    current = records(CURRENT_MES)
    scn = SCN.read_bytes()
    rows: list[dict[str, object]] = []
    for offset in range(len(scn) - 8):
        if scn[offset] != 0x24 or scn[offset + 5] not in (0x27, 0x28):
            continue
        text_id = int.from_bytes(scn[offset + 6 : offset + 8], "big")
        if not (1 <= text_id <= min(len(original), len(current))):
            continue
        width = CELL_WIDTHS.get(scn[offset + 3])
        if width is None:
            continue
        index = text_id - 1
        original_cells = cells(original[index])
        current_cells = cells(current[index])
        rows.append(
            {
                "scn_offset": offset,
                "scn_offset_hex": f"0x{offset:04X}",
                "record": index,
                "width_cells": width,
                "original": {
                    "raw_size": len(original[index]),
                    "cells": original_cells,
                    "rows": math.ceil(original_cells / width),
                },
                "current": {
                    "raw_size": len(current[index]),
                    "cells": current_cells,
                    "rows": math.ceil(current_cells / width),
                },
            }
        )
    config = json.loads(V4_CONFIG.read_text(encoding="utf-8"))
    entry162 = next(item for item in config["segments"] if item["segment"] == 162)
    phrase = " ".join(str(entry162["text"]).split())
    words = phrase.split()
    wrap_candidates: list[list[str]] = []

    def visit(start: int, built: list[str]) -> None:
        """Enumerate exact-prose wraps whose packed rows fit eight cells."""
        if start == len(words):
            wrap_candidates.append(built)
            return
        for end in range(start + 1, len(words) + 1):
            line = " ".join(words[start:end])
            if len(pack_text_pairs(line)) > 8:
                break
            visit(end, built + [line])

    visit(0, [])
    minimum_rows = min(map(len, wrap_candidates))
    minimum_wraps = [item for item in wrap_candidates if len(item) == minimum_rows]
    report = {
        "command_count": len(rows),
        "first_current_over_40_cells": next(
            (row for row in rows if int(row["current"]["cells"]) > 40), None
        ),
        "first_current_over_5_rows": next(
            (row for row in rows if int(row["current"]["rows"]) > 5), None
        ),
        "record_162_exact_prose_rewrap": {
            "phrase": phrase,
            "minimum_rows_at_8_cells": minimum_rows,
            "minimum_wraps": [
                [
                    {"text": line, "cells": len(pack_text_pairs(line))}
                    for line in candidate
                ]
                for candidate in minimum_wraps
            ],
        },
        "commands": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    focused = [row for row in rows if 0x0A00 <= int(row["scn_offset"]) <= 0x0C00]
    print(json.dumps({
        "command_count": len(rows),
        "first_current_over_40_cells": report["first_current_over_40_cells"],
        "first_current_over_5_rows": report["first_current_over_5_rows"],
        "record_162_exact_prose_rewrap": report["record_162_exact_prose_rewrap"],
        "focused_commands": focused,
    }, indent=2))


if __name__ == "__main__":
    main()

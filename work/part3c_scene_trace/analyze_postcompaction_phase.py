#!/usr/bin/env python3
"""Find remaining exact-prose pair-phase savings in the compacted PART3C."""

from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
MES = HERE / "PART3C_rowparityfix6.MES"
FONT = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh" / "FIX_CODE.FNT"
PHASE = (
    PROJECT
    / "work"
    / "nostalgia1907"
    / "part3c_blackoutfix"
    / "phase_compaction_analysis.json"
)
REPORT = HERE / "postcompaction_phase_report.json"
GLYPH_BYTES = 18

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    encode_dynamic_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def tokenize(record: bytes) -> list[bytes]:
    """Split one record into tokens, excluding its terminator."""
    result: list[bytes] = []
    cursor = 0
    while cursor < len(record) - 1:
        width = 2 if record[cursor] >= 0xF0 else 1
        result.append(record[cursor : cursor + width])
        cursor += width
    if cursor != len(record) - 1 or record[-1:] != b"\0":
        raise ValueError("invalid record token stream")
    return result


def render(style: str, unit: str) -> bytes:
    """Render one build-config unit in stored orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def main() -> None:
    """Evaluate old phase alternatives against the final token vocabulary."""
    data = MES.read_bytes()
    info, pointers = parse_mes(data, MES)
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    tail = data[info.split_offset :]
    font = FONT.read_bytes()

    def bitmap(token: bytes) -> bytes | None:
        if len(token) == 1 and 1 <= token[0] <= 0xED:
            start = (token[0] - 1) * GLYPH_BYTES
            return font[start : start + GLYPH_BYTES]
        if len(token) == 2:
            index = dynamic_glyph_index(token[0], token[1])
            if index is not None:
                start = index * GLYPH_BYTES
                return tail[start : start + GLYPH_BYTES]
        return None

    vocabulary: dict[bytes, bytes] = {}
    for index in range(len(tail) // GLYPH_BYTES):
        start = index * GLYPH_BYTES
        vocabulary.setdefault(tail[start : start + GLYPH_BYTES], encode_dynamic_index(index))
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        vocabulary[font[start : start + GLYPH_BYTES]] = bytes((code,))

    results = []
    for item in json.loads(PHASE.read_text(encoding="utf-8"))["candidates"]:
        segment = int(item["segment"])
        start = int(item["unit_start"])
        end = int(item["unit_end"])
        current = tokenize(records[segment])
        if end > len(current):
            continue
        expected = [render(str(style), str(unit)) for style, unit in item["current_units"]]
        actual = [bitmap(token) for token in current[start:end]]
        if actual != expected:
            continue
        replacement = []
        for style, unit in item["candidate_units"]:
            token = vocabulary.get(render(str(style), str(unit)))
            if token is None:
                replacement = []
                break
            replacement.append(token)
        if not replacement:
            continue
        saving = sum(map(len, current[start:end])) - sum(map(len, replacement))
        if saving > 0:
            results.append(
                {
                    "segment": segment,
                    "row": int(item["row"]),
                    "unit_start": start,
                    "unit_end": end,
                    "saving": saving,
                    "replacement_hex": b"".join(replacement).hex(" ").upper(),
                }
            )
    report = {
        "status": "PASS",
        "candidate_count": len(results),
        "total_saving": sum(item["saving"] for item in results),
        "candidates": results,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

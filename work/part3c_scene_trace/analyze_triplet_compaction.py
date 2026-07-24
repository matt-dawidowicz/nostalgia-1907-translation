#!/usr/bin/env python3
"""Find narrow three-character merges that retire unique dynamic glyphs."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
MES = HERE / "PART3C_rowparityfix6.MES"
FONT = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh" / "FIX_CODE.FNT"
CONFIG = (
    PROJECT
    / "outputs"
    / "nostalgia1907_act3c_000_223_visualfix4"
    / "PART3C_000_223_visualfix4_build_config.json"
)
REPORT = HERE / "triplet_compaction_report.json"
GLYPH_BYTES = 18

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    dynamic_glyph_index,
    parse_mes,
    render_generated_unit,
    segments_for,
    transform_glyph_bytes,
)


def tokenize(record: bytes) -> list[bytes]:
    """Return glyph/control tokens before the null terminator."""
    result = []
    cursor = 0
    while cursor < len(record) - 1:
        width = 2 if record[cursor] >= 0xF0 else 1
        result.append(record[cursor : cursor + width])
        cursor += width
    if cursor != len(record) - 1 or record[-1:] != b"\0":
        raise ValueError("invalid record")
    return result


def render(style: str, unit: str) -> bytes:
    """Render a unit in MES/FNT storage orientation."""
    return transform_glyph_bytes(render_generated_unit(style, unit), "prerot-cw")


def main() -> None:
    """Report conservative adjacent-unit candidates."""
    data = MES.read_bytes()
    info, pointers = parse_mes(data, MES)
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    tail = data[info.split_offset :]
    font = FONT.read_bytes()

    def token_bitmap(token: bytes) -> bytes | None:
        if len(token) == 1 and 1 <= token[0] <= 0xED:
            start = (token[0] - 1) * GLYPH_BYTES
            return font[start : start + GLYPH_BYTES]
        if len(token) == 2:
            index = dynamic_glyph_index(token[0], token[1])
            if index is not None:
                start = index * GLYPH_BYTES
                return tail[start : start + GLYPH_BYTES]
        return None

    dynamic_use: Counter[int] = Counter()
    for record in records:
        for token in tokenize(record):
            if len(token) == 2:
                index = dynamic_glyph_index(token[0], token[1])
                if index is not None:
                    dynamic_use[index] += 1

    labels: dict[bytes, set[tuple[str, str]]] = defaultdict(set)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    for entry in config["segments"]:
        for unit in entry["units"]:
            style = str(unit["style"])
            text = str(unit["unit"])
            try:
                labels[render(style, text)].add((style, text))
            except ValueError:
                pass

    protected = set(config["scn_fixed_window_padding"]["segments"])
    protected.update(config["profile_forced_final_row_padding"]["segments"])
    existing = {
        font[index : index + GLYPH_BYTES]
        for index in range(0, len(font), GLYPH_BYTES)
    }
    existing.update(
        tail[index : index + GLYPH_BYTES]
        for index in range(0, len(tail), GLYPH_BYTES)
    )
    results = []
    styles = ("packed", "packed-compact", "packed-literal", "full")
    for record_index, record in enumerate(records):
        if record_index in protected:
            continue
        tokens = tokenize(record)
        for position, (left, right) in enumerate(zip(tokens, tokens[1:])):
            left_index = (
                dynamic_glyph_index(left[0], left[1]) if len(left) == 2 else None
            )
            right_index = (
                dynamic_glyph_index(right[0], right[1]) if len(right) == 2 else None
            )
            unique_indexes = [
                index
                for index in (left_index, right_index)
                if index is not None and dynamic_use[index] == 1
            ]
            if len(unique_indexes) != 1:
                continue
            left_labels = labels.get(token_bitmap(left) or b"", set())
            right_labels = labels.get(token_bitmap(right) or b"", set())
            for _, left_text in left_labels:
                for _, right_text in right_labels:
                    combined = left_text + right_text
                    if len(combined) != 3 or not combined.strip():
                        continue
                    for style in styles:
                        try:
                            value = render(style, combined)
                        except ValueError:
                            continue
                        results.append(
                            {
                                "record": record_index,
                                "position": position,
                                "replace_index": unique_indexes[0],
                                "left": left_text,
                                "right": right_text,
                                "combined": combined,
                                "style": style,
                                "bitmap_already_exists": value in existing,
                                "estimated_saving": len(left) + len(right) - 2,
                            }
                        )
    unique = []
    seen = set()
    for item in results:
        key = (item["record"], item["position"], item["combined"], item["style"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    report = {"status": "PASS", "candidate_count": len(unique), "candidates": unique}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "candidate_count": len(unique), "candidates": unique[:40]}, indent=2))


if __name__ == "__main__":
    main()

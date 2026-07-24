#!/usr/bin/env python3
"""Measure safe whole-MES compaction options before changing another image."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
CANDIDATE = HERE / "PART3C_cursorparityfix4.MES"
FONT = WORKSPACE / "outputs" / "PART3C_cursorparityfix4_fresh" / "FIX_CODE.FNT"
REGRESSION = (
    WORKSPACE / "outputs" / "PART3C_cursorparityfix4_fresh" / "regression_full"
)
REPORT = HERE / "compaction_capacity_report.json"

GLYPH_BYTES = 18

sys.path.insert(0, str(TOOLS))

from mes_probe import dynamic_glyph_index, parse_mes, segments_for  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_records(path: Path) -> tuple[bytes, object, list[bytes], bytes]:
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid:
        raise ValueError(f"invalid MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    return data, info, records, data[info.split_offset :]


def fixed_code_usage(path: Path) -> Counter[int]:
    data, _, records, _ = load_records(path)
    usage: Counter[int] = Counter()
    for record in records:
        offset = 0
        while offset < len(record) - 1:
            value = record[offset]
            if value >= 0xF0:
                if offset + 1 >= len(record) - 1:
                    raise ValueError(f"truncated dynamic token in {path}")
                offset += 2
                continue
            if 1 <= value <= 0xED:
                usage[value] += 1
            offset += 1
    return usage


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    data, info, records, tail = load_records(CANDIDATE)

    distinct = list(dict.fromkeys(records))
    exact_alias_savings = sum(map(len, records)) - sum(map(len, distinct))
    retained: list[bytes] = []
    for record in sorted(distinct, key=len, reverse=True):
        if not any(container.endswith(record) for container in retained):
            retained.append(record)
    arbitrary_suffix_savings = sum(map(len, records)) - sum(map(len, retained))

    adjacent_suffix_hits = []
    adjacent_suffix_savings = 0
    for index in range(1, len(records)):
        before = records[index - 1]
        current = records[index]
        if len(current) <= len(before) and before.endswith(current):
            adjacent_suffix_savings += len(current)
            adjacent_suffix_hits.append(
                {"record": index, "container": index - 1, "bytes": len(current)}
            )

    all_mes = sorted(
        path
        for path in REGRESSION.rglob("*.unpacked")
        if path.name.upper().endswith(".MES.UNPACKED")
    )
    global_usage: Counter[int] = Counter()
    usage_by_file: dict[str, Counter[int]] = {}
    for path in all_mes:
        usage = fixed_code_usage(path)
        global_usage.update(usage)
        usage_by_file[str(path.relative_to(REGRESSION))] = usage
    unused_codes = [code for code in range(1, 0xEE) if not global_usage[code]]

    font = FONT.read_bytes()
    bitmap_codes: dict[bytes, list[int]] = defaultdict(list)
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        bitmap_codes[font[start : start + GLYPH_BYTES]].append(code)
    duplicate_groups = [codes for codes in bitmap_codes.values() if len(codes) > 1]
    duplicate_reclaimable = sum(len(codes) - 1 for codes in duplicate_groups)

    candidate_usage = fixed_code_usage(CANDIDATE)
    candidate_only_codes = [
        code
        for code in range(1, 0xEE)
        if candidate_usage[code]
        and global_usage[code] == usage_by_file.get(
            "PART3C\\001_PART3C.MES.unpacked", Counter()
        )[code]
    ]

    report = {
        "status": "PASS",
        "candidate": {
            "size": len(data),
            "size_hex": f"0x{len(data):X}",
            "sha256": digest(data),
            "text_split": info.split_offset,
            "record_bytes": sum(map(len, records)),
            "tail_bytes": len(tail),
            "dynamic_glyphs": len(tail) // GLYPH_BYTES,
        },
        "record_alias_capacity": {
            "record_count": len(records),
            "distinct_record_count": len(distinct),
            "exact_alias_savings_with_arbitrary_pointers": exact_alias_savings,
            "suffix_alias_savings_with_arbitrary_pointers": arbitrary_suffix_savings,
            "adjacent_monotonic_suffix_savings": adjacent_suffix_savings,
            "adjacent_monotonic_suffix_hits": adjacent_suffix_hits,
        },
        "global_fixed_font_capacity": {
            "validated_mes_files": len(all_mes),
            "used_codes": len(global_usage),
            "unused_codes": len(unused_codes),
            "unused_code_hex": [f"0x{code:02X}" for code in unused_codes],
            "duplicate_bitmap_groups": [
                [f"0x{code:02X}" for code in codes] for codes in duplicate_groups
            ],
            "duplicate_slots_reclaimable": duplicate_reclaimable,
            "candidate_used_codes": len(candidate_usage),
            "candidate_only_code_hex": [
                f"0x{code:02X}" for code in candidate_only_codes
            ],
        },
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

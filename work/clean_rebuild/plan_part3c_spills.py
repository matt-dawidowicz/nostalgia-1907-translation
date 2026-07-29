#!/usr/bin/env python3
"""Analyze candidate additions to the shared fixed English-cell dictionary."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import product
from pathlib import Path

from font_render import CHARSET, FontError, stored_cell
from mes_compiler import FIXED_ENGLISH_UNITS
from mes_format import DYNAMIC_PREFIX_START, read_mes
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES


def _fixed_codes(record: bytes) -> set[int]:
    """Return one-byte fixed-font codes referenced by one MES record."""
    codes: set[int] = set()
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value >= DYNAMIC_PREFIX_START:
            offset += 2
        else:
            if 1 <= value <= 0xED:
                codes.add(value)
            offset += 1
    return codes


def _preserved_code_usage(retail_root: Path) -> Counter[int]:
    """Count fixed codes that must retain retail glyphs in preserved records."""
    index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
    usage: Counter[int] = Counter()
    for item in index["chapters"]:
        chapter = item["chapter"]
        canonical = json.loads((SOURCES / item["source"]).read_text(encoding="utf-8"))
        retail = read_mes(
            retail_root / "retail_unpacked" / chapter / f"{chapter}.MES"
        )
        for record in canonical["records"]:
            if record["policy"] != "preserve":
                continue
            for code in _fixed_codes(retail.records[record["index"]]):
                usage[code] += 1
    return usage


def _dynamic_frequency(path: Path) -> tuple[Counter[bytes], dict[bytes, int]]:
    """Count referenced dynamic bitmaps in a compiled diagnostic MES."""
    mes = read_mes(path)
    frequency: Counter[bytes] = Counter()
    for record in mes.records:
        offset = 0
        while offset < len(record):
            value = record[offset]
            if value < DYNAMIC_PREFIX_START:
                offset += 1
                continue
            index = (value - DYNAMIC_PREFIX_START) * 0xFF + record[offset + 1] - 1
            frequency[mes.glyphs[index]] += 1
            offset += 2
    return frequency, {bitmap: index for index, bitmap in enumerate(mes.glyphs)}


def _bitmap_names() -> dict[bytes, tuple[str, str]]:
    """Build deterministic human-readable names for generated cell bitmaps."""
    characters = sorted(set(CHARSET + " "))
    names: dict[bytes, tuple[str, str]] = {}
    for size in (1, 2):
        for values in product(characters, repeat=size):
            unit = "".join(values)
            try:
                names.setdefault(stored_cell("literal", unit), ("literal", unit))
            except FontError:
                pass
    # The compiler's only high-frequency compact cluster is already in the
    # baseline spill map.  Literal one/two-character cells cover additional
    # candidates without an expensive cubic punctuation search.
    return names


def plan(candidate: Path, retail_root: Path) -> dict[str, object]:
    """Return safe codes and high-value dynamic units without editing files."""
    preserved_usage = _preserved_code_usage(retail_root)
    existing_codes = {code for code, _style, _unit in FIXED_ENGLISH_UNITS}
    available_codes = [
        code
        for code in range(1, 0xEE)
        if not preserved_usage[code] and code not in existing_codes
    ]
    frequency, indexes = _dynamic_frequency(candidate)
    names = _bitmap_names()
    candidates = []
    for bitmap, occurrences in frequency.most_common():
        if bitmap not in names:
            continue
        style, unit = names[bitmap]
        candidates.append(
            {
                "style": style,
                "unit": unit,
                "dynamic_index": indexes[bitmap],
                "occurrences": occurrences,
                "estimated_savings": occurrences + 18,
                "bitmap": bitmap.hex().upper(),
            }
        )
    return {
        "status": "PASS",
        "candidate": str(candidate),
        "preserved_fixed_code_count": len(preserved_usage),
        "available_code_count": len(available_codes),
        "available_codes": [f"0x{code:02X}" for code in available_codes],
        "ranked_dynamic_units": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    payload = plan(args.candidate, args.retail_root)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit globally safe fixed-font slots for the final PART3C transition fix."""

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
REGRESSION = WORKSPACE / "outputs" / "PART3C_rowparityfix6_fresh" / "regression_full"
REPORT = HERE / "transitionfix10_fixed_capacity.json"
GLYPH_BYTES = 18

sys.path.insert(0, str(TOOLS))

from mes_probe import parse_mes, segments_for  # noqa: E402


def usage(path: Path) -> Counter[int]:
    """Count fixed tokens while skipping dynamic payload bytes."""
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
    """Report unused codes and equivalent-code remapping capacity."""
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    counts: Counter[int] = Counter()
    audited = []
    for path in sorted(REGRESSION.glob("*/*.MES.unpacked")):
        if path.parent.name == "PART3C":
            continue
        counts.update(usage(path))
        audited.append(str(path.relative_to(REGRESSION)))
    counts.update(usage(MES))

    font = FONT.read_bytes()
    groups: dict[bytes, list[int]] = defaultdict(list)
    for code in range(1, 0xEE):
        start = (code - 1) * GLYPH_BYTES
        groups[font[start : start + GLYPH_BYTES]].append(code)
    duplicates = []
    reclaimable = []
    for codes in groups.values():
        if len(codes) < 2:
            continue
        item = {f"0x{code:02X}": counts[code] for code in codes}
        duplicates.append(item)
        keeper = min(codes, key=lambda code: (-counts[code], code))
        for code in codes:
            if code != keeper:
                reclaimable.append(
                    {
                        "code": f"0x{code:02X}",
                        "uses_to_remap": counts[code],
                        "equivalent_keeper": f"0x{keeper:02X}",
                    }
                )
    unused = [f"0x{code:02X}" for code in range(1, 0xEE) if counts[code] == 0]
    report = {
        "status": "PASS",
        "audited_mes_files": len(audited) + 1,
        "unused_codes": unused,
        "duplicate_groups": duplicates,
        "reclaimable_duplicate_codes": reclaimable,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

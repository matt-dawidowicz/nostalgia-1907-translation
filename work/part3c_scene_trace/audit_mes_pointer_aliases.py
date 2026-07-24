#!/usr/bin/env python3
"""Audit retail and translated MES files for pointer aliases and ordering."""

from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
RETAIL_ROOT = PROJECT / "work" / "nostalgia1907" / "unpacked"
CURRENT_ROOT = WORKSPACE / "outputs" / "PART3C_cursorparityfix4_fresh" / "regression_full"
REPORT = HERE / "mes_pointer_alias_audit.json"

sys.path.insert(0, str(TOOLS))

from mes_probe import parse_mes  # noqa: E402


def inspect(path: Path) -> dict[str, object]:
    """Return pointer ordering and alias facts for one MES."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    duplicates: dict[int, list[int]] = {}
    for index, pointer in enumerate(pointers):
        duplicates.setdefault(pointer, []).append(index)
    aliases = {key: value for key, value in duplicates.items() if len(value) > 1}
    descents = [
        index for index in range(1, len(pointers)) if pointers[index] < pointers[index - 1]
    ]
    return {
        "path": str(path),
        "valid": info.valid,
        "pointer_count": info.pointer_count,
        "alias_groups": aliases,
        "alias_group_count": len(aliases),
        "descents": descents,
    }


def main() -> None:
    """Write a concise cross-game alias audit."""
    retail = sorted(RETAIL_ROOT.glob("*/*.MES.unpacked"))
    current = sorted(CURRENT_ROOT.glob("*/*.MES.unpacked"))
    rows = [inspect(path) for path in retail + current]
    report = {
        "retail_count": len(retail),
        "current_count": len(current),
        "files_with_aliases": [row for row in rows if row["alias_group_count"]],
        "files_with_descents": [row for row in rows if row["descents"]],
        "all": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "retail_count": len(retail),
                "current_count": len(current),
                "files_with_aliases": len(report["files_with_aliases"]),
                "files_with_descents": len(report["files_with_descents"]),
                "alias_examples": report["files_with_aliases"][:5],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

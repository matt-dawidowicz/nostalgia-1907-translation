#!/usr/bin/env python3
"""Export historical glyph patterns for forensic provenance only.

This retired investigation utility is not imported by the clean rebuild and
has no default path to a contributor's machine. It runs only when the caller
explicitly supplies the historical ``mes_probe.py`` file that produced the
already-tracked immutable font-pattern data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "work" / "clean_rebuild" / "font_patterns.json"


def export_patterns(source: Path, output: Path) -> dict[str, object]:
    """Export immutable glyph patterns and the exact historical source hash."""
    if not source.is_file():
        raise FileNotFoundError(f"historical renderer source is unavailable: {source}")
    spec = importlib.util.spec_from_file_location("font_pattern_source", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    payload = {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest().upper(),
        "english_charset": module.ENGLISH_CHARSET,
        "patterns": module.BITMAP_GLYPHS,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "FORENSIC_ONLY",
        "output": str(output),
        "glyphs": len(module.BITMAP_GLYPHS),
    }


def main() -> None:
    """Parse explicit forensic inputs and write one machine-readable export."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="explicit path to the retired historical mes_probe.py",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export_patterns(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()

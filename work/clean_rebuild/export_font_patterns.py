#!/usr/bin/env python3
"""Freeze the validated historical 5x7 English art as data, not code."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = Path(
    r"C:\Users\thema\Documents\Codex\2026-07-12\i\outputs"
    r"\nostalgia1907_tools\mes_probe.py"
)
OUTPUT = HERE / "font_patterns.json"


def main() -> None:
    """Export only immutable glyph patterns and their source hash."""
    spec = importlib.util.spec_from_file_location("font_pattern_source", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    payload = {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper(),
        "english_charset": module.ENGLISH_CHARSET,
        "patterns": module.BITMAP_GLYPHS,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(OUTPUT), "glyphs": len(module.BITMAP_GLYPHS)}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compile the complete canonical script and assemble its generated font.

This orchestration layer iterates ``sources/index.json`` in canonical chapter
order, calls ``mes_compiler.compile_files`` with each hash-locked retail MES and
SCN, writes derived MES files, and collects capacity metrics. It also applies
the compiler's declared fixed-font spill bitmaps to a copy of the retail fixed
font while rejecting conflicting or out-of-range codes.

The emitted ``mes_report.json`` is generated evidence for regression and
capacity review; it is never a source input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from source_json import load_json_object

from mes_compiler import compile_files


HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def report_path(build_root: Path, path: Path) -> str:
    """Return a deterministic POSIX path relative to the current build root.

    Generated reports are compared across independent clean-build directories.
    Absolute temporary paths would make otherwise identical builds appear
    different, so every managed artifact path is serialized relative to the
    run-local build root.
    """
    try:
        relative = path.relative_to(build_root)
    except ValueError as error:
        raise ValueError(
            f"report artifact escapes build root: {path} is not below {build_root}"
        ) from error
    return relative.as_posix()


def build_mes_set(build_root: Path) -> dict[str, object]:
    """Compile all chapters and assemble the generated fixed-font image.

    Args:
        build_root: Prepared build tree containing guarded retail members.

    Returns:
        Capacity and hash evidence for every MES plus the merged font patches.

    Raises:
        ValueError: If compilation fails, font patches conflict, or a patched
            code lies outside the retail fixed-font bank.

    Side Effects:
        Writes generated MES files, ``FIX_CODE.FNT``, and ``mes_report.json``
        below ``build_root``. Canonical and retail inputs remain unchanged.
    """
    original = build_root / "retail_unpacked"
    output = build_root / "mes"
    retail_font = build_root / "retail_files" / "FIX_CODE.FNT"
    output_font = build_root / "FIX_CODE.FNT"
    report = build_root / "mes_report.json"
    index = load_json_object(SOURCES / "index.json")
    output.mkdir(parents=True, exist_ok=True)
    chapters: list[dict[str, object]] = []
    font_patches: dict[int, bytes] = {}
    for item in index["chapters"]:
        chapter = item["chapter"]
        retail_dir = original / chapter
        output_path = output / f"{chapter}.MES"
        result = compile_files(
            retail_dir / f"{chapter}.MES",
            retail_dir / f"{chapter}.SCN",
            SOURCES / item["source"],
            output_path,
            glyph_order="first-use",
        )
        details = asdict(result)
        details.pop("data")
        raw_patches = details.pop("fixed_font_patches")
        for code, glyph_hex in raw_patches:
            glyph = bytes.fromhex(glyph_hex)
            previous = font_patches.get(code)
            if previous is not None and previous != glyph:
                raise ValueError(f"conflicting fixed-font patch for code 0x{code:02X}")
            font_patches[code] = glyph
        details.update(
            {
                "chapter": chapter,
                "path": report_path(build_root, output_path),
                "size": output_path.stat().st_size,
                "sha256": sha256(output_path),
            }
        )
        chapters.append(details)
    font = bytearray(retail_font.read_bytes())
    if len(font) % 18:
        raise ValueError("retail fixed font has a partial glyph")
    for code, glyph in sorted(font_patches.items()):
        offset = (code - 1) * 18
        if not 0 <= offset <= len(font) - 18:
            raise ValueError(f"fixed-font code 0x{code:02X} is outside the font")
        font[offset : offset + 18] = glyph
    output_font.parent.mkdir(parents=True, exist_ok=True)
    output_font.write_bytes(font)
    payload = {
        "status": "PASS",
        "chapter_count": len(chapters),
        "total_records": sum(int(item["record_count"]) for item in chapters),
        "max_dynamic_glyphs": max(int(item["dynamic_glyphs"]) for item in chapters),
        "fixed_font": {
            "path": report_path(build_root, output_font),
            "size": output_font.stat().st_size,
            "sha256": sha256(output_font),
            "patched_codes": [f"0x{code:02X}" for code in sorted(font_patches)],
        },
        "chapters": chapters,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, default=HERE / "build")
    args = parser.parse_args()
    payload = build_mes_set(args.build_root)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "chapter_count": payload["chapter_count"],
                "total_records": payload["total_records"],
                "max_dynamic_glyphs": payload["max_dynamic_glyphs"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

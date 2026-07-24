#!/usr/bin/env python3
"""Determine which fixed font matches the visualfix4 MES manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
V3 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix3"
V4 = PROJECT / "outputs" / "nostalgia1907_act3c_000_223_visualfix4"
REPORT = HERE / "visualfix4_font_verification.json"

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    GLYPH_BYTES,
    parse_mes,
    render_generated_unit,
    transform_glyph_bytes,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> None:
    if REPORT.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT}")
    config = json.loads(
        (V4 / "PART3C_000_223_visualfix4_build_config.json").read_text(
            encoding="utf-8"
        )
    )
    mes = (V4 / "PART3C.MES").read_bytes()
    info, _ = parse_mes(mes, V4 / "PART3C.MES")
    tail = mes[info.split_offset :]
    transform = str(config["glyph_transform"])
    fonts = {
        "visualfix4_standalone": (V4 / "FIX_CODE.FNT").read_bytes(),
        "visualfix4_iso_embedded": (
            V4 / "iso_extract_verify" / "FIX_CODE.FNT"
        ).read_bytes(),
        "visualfix3": (V3 / "FIX_CODE.FNT").read_bytes(),
    }
    results = {}
    for name, font in fonts.items():
        mismatches = []
        checked = 0
        for entry in config["segments"]:
            segment = int(entry["segment"])
            for position, unit in enumerate(entry["units"]):
                expected = transform_glyph_bytes(
                    render_generated_unit(str(unit["style"]), str(unit["unit"])),
                    transform,
                )
                if unit["encoding"] == "fixed":
                    code = int(str(unit["code"]), 0)
                    start = (code - 1) * GLYPH_BYTES
                    actual = font[start : start + GLYPH_BYTES]
                    token = f"fixed:{code:02X}"
                elif unit["encoding"] == "dynamic":
                    index = int(unit["dynamic_index"])
                    start = index * GLYPH_BYTES
                    actual = tail[start : start + GLYPH_BYTES]
                    token = f"dynamic:{index}"
                else:
                    raise ValueError(f"unknown encoding: {unit!r}")
                checked += 1
                if actual != expected and len(mismatches) < 50:
                    mismatches.append(
                        {
                            "segment": segment,
                            "position": position,
                            "token": token,
                            "style": unit["style"],
                            "unit": unit["unit"],
                            "expected_sha256": digest(expected),
                            "actual_sha256": digest(actual),
                        }
                    )
        results[name] = {
            "font_sha256": digest(font),
            "checked_unit_occurrences": checked,
            "mismatch_count_capped": len(mismatches),
            "first_mismatches": mismatches,
            "all_checked_units_match": not mismatches,
        }
    matching = [name for name, result in results.items() if result["all_checked_units_match"]]
    if matching != ["visualfix4_standalone"]:
        raise ValueError(f"unexpected matching fonts: {matching}")
    report = {
        "status": "PASS",
        "matching_font": matching[0],
        "results": results,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

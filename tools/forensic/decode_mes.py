#!/usr/bin/env python3
"""Decode historical compiled MES glyph cells for forensic provenance only.

This retired investigation utility is not imported by the clean rebuild. It
requires explicit paths to a historical renderer and historical extracted
artifacts, preventing contributor-machine locations from becoming hidden build
dependencies. Its output is never a source input.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
CLEAN_REBUILD = ROOT / "work" / "clean_rebuild"
if str(CLEAN_REBUILD) not in sys.path:
    sys.path.insert(0, str(CLEAN_REBUILD))

from mes_format import DYNAMIC_PREFIX_START, read_mes  # noqa: E402


DEFAULT_OUTPUT = CLEAN_REBUILD / "forensic_decode.json"


def load_historical_renderer(renderer_path: Path) -> ModuleType:
    """Load an explicitly supplied renderer without changing ``sys.path``."""
    path = renderer_path
    if not path.is_file():
        raise FileNotFoundError(f"historical renderer is unavailable: {path}")
    spec = importlib.util.spec_from_file_location("historical_mes_probe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def candidate_units(renderer: ModuleType) -> dict[bytes, list[tuple[str, str]]]:
    """Return every plausible English unit keyed by its stored bitmap."""
    candidates: dict[bytes, list[tuple[str, str]]] = defaultdict(list)
    charset = str(renderer.ENGLISH_CHARSET)
    visible = charset.replace(" ", "")

    units: set[tuple[str, str]] = set()
    units.update(("full", char) for char in charset)
    units.update(("packed-literal", char) for char in charset)
    units.update(
        ("packed-literal", "".join(chars))
        for chars in itertools.product(charset, repeat=2)
    )

    for style in ("packed", "packed-compact"):
        units.update((style, char) for char in visible)
        units.update(
            (style, "".join(chars)) for chars in itertools.product(visible, repeat=2)
        )
        units.update(
            (style, f" {left}{right}")
            for left, right in itertools.product(visible, repeat=2)
        )
        units.update(
            (style, f"{left} {right}")
            for left, right in itertools.product(visible, repeat=2)
        )
        units.update(
            (style, "".join(chars))
            for chars in itertools.product(visible, repeat=3)
            if "." in chars or "'" in chars
        )

    for style, unit in sorted(units):
        try:
            bitmap = renderer.render_generated_unit(style, unit)
            stored = renderer.transform_glyph_bytes(bitmap, "prerot-cw")
        except ValueError:
            continue
        entry = (style, unit)
        if entry not in candidates[stored]:
            candidates[stored].append(entry)
    return dict(candidates)


def choose_unit(options: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Choose only candidates whose text is unambiguous across render styles."""
    if not options:
        return None
    texts = {unit for _, unit in options}
    if len(texts) != 1:
        return None
    preferred = {"packed-literal": 0, "packed": 1, "packed-compact": 2, "full": 3}
    return min(options, key=lambda item: preferred[item[0]])


def decode_chapter(
    chapter: str,
    candidates: dict[bytes, list[tuple[str, str]]],
    historical_root: Path,
) -> dict[str, object]:
    """Decode one historical chapter and retain ambiguous alternatives."""
    mes_path = (
        historical_root / "unpacked" / chapter / f"001_{chapter}.MES.unpacked"
    )
    font_path = historical_root / "iso_files" / "FIX_CODE.FNT"
    mes = read_mes(mes_path)
    font_data = font_path.read_bytes()
    fixed_glyphs = tuple(
        font_data[offset : offset + 18] for offset in range(0, len(font_data), 18)
    )

    dynamic_options = [candidates.get(glyph, []) for glyph in mes.glyphs]
    fixed_options = [candidates.get(glyph, []) for glyph in fixed_glyphs]
    decoded_records: list[dict[str, object]] = []

    used_dynamic: set[int] = set()
    used_fixed: set[int] = set()
    for record_index, record in enumerate(mes.records):
        offset = 0
        pieces: list[str] = []
        tokens: list[dict[str, object]] = []
        ambiguous = 0
        unknown = 0
        while offset < len(record):
            value = record[offset]
            if value == 0:
                tokens.append({"kind": "end", "hex": "00"})
                offset += 1
                continue
            if value >= DYNAMIC_PREFIX_START:
                low = record[offset + 1]
                index = (value - DYNAMIC_PREFIX_START) * 0xFF + low - 1
                used_dynamic.add(index)
                options = dynamic_options[index]
                selected = choose_unit(options)
                if selected is None:
                    pieces.append(f"{{DYN:{index}}}")
                    ambiguous += bool(options)
                    unknown += not options
                else:
                    pieces.append(selected[1])
                tokens.append(
                    {
                        "kind": "dynamic",
                        "index": index,
                        "selected": list(selected) if selected else None,
                        "options": [list(item) for item in options],
                    }
                )
                offset += 2
                continue
            if 0x01 <= value <= 0xED:
                index = value - 1
                used_fixed.add(index)
                options = fixed_options[index]
                selected = choose_unit(options)
                if selected is None:
                    pieces.append(f"{{FIX:{value:02X}}}")
                    ambiguous += bool(options)
                    unknown += not options
                else:
                    pieces.append(selected[1])
                tokens.append(
                    {
                        "kind": "fixed",
                        "code": value,
                        "selected": list(selected) if selected else None,
                        "options": [list(item) for item in options],
                    }
                )
                offset += 1
                continue
            tokens.append({"kind": "control", "hex": f"{value:02X}"})
            pieces.append(f"{{CTRL:{value:02X}}}")
            offset += 1

        decoded_records.append(
            {
                "record": record_index,
                "decoded_cells": "".join(pieces),
                "ambiguous_cells": ambiguous,
                "unknown_cells": unknown,
                "tokens": tokens,
            }
        )

    return {
        "chapter": chapter,
        "mes": str(mes_path),
        "record_count": mes.record_count,
        "dynamic_glyph_count": len(mes.glyphs),
        "used_dynamic_glyph_count": len(used_dynamic),
        "used_dynamic_without_candidate": sorted(
            index for index in used_dynamic if not dynamic_options[index]
        ),
        "used_dynamic_with_ambiguous_text": sorted(
            index
            for index in used_dynamic
            if dynamic_options[index]
            and len({unit for _, unit in dynamic_options[index]}) > 1
        ),
        "used_fixed_codes": sorted(index + 1 for index in used_fixed),
        "used_fixed_without_candidate": sorted(
            index + 1 for index in used_fixed if not fixed_options[index]
        ),
        "used_fixed_with_ambiguous_text": sorted(
            index + 1
            for index in used_fixed
            if fixed_options[index]
            and len({unit for _, unit in fixed_options[index]}) > 1
        ),
        "records": decoded_records,
    }


def main() -> None:
    """Decode selected chapters from explicitly supplied historical inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chapters", nargs="+", help="chapter names such as PART2F")
    parser.add_argument(
        "--renderer",
        type=Path,
        required=True,
        help="explicit path to the retired historical mes_probe.py",
    )
    parser.add_argument(
        "--historical-root",
        type=Path,
        required=True,
        help="explicit root containing unpacked/ and iso_files/ forensic data",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    renderer = load_historical_renderer(args.renderer)
    candidates = candidate_units(renderer)
    payload = {
        "status": "FORENSIC_ONLY",
        "candidate_bitmap_count": len(candidates),
        "chapters": [
            decode_chapter(name, candidates, args.historical_root)
            for name in args.chapters
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "candidate_bitmap_count": len(candidates),
                "chapters": [
                    {
                        "chapter": item["chapter"],
                        "record_count": item["record_count"],
                        "dynamic_missing": len(item["used_dynamic_without_candidate"]),
                        "dynamic_ambiguous": len(
                            item["used_dynamic_with_ambiguous_text"]
                        ),
                        "fixed_missing": len(item["used_fixed_without_candidate"]),
                        "fixed_ambiguous": len(item["used_fixed_with_ambiguous_text"]),
                    }
                    for item in payload["chapters"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

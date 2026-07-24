#!/usr/bin/env python3
"""Build and validate first-pass English MES files for all Act 4 scripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
SOURCE_ROOT = PROJECT / "work" / "nostalgia1907" / "unpacked"
FIXED_FONT = WORKSPACE / "outputs" / "PART3C_transitionfix10_full_fresh" / "FIX_CODE.FNT"
OUTPUT_ROOT = HERE / "built"
REPORT_PATH = HERE / "act4_mes_build_report.json"

sys.path.insert(0, str(TOOLS))

from mes_probe import (  # noqa: E402
    build_dynamic_text_mes_selective,
    parse_mes,
    read_segment_texts_json,
    segments_for,
)
from profiled_text_builder import (  # noqa: E402
    audit_runtime_row_boundaries,
    find_choice_segments,
    infer_scn_floating_row_limits,
    infer_scn_runtime_layouts,
    validate_scn_floating_row_limits,
    validate_translation_text_hygiene,
    validate_wrapped_text_integrity,
)


CHAPTERS = {
    "PART4A": 63,
    "PART4B": 293,
    "PART4C": 60,
}
VISIBLE_DIALOGUE = (12, 10)
VISIBLE_CONTINUATION = (10, 10)
RUNTIME_DIALOGUE = (12, 11)
RUNTIME_CONTINUATION = (11, 11)
WINDOW_SUBTYPES = frozenset((0x27, 0x28))
CHOICE_LIMIT = 18
LOCAL_WINDOW_LAYOUT_OVERRIDES = {
    # Retail PART4C uses the otherwise-unlisted 0x11 width at SCN 0x2C2.
    # The neighboring 0x10/0x12 widths map to 9/10 cells, respectively.
    "PART4C": {48: (9, 9)},
}
GLYPH_ORDER = {
    "PART4A": "first-use",
    "PART4B": "first-use",
    "PART4C": "first-use",
}


def digest(data: bytes) -> str:
    """Return uppercase SHA-256."""
    return hashlib.sha256(data).hexdigest().upper()


def load_records(path: Path) -> tuple[bytes, object, list[int], list[bytes]]:
    """Load one MES and require strict record boundaries and terminators."""
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    if not info.valid or any(left >= right for left, right in zip(pointers, pointers[1:])):
        raise ValueError(f"invalid or non-monotonic MES: {path}")
    spans = segments_for(data, pointers, info.split_offset)
    records = [data[item.offset : item.offset + item.size] for item in spans]
    for index, record in enumerate(records):
        if not record or record[-1] != 0 or record.count(0) != 1:
            raise ValueError(f"record {index} in {path.name} lacks one final terminator")
    return data, info, pointers, records


def build_one(chapter: str, expected_count: int) -> dict[str, object]:
    """Build one complete chapter with inferred SCN layouts and hard QA."""
    source_dir = SOURCE_ROOT / chapter
    source_mes = source_dir / f"001_{chapter}.MES.unpacked"
    source_scn = source_dir / f"000_{chapter}.SCN.unpacked"
    texts_path = HERE / f"{chapter}_texts.json"
    out_dir = OUTPUT_ROOT / chapter
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mes = out_dir / f"{chapter}.MES"
    manifest_path = out_dir / f"{chapter}_manifest.json"
    if out_mes.exists() or manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite built {chapter} artifacts")

    replacements = read_segment_texts_json(texts_path)
    if set(replacements) != set(range(expected_count)):
        missing = sorted(set(range(expected_count)) - set(replacements))
        extra = sorted(set(replacements) - set(range(expected_count)))
        raise ValueError(f"{chapter} translation coverage mismatch: missing={missing}, extra={extra}")
    hygiene = validate_translation_text_hygiene(replacements)
    source_data, source_info, _, source_records = load_records(source_mes)
    if len(source_records) != expected_count:
        raise ValueError(f"{chapter} source record count changed")

    choices = find_choice_segments(source_scn, expected_count, require=(chapter != "PART4A"))
    local_overrides = LOCAL_WINDOW_LAYOUT_OVERRIDES.get(chapter, {})
    if chapter == "PART4C":
        scn_data = source_scn.read_bytes()
        if scn_data[0x2C2 : 0x2CA] != bytes.fromhex("24 02 11 11 0C 27 00 31"):
            raise ValueError("PART4C retail 0x11 window command drifted at SCN 0x2C2")
    eligible = set(range(expected_count)) - choices - set(local_overrides)
    visible_layouts = infer_scn_runtime_layouts(
        source_scn,
        expected_count,
        eligible,
        dialogue_layout=VISIBLE_DIALOGUE,
        continuation_layout=VISIBLE_CONTINUATION,
        window_text_subtypes=WINDOW_SUBTYPES,
    )
    runtime_layouts = infer_scn_runtime_layouts(
        source_scn,
        expected_count,
        eligible,
        dialogue_layout=RUNTIME_DIALOGUE,
        continuation_layout=RUNTIME_CONTINUATION,
        window_text_subtypes=WINDOW_SUBTYPES,
    )
    visible_layouts.update(local_overrides)
    runtime_layouts.update(local_overrides)
    if set(visible_layouts) != set(runtime_layouts):
        raise ValueError(f"{chapter} visible/runtime SCN classification differs")
    wrap_segments = set(visible_layouts)
    floating_limits = infer_scn_floating_row_limits(
        source_scn,
        expected_count,
        eligible,
        window_text_subtypes=WINDOW_SUBTYPES,
    )

    manifest = build_dynamic_text_mes_selective(
        source_mes,
        out_mes,
        replacements,
        glyph_transform="prerot-cw",
        wrap_segments=wrap_segments,
        wrap_layouts=visible_layouts,
        runtime_row_layouts=runtime_layouts,
        pad_final_rows=True,
        max_render_cells={index: CHOICE_LIMIT for index in choices},
        pack_pairs=True,
        pack_segments=set(replacements),
        literal_space_pack_segments=set(replacements),
        optimize_literal_pair_phase=True,
        compact_literal_punctuation=True,
        blank_original_leading_quotes=True,
        generated_glyph_order=GLYPH_ORDER[chapter],
        prune_unused_original_glyphs=True,
    )
    manifest["chapter"] = chapter
    manifest["translation_status"] = "first-pass-complete"
    manifest["translation_coverage"] = {
        "expected_records": expected_count,
        "translated_records": len(replacements),
        "complete": len(replacements) == expected_count,
    }
    manifest["choice_segments"] = sorted(choices)
    manifest["choice_render_cell_limit"] = CHOICE_LIMIT
    manifest["scn_sha256"] = digest(source_scn.read_bytes())
    manifest["text_hygiene"] = hygiene
    manifest["scn_layouts"] = {
        "wrapped_segments": sorted(wrap_segments),
        "visible": {str(k): {"first": v[0], "continuation": v[1]} for k, v in sorted(visible_layouts.items())},
        "runtime": {str(k): {"first": v[0], "continuation": v[1]} for k, v in sorted(runtime_layouts.items())},
    }

    validate_wrapped_text_integrity(replacements, manifest, wrap_segments)
    runtime_audit = audit_runtime_row_boundaries(
        replacements,
        manifest,
        visible_layouts,
        runtime_layouts,
        wrap_segments,
    )
    validate_scn_floating_row_limits(manifest, floating_limits)
    output_data, output_info, output_pointers, output_records = load_records(out_mes)
    if len(output_records) != expected_count:
        raise ValueError(f"{chapter} output record count changed")
    if len(output_pointers) != expected_count:
        raise ValueError(f"{chapter} output pointer count changed")
    if source_scn.read_bytes() != (source_dir / f"000_{chapter}.SCN.unpacked").read_bytes():
        raise ValueError(f"{chapter} SCN changed during MES-only build")
    if len(output_data[output_info.split_offset :]) % 18:
        raise ValueError(f"{chapter} dynamic glyph tail is misaligned")

    manifest["runtime_row_boundary_audit"] = runtime_audit
    manifest["floating_row_limits"] = {str(k): v for k, v in sorted(floating_limits.items())}
    manifest["structure_guard"] = {
        "pointer_count": len(output_pointers),
        "strictly_increasing_pointers": True,
        "records_with_one_final_terminator": len(output_records),
        "dynamic_tail_18_byte_aligned": True,
        "source_scn_byte_identical": True,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "chapter": chapter,
        "status": "PASS",
        "source_mes_size": len(source_data),
        "output_mes_size": len(output_data),
        "source_split": source_info.split_offset,
        "output_split": output_info.split_offset,
        "record_count": expected_count,
        "translated_records": len(replacements),
        "choice_segments": sorted(choices),
        "wrapped_segments": len(wrap_segments),
        "floating_windows": len(floating_limits),
        "dynamic_glyph_count": len(output_data[output_info.split_offset :]) // 18,
        "mes_sha256": digest(output_data),
        "scn_sha256": digest(source_scn.read_bytes()),
    }


def main() -> None:
    """Build all three Act 4 MES resources and emit one aggregate report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapter", choices=sorted(CHAPTERS))
    args = parser.parse_args()
    if args.chapter:
        report = build_one(args.chapter, CHAPTERS[args.chapter])
        print(json.dumps(report, indent=2))
        return
    if REPORT_PATH.exists():
        raise FileExistsError(f"refusing to overwrite {REPORT_PATH}")
    reports = [build_one(chapter, count) for chapter, count in CHAPTERS.items()]
    report = {
        "status": "PASS",
        "translation_status": "Act 4 first pass complete",
        "chapters": reports,
        "total_records": sum(item["record_count"] for item in reports),
        "translated_records": sum(item["translated_records"] for item in reports),
        "fixed_font_sha256": digest(FIXED_FONT.read_bytes()),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

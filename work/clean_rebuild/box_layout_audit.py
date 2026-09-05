#!/usr/bin/env python3
"""Audit every translated record against its exact text-box contract.

This is a layout certification tool, not a translation-quality checker.  It
reports every translated record, every SCN occurrence that can be identified,
its renderer/box class, row-by-row cell use, native opening gutter, and any
unexplained indentation.  Records whose runtime geometry is not proven are
reported as certification blockers instead of being silently treated as safe.

The existing compiler remains authoritative for emitted MES bytes.  This tool
adds a human-reviewable occurrence-level inventory so record-level contract
merging cannot hide that the same text is reached through multiple boxes.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .renderer_format import measure_literal
from .scn_layout import _selector_window_commands, _window_text_commands
from .source_json import load_json_object
from .translation_audit import DEFAULT_RETAIL_ROOT, SOURCES
from .translation_formatter import audit_layouts


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
DEFAULT_REPORT = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Translation_Audit"
    / "box_layout_audit.json"
)
DEFAULT_TSV = DEFAULT_REPORT.with_suffix(".tsv")


def _leading_spaces(text: str) -> int:
    """Return literal leading ASCII spaces in one rendered row."""
    return len(text) - len(text.lstrip(" "))


def _trailing_spaces(text: str) -> int:
    """Return literal trailing ASCII spaces in one rendered row."""
    return len(text) - len(text.rstrip(" "))


def _row_details(item: dict[str, object]) -> list[dict[str, object]]:
    """Describe every preview/exact row using the record's proven geometry."""
    rows = item.get("preview_rows")
    if not isinstance(rows, list) or not all(isinstance(row, str) for row in rows):
        raise ValueError(f"{item.get('id')}: preview_rows is malformed")
    layout = item.get("layout")
    output: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        used_cells = measure_literal(row)
        permitted_cells: int | None = None
        native_prefix_cells = 0
        row_kind = "fixed/unproven"
        if isinstance(layout, dict):
            visible = layout.get("visible_cells")
            if not isinstance(visible, dict):
                raise ValueError(f"{item.get('id')}: visible cell geometry is malformed")
            page_rows = layout.get("page_rows")
            repeat = bool(layout.get("repeat_first_row_on_page"))
            first = row_index == 0 or (
                repeat
                and isinstance(page_rows, int)
                and page_rows > 0
                and row_index > 0
                and row_index % page_rows == 0
            )
            key = "first" if first else "continuation"
            raw_permitted = visible.get(key)
            if not isinstance(raw_permitted, int):
                raise ValueError(f"{item.get('id')}: {key} width is malformed")
            native_prefix_cells = (
                int(layout.get("opening_anchor_cells", 0)) if row_index == 0 else 0
            )
            permitted_cells = raw_permitted - native_prefix_cells
            row_kind = key
        output.append(
            {
                "row": row_index + 1,
                "row_kind": row_kind,
                "text": row,
                "characters": len(row),
                "used_cells": used_cells,
                "permitted_cells": permitted_cells,
                "remaining_cells": (
                    permitted_cells - used_cells
                    if permitted_cells is not None
                    else None
                ),
                "native_prefix_cells": native_prefix_cells,
                "leading_spaces": _leading_spaces(row),
                "trailing_spaces": _trailing_spaces(row),
            }
        )
    return output


def _occurrences(
    scn: bytes,
    record_count: int,
    profile: dict[str, object] | None,
) -> dict[int, list[dict[str, object]]]:
    """Return every statically identifiable SCN display occurrence by record."""
    result: dict[int, list[dict[str, object]]] = defaultdict(list)

    def add(index: int, **fields: object) -> None:
        if 0 <= index < record_count:
            result[index].append(fields)

    for offset in range(len(scn)):
        opcode = scn[offset]
        if opcode == 0x21 and offset + 5 <= len(scn):
            first_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            second_id = int.from_bytes(scn[offset + 3 : offset + 5], "big")
            if 1 <= second_id <= record_count:
                if 1 <= first_id <= record_count:
                    add(
                        first_id - 1,
                        offset=f"0x{offset:X}",
                        command="0x21",
                        part="speaker_name",
                        box="scene_label/speaker",
                    )
                add(
                    second_id - 1,
                    offset=f"0x{offset:X}",
                    command="0x21",
                    part="dialogue_body",
                    box="lower_dialogue",
                )
            elif second_id == 0 and 1 <= first_id <= record_count:
                add(
                    first_id - 1,
                    offset=f"0x{offset:X}",
                    command="0x21",
                    part="dialogue_continuation",
                    box="lower_continuation",
                )
        elif opcode == 0x22 and offset + 6 <= len(scn) and scn[offset + 3] == 0x23:
            location_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            perspective_id = int.from_bytes(scn[offset + 4 : offset + 6], "big")
            if 1 <= location_id <= record_count:
                add(
                    location_id - 1,
                    offset=f"0x{offset:X}",
                    command="0x22/0x23",
                    part="location_name",
                    box="scene_label/location",
                )
            if 1 <= perspective_id <= record_count:
                add(
                    perspective_id - 1,
                    offset=f"0x{offset + 3:X}",
                    command="0x22/0x23",
                    part="perspective_name",
                    box="scene_label/perspective",
                )
        elif opcode == 0x31 and offset + 6 <= len(scn) and scn[offset + 3] == 0xFF:
            text_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            jump = int.from_bytes(scn[offset + 4 : offset + 6], "big")
            if 1 <= text_id <= record_count and 0 < jump < len(scn):
                add(
                    text_id - 1,
                    offset=f"0x{offset:X}",
                    command="0x31",
                    part="menu_choice",
                    box="choice",
                    branch_target=f"0x{jump:X}",
                )

    settings = profile or {}
    raw_subtypes = settings.get("scn_window_text_subtypes", [0x27])
    subtypes = set(raw_subtypes) if isinstance(raw_subtypes, list) else {0x27}
    for offset, subtype, width_byte, raw_y, indexes in _window_text_commands(
        scn, record_count, subtypes
    ):
        for chain_index, index in enumerate(indexes):
            add(
                index,
                offset=f"0x{offset if chain_index == 0 else offset + 8 + 3 * (chain_index - 1):X}",
                command="0x24" if chain_index == 0 else "0x27",
                part="floating_window" if chain_index == 0 else "floating_continuation",
                box="floating_window",
                subtype=f"0x{subtype:02X}",
                width_operand=f"0x{width_byte:02X}",
                y_operand=raw_y,
                chain_position=chain_index,
            )
    for offset, subtype, width_byte, raw_y, indexes in _selector_window_commands(
        scn, record_count
    ):
        for index in indexes:
            add(
                index,
                offset=f"0x{offset:X}",
                command="0x24 selector target",
                part="menu_choice_window",
                box="floating_window",
                subtype=f"0x{subtype:02X}",
                width_operand=f"0x{width_byte:02X}",
                y_operand=raw_y,
            )
    return result


def audit(retail_root: Path = DEFAULT_RETAIL_ROOT) -> dict[str, object]:
    """Run strict whole-game box certification and return a JSON report."""
    base = audit_layouts(retail_root)
    base_by_id = {str(item["id"]): item for item in base["records"]}
    index = load_json_object(SOURCES / "index.json")
    records: list[dict[str, object]] = []
    blockers: list[str] = []
    defects: list[str] = []
    box_counts: Counter[str] = Counter()
    occurrence_count = 0

    for chapter_item in index["chapters"]:
        chapter = str(chapter_item["chapter"])
        source = load_json_object(SOURCES / str(chapter_item["source"]))
        retail = retail_root / "retail_unpacked" / chapter
        scn_path = retail / f"{chapter}.SCN"
        if not scn_path.is_file():
            raise FileNotFoundError(f"missing hash-locked retail SCN: {scn_path}")
        occurrences = _occurrences(
            scn_path.read_bytes(),
            int(source["record_count"]),
            source.get("profile") if isinstance(source.get("profile"), dict) else None,
        )
        for source_record in source["records"]:
            if source_record.get("policy") != "translate":
                continue
            record_id = f"{chapter}:{int(source_record['index']):03d}"
            item = base_by_id.get(record_id)
            if item is None:
                raise ValueError(f"{record_id}: missing from base layout audit")
            row_details = _row_details(item)
            raw_occurrences = occurrences.get(int(source_record["index"]), [])
            occurrence_count += len(raw_occurrences)
            layout = item.get("layout")
            box = (
                str(layout["text_box"])
                if isinstance(layout, dict)
                else "fixed_unproven"
            )
            box_counts[box] += 1
            record_defects = list(item.get("failures", []))
            record_blockers: list[str] = []

            for row in row_details:
                permitted = row["permitted_cells"]
                if isinstance(permitted, int) and int(row["used_cells"]) > permitted:
                    record_defects.append(
                        f"row {row['row']} exceeds box width: "
                        f"{row['used_cells']} > {permitted} cells"
                    )
                if item.get("adaptive") and int(row["leading_spaces"]) > 0:
                    record_defects.append(
                        f"row {row['row']} contains unexplained leading indentation"
                    )

            if item.get("layout_policy") == "fixed" and not isinstance(layout, dict):
                record_blockers.append(
                    "fixed translated record has no proven width/rows/origin/alignment contract"
                )
                if any(int(row["leading_spaces"]) > 0 for row in row_details):
                    record_blockers.append(
                        "fixed record contains leading spaces whose indentation cannot be certified"
                    )
            elif not raw_occurrences:
                # Reviewed profile overrides can legitimately provide a contract
                # when the renderer path is not represented by the generic SCN
                # command shapes. Keep this visible rather than pretending an
                # occurrence was found.
                record_blockers.append(
                    "no generic SCN display occurrence identified; verify profile-backed renderer evidence"
                )

            defects.extend(f"{record_id}: {problem}" for problem in record_defects)
            blockers.extend(f"{record_id}: {problem}" for problem in record_blockers)
            records.append(
                {
                    "id": record_id,
                    "text": item.get("display_text"),
                    "roles": item.get("roles"),
                    "layout_policy": item.get("layout_policy"),
                    "box": box,
                    "layout": layout,
                    "max_rows": item.get("max_rows"),
                    "rows": row_details,
                    "occurrence_count": len(raw_occurrences),
                    "occurrences": raw_occurrences,
                    "defects": record_defects,
                    "blockers": record_blockers,
                    "certified": not record_defects and not record_blockers,
                }
            )

    translated_count = len(records)
    certified_count = sum(bool(record["certified"]) for record in records)
    unresolved_count = sum(bool(record["blockers"]) for record in records)
    defect_record_count = sum(bool(record["defects"]) for record in records)
    return {
        "status": "PASS" if not defects and not blockers else "FAIL",
        "schema_version": 1,
        "purpose": "layout-only certification; English wording/translation quality is out of scope",
        "translated_record_count": translated_count,
        "certified_record_count": certified_count,
        "unresolved_record_count": unresolved_count,
        "defect_record_count": defect_record_count,
        "occurrence_count": occurrence_count,
        "box_counts": dict(sorted(box_counts.items())),
        "defect_count": len(defects),
        "defects": defects,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "records": records,
    }


def write_tsv(path: Path, report: dict[str, object]) -> None:
    """Write one compact row per translated record for spreadsheet review."""
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "id",
        "box",
        "layout_policy",
        "roles",
        "occurrence_count",
        "rows",
        "certified",
        "defects",
        "blockers",
        "text",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for record in report["records"]:
            writer.writerow(
                {
                    "id": record["id"],
                    "box": record["box"],
                    "layout_policy": record["layout_policy"],
                    "roles": ",".join(record["roles"] or []),
                    "occurrence_count": record["occurrence_count"],
                    "rows": " | ".join(
                        f"{row['used_cells']}/{row['permitted_cells'] if row['permitted_cells'] is not None else '?'}:{row['text']}"
                        for row in record["rows"]
                    ),
                    "certified": record["certified"],
                    "defects": " | ".join(record["defects"]),
                    "blockers": " | ".join(record["blockers"]),
                    "text": record["text"],
                }
            )


def main() -> None:
    """Run the audit and write JSON plus TSV review artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--tsv", type=Path, default=DEFAULT_TSV)
    args = parser.parse_args()
    report = audit(args.retail_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_tsv(args.tsv, report)
    summary = {key: value for key, value in report.items() if key != "records"}
    print(json.dumps(summary, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

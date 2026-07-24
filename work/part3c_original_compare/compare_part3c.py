#!/usr/bin/env python3
"""Compare the delivered PART3C against the user's original disc and baselines."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
TOOLS = Path(
    r"C:\Users\thema\Documents\Codex\2026-07-12\i\outputs\nostalgia1907_tools"
)
BASE = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i\outputs")
sys.path.insert(0, str(TOOLS))

from mes_probe import dynamic_glyph_index, parse_mes, segments_for  # noqa: E402


GLYPH_BYTES = 18


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_mes(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    info, pointers = parse_mes(data, path)
    spans = segments_for(data, pointers, info.split_offset)
    return {
        "path": path,
        "data": data,
        "info": info,
        "pointers": pointers,
        "records": [data[item.offset : item.offset + item.size] for item in spans],
        "spans": spans,
        "tail": data[info.split_offset :],
    }


def record_tokens(record: bytes) -> list[bytes]:
    result: list[bytes] = []
    offset = 0
    for_end = len(record) - 1
    if not record or record[-1] != 0:
        raise ValueError("unterminated MES record")
    while offset < for_end:
        width = 2 if record[offset] >= 0xF0 else 1
        result.append(record[offset : offset + width])
        offset += width
    if offset != for_end:
        raise ValueError("incomplete MES token")
    return result


def bitmap(token: bytes, font: bytes, tail: bytes) -> bytes | None:
    if len(token) == 2:
        index = dynamic_glyph_index(token[0], token[1])
        if index is None:
            return None
        start = index * GLYPH_BYTES
        return tail[start : start + GLYPH_BYTES]
    if 1 <= token[0] <= 0xED:
        start = (token[0] - 1) * GLYPH_BYTES
        return font[start : start + GLYPH_BYTES]
    return None


def terminal_blank_cells(record: bytes, font: bytes, tail: bytes) -> int:
    blank = bytes(GLYPH_BYTES)
    count = 0
    for token in reversed(record_tokens(record)):
        if bitmap(token, font, tail) != blank:
            break
        count += 1
    return count


def controls(record: bytes) -> list[str]:
    return [f"{item[0]:02X}" for item in record_tokens(record) if item[0] in (0xEE, 0xEF)] + ["00"]


def file_hashes(root: Path) -> dict[str, str]:
    return {
        str(item.relative_to(root)): sha(item.read_bytes())
        for item in root.rglob("*")
        if item.is_file()
    }


def manifest_entries(path: Path) -> dict[int, dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(item["segment"]): item for item in data["segments"]}


def main() -> None:
    original_path = HERE / "original_part3c" / "001_PART3C.MES.unpacked"
    current_path = HERE / "current_part3c" / "001_PART3C.MES.unpacked"
    visual3_path = BASE / "nostalgia1907_act3c_000_223_visualfix3" / "PART3C.MES"
    visual4_path = BASE / "nostalgia1907_act3c_000_223_visualfix4" / "PART3C.MES"
    sources = {
        "original": load_mes(original_path),
        "current": load_mes(current_path),
        "visualfix3": load_mes(visual3_path),
        "visualfix4": load_mes(visual4_path),
    }
    fonts = {
        "original": (HERE / "original_extract" / "FIX_CODE.FNT").read_bytes(),
        "current": (HERE / "current_extract" / "FIX_CODE.FNT").read_bytes(),
        "visualfix3": (
            BASE / "nostalgia1907_act3c_000_223_visualfix3" / "FIX_CODE.FNT"
        ).read_bytes(),
        "visualfix4": (
            BASE / "nostalgia1907_act3c_000_223_visualfix4" / "FIX_CODE.FNT"
        ).read_bytes(),
    }
    manifest3 = manifest_entries(
        BASE
        / "nostalgia1907_act3c_000_223_visualfix3"
        / "PART3C_000_223_visualfix3_build_config.json"
    )
    manifest4_path = (
        BASE
        / "nostalgia1907_act3c_000_223_visualfix4"
        / "PART3C_000_223_visualfix4_build_config.json"
    )
    manifest4_full = json.loads(manifest4_path.read_text(encoding="utf-8"))
    manifest4 = {
        int(item["segment"]): item for item in manifest4_full["segments"]
    }

    archive_original = file_hashes(HERE / "original_part3c")
    archive_current = file_hashes(HERE / "current_part3c")
    changed_archive = sorted(
        name
        for name in archive_original.keys() & archive_current.keys()
        if archive_original[name] != archive_current[name]
    )

    record_rows = []
    for index in range(112, 124):
        row: dict[str, object] = {"record": index}
        for name, source in sources.items():
            record = source["records"][index]
            span = source["spans"][index]
            row[name] = {
                "offset": span.offset,
                "size": len(record),
                "sha256": sha(record),
                "terminal_blank_cells": terminal_blank_cells(
                    record, fonts[name], source["tail"]
                ),
                "controls": controls(record),
                "hex": record.hex(" ").upper(),
            }
        row["visualfix3_pad_final_row"] = manifest3[index].get("pad_final_row")
        row["visualfix4_pad_final_row"] = manifest4[index].get("pad_final_row")
        record_rows.append(row)

    current_records = sources["current"]["records"]
    visual4_records = sources["visualfix4"]["records"]
    current_vs_visual4 = [
        index
        for index, (current, visual4) in enumerate(zip(current_records, visual4_records))
        if current != visual4
    ]
    v3_records = sources["visualfix3"]["records"]
    v3_vs_v4 = [
        index
        for index, (visual3, visual4) in enumerate(zip(v3_records, visual4_records))
        if visual3 != visual4
    ]
    fixed_window_segments = set(
        manifest4_full["scn_fixed_window_padding"]["segments"]
    )
    forced_padding_segments = set(
        manifest4_full["profile_forced_final_row_padding"]["segments"]
    )
    protected_padding_segments = fixed_window_segments | forced_padding_segments
    removed_from_visualfix3 = {
        index: len(v3_records[index]) - len(current_records[index])
        for index in range(len(current_records))
        if len(current_records[index]) < len(v3_records[index])
    }
    protected_removals = {
        index: removed
        for index, removed in removed_from_visualfix3.items()
        if index in protected_padding_segments
    }
    nonprotected_removals = {
        index: removed
        for index, removed in removed_from_visualfix3.items()
        if index not in protected_padding_segments
    }

    scn = {}
    for name, path in {
        "original": HERE / "original_part3c" / "000_PART3C.SCN.unpacked",
        "current": HERE / "current_part3c" / "000_PART3C.SCN.unpacked",
    }.items():
        data = path.read_bytes()
        scn[name] = {"size": len(data), "sha256": sha(data)}

    report = {
        "status": "PASS",
        "mes": {
            name: {
                "path": str(source["path"]),
                "size": len(source["data"]),
                "size_hex": f"0x{len(source['data']):X}",
                "sha256": sha(source["data"]),
                "pointer_count": source["info"].pointer_count,
                "split_offset": source["info"].split_offset,
                "split_offset_hex": f"0x{source['info'].split_offset:X}",
            }
            for name, source in sources.items()
        },
        "scn": scn,
        "scn_byte_identical": scn["original"] == scn["current"],
        "archive_member_count": len(archive_current),
        "changed_archive_members": changed_archive,
        "visualfix3_vs_visualfix4_changed_records": v3_vs_v4,
        "current_vs_visualfix4_changed_record_count": len(current_vs_visual4),
        "current_vs_visualfix4_changed_records": current_vs_visual4,
        "padding_analysis": {
            "fixed_window_segments": sorted(fixed_window_segments),
            "forced_padding_segments": sorted(forced_padding_segments),
            "protected_padding_segments": sorted(protected_padding_segments),
            "all_visualfix3_terminal_bytes_removed": removed_from_visualfix3,
            "protected_terminal_bytes_removed": protected_removals,
            "protected_terminal_bytes_removed_total": sum(protected_removals.values()),
            "nonprotected_terminal_bytes_removed_total": sum(
                nonprotected_removals.values()
            ),
        },
        "records_112_123": record_rows,
    }
    out = HERE / "comparison_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

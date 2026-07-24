#!/usr/bin/env python3
"""Print SCN text commands that reference PART3C MES records 140-170."""

import json
import sys
from pathlib import Path


SCN = (
    Path(__file__).resolve().parents[1]
    / "part3c_original_compare"
    / "original_part3c"
    / "000_PART3C.SCN.unpacked"
)
CONFIG = Path(
    r"C:\Users\thema\Documents\Codex\2026-07-12\i\outputs"
    r"\nostalgia1907_act3c_000_223_visualfix3"
    r"\PART3C_000_223_visualfix3_build_config.json"
)
PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
TOOLS = PROJECT / "outputs" / "nostalgia1907_tools"
ORIGINAL_MES = SCN.with_name("001_PART3C.MES.unpacked")
MES_VARIANTS = {
    "original": ORIGINAL_MES,
    "visualfix3": (
        PROJECT
        / "outputs"
        / "nostalgia1907_act3c_000_223_visualfix3"
        / "PART3C.MES"
    ),
    "globalfontfix3": (
        Path(__file__).resolve().parents[1]
        / "part3c_globalfontfix3"
        / "PART3C_globalfontfix3.MES"
    ),
    "cursorparityfix4": Path(__file__).with_name("PART3C_cursorparityfix4.MES"),
}

sys.path.insert(0, str(TOOLS))

from mes_probe import parse_mes, segments_for  # noqa: E402


def main() -> None:
    """Print matching dialogue and floating-window commands."""
    data = SCN.read_bytes()
    for offset in range(len(data) - 8):
        opcode = data[offset]
        if opcode == 0x21:
            first = int.from_bytes(data[offset + 1 : offset + 3], "big")
            second = int.from_bytes(data[offset + 3 : offset + 5], "big")
            records = []
            if 141 <= first <= 171:
                records.append(first - 1)
            if 141 <= second <= 171:
                records.append(second - 1)
            if records:
                raw = data[offset : offset + 8].hex(" ").upper()
                print(f"{offset:04X} 21 {raw} records={records}")
        elif opcode == 0x24 and data[offset + 5] in (0x27, 0x28):
            text_id = int.from_bytes(data[offset + 6 : offset + 8], "big")
            if 141 <= text_id <= 171:
                raw = data[offset : offset + 9].hex(" ").upper()
                print(f"{offset:04X} 24 {raw} record={text_id - 1}")

    print("\nRaw SCN bytes 0x09C0-0x0B80:")
    for offset in range(0x09C0, 0x0B80, 16):
        raw = data[offset : offset + 16]
        print(f"{offset:04X}: {raw.hex(' ').upper()}")

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    segments = {int(item["segment"]): item for item in config["segments"]}
    print("\nVisualfix3 records 143-166:")
    for index in range(143, 167):
        item = segments.get(index)
        if item is None:
            print(f"{index}: untranslated/preserved record (not in manifest)")
            continue
        text = item["text"].replace("\n", "\\n")
        print(
            f"{index}: cells={item['render_cell_count']} "
            f"bytes={item['after']['size']} pad={item['pad_final_row']} "
            f"text={text!r}"
        )

    print("\nExact MES records 158-164 by variant:")
    for name, path in MES_VARIANTS.items():
        mes = path.read_bytes()
        info, pointers = parse_mes(mes, path)
        spans = segments_for(mes, pointers, info.split_offset)
        print(f"{name}: size=0x{len(mes):X} split=0x{info.split_offset:X}")
        for index in range(158, 165):
            span = spans[index]
            record = mes[span.offset : span.offset + span.size]
            print(f"  {index}: {record.hex(' ').upper()}")


if __name__ == "__main__":
    main()

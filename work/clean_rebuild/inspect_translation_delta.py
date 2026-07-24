#!/usr/bin/env python3
"""Compare retail and playable MES record sets against translation profiles."""

from __future__ import annotations

import json
from pathlib import Path

from mes_format import changed_record_indexes, read_mes


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
OLD_PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
ORIGINAL = OLD_PROJECT / "work" / "nostalgia1907" / "unpacked"
GOLDEN = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Act4_firstpass_credits"
    / "regression"
    / "unpacked"
)
PROFILES = OLD_PROJECT / "outputs" / "nostalgia1907_translation_profiles"
REPORT = HERE / "translation_delta.json"


def main() -> None:
    """Write a report proving whether profile keys cover every changed record."""
    result: dict[str, object] = {"status": "PASS", "chapters": {}}
    chapters: dict[str, object] = result["chapters"]  # type: ignore[assignment]
    for chapter in ("PART2F", "PART3B", "PART3B_"):
        source = ORIGINAL / chapter / f"001_{chapter}.MES.unpacked"
        playable = GOLDEN / chapter / f"001_{chapter}.MES.unpacked"
        original_mes = read_mes(source)
        playable_mes = read_mes(playable)
        changed = set(changed_record_indexes(original_mes, playable_mes))

        profile_path = PROFILES / f"{chapter}.json"
        profile_keys: set[int] = set()
        if profile_path.exists():
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile_keys = {
                int(index) for index in profile.get("required_text_exact", {})
            }

        uncovered = sorted(changed - profile_keys)
        redundant = sorted(profile_keys - changed)
        entry = {
            "record_count": original_mes.record_count,
            "original_size": source.stat().st_size,
            "playable_size": playable.stat().st_size,
            "original_dynamic_glyphs": len(original_mes.glyphs),
            "playable_dynamic_glyphs": len(playable_mes.glyphs),
            "changed_records": sorted(changed),
            "profile_text_records": sorted(profile_keys),
            "changed_records_missing_profile_text": uncovered,
            "profile_records_unchanged_in_playable": redundant,
            "profile_covers_all_changed_records": not uncovered,
        }
        chapters[chapter] = entry
        if uncovered:
            result["status"] = "FAIL"

    REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

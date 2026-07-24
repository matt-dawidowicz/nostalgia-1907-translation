#!/usr/bin/env python3
"""Freeze all translated chapters into one self-contained canonical schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from mes_format import read_mes


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
PROVENANCE = HERE / "source_provenance.json"
RECOVERED = HERE / "recovered_compiled_text.json"
PART3B_TRANSLATION = HERE / "part3b_translation.json"
OUT_ROOT = HERE / "sources"

CHAPTERS = (
    "START",
    "PART1A",
    "PART1B",
    "PART1C",
    "PART1D",
    "PART2A",
    "PART2B",
    "PART2C",
    "PART2D",
    "PART2E",
    "PART2F",
    "PART3A",
    "PART3B",
    "PART3B_",
    "PART3C",
    "PART4A",
    "PART4B",
    "PART4C",
    "STAFF",
)

PART1A_MANIFEST = (
    OLD_PROJECT
    / "outputs"
    / "nostalgia1907_act2e_complete"
    / "profile_migration_verify"
    / "PART1A_manifest.json"
)
PART3C_MANIFEST = (
    OLD_PROJECT
    / "outputs"
    / "nostalgia1907_act3c_000_223_visualfix3"
    / "PART3C_000_223_visualfix3_build_config.json"
)

# These are visible word-boundary defects proven by the compiled PART2F glyph
# stream.  Correcting them here prevents the clean source from canonizing old
# render-compaction artifacts as translator prose.
PART2F_FORMATTING_FIXES = {
    32: "Then we are alike...",
    35: "It hurts, doesn't it? I enjoyed our card game.",
    36: (
        "Do not turn me into one last memory and die. Hold on! I still do not "
        "understand. The St. Petersburg treasure. Words that curse the nobility. "
        "A secret weapon that could overturn Europe's balance of power..."
    ),
    50: "Your voice sounds far away...",
    60: "It is like a riddle from the Sphinx, young man.",
    61: "Rumor sees only one side of the truth.",
    66: "You mean the words combine to reveal another meaning?",
    67: (
        "When people hide the truth, they substitute one word for another. Yet "
        "the words they choose still carry the impression of the truth beneath them."
    ),
    74: (
        "The Russian Fog is a person: an experienced soldier serving the Tsar "
        "directly, feared even by Russian nobles and charged with watching them."
    ),
    78: (
        "The Russian court swarms with intelligence agents. Capture one close to "
        "the Tsar and you gain his plans, habits, and intentions. That knowledge "
        "is worth sinking a floating palace."
    ),
    95: "Hard eyes. He is no civilian.",
    110: "I wore several masks. They were meant to fool the Russian agents.",
    120: "I dismissed it. Six months later another message came, this time signed:",
    127: "Active in the St. Petersburg court since 1897.",
    129: (
        "Active in Manchuria since 1903 as an anti-British and anti-Japanese agent."
    ),
    132: "Enough to overturn the future balance of power.",
    136: "The final message arrived this January.",
    146: "There is only one answer: defection.",
    148: (
        "NOSTALGIA sails from New York to Britain. Its name was a signal, and "
        "those accusations proved the value of the intelligence offered."
    ),
    152: (
        "I accept that risk. I can still take my own life. This is too much for a "
        "junior officer. Let me do one last job before I retire."
    ),
    158: (
        "Russian counterintelligence may be trying to stop the defection, or a "
        "third nation may be trying to seize the agent."
    ),
    160: (
        "The culprit may be one person, but that person carries out a nation's will."
    ),
    161: (
        "Besides the Russian Fog, other spies must be aboard. Russian "
        "counterintelligence often assigns several agents to watch one target "
        "without telling them of one another."
    ),
    176: "Joseph the bellboy and several others remain under suspicion.",
    185: "One bomb remains. It will explode at 7:00 p.m.",
    187: "Again: recover the Russian Fog.",
    192: "I last left this room at 2:51 p.m. It is now 3:05.",
}


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_json(path: Path) -> dict[str, object]:
    """Load one JSON object."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def full_manifest_for(chapter: str, provenance: dict[str, object]) -> Path:
    """Choose a deterministic complete text manifest for a playable MES."""
    chapter_info = provenance["chapters"][chapter]  # type: ignore[index]
    paths = sorted(
        Path(manifest["path"])
        for match in chapter_info["matching_generated_mes"]
        for manifest in match["manifests"]
        if manifest.get("all_segments_have_text")
    )
    if not paths:
        raise ValueError(f"{chapter}: no complete text-bearing manifest")
    return paths[0]


def manifest_texts(path: Path) -> dict[int, str]:
    """Return record text from a historical build manifest."""
    payload = load_json(path)
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise ValueError(f"{path}: missing segments")
    texts: dict[int, str] = {}
    for item in segments:
        if not isinstance(item, dict):
            raise ValueError(f"{path}: invalid segment entry")
        index = item.get("segment")
        text = item.get("text")
        if not isinstance(index, int) or not isinstance(text, str):
            raise ValueError(f"{path}: segment lacks integer index or text")
        texts[index] = text
    return texts


def recovered_texts(chapter: str) -> dict[int, str]:
    """Return bitmap-recovered text for one chapter."""
    payload = load_json(RECOVERED)
    if payload.get("status") != "PASS":
        raise ValueError("compiled-text recovery has not passed its locked fixtures")
    for item in payload["chapters"]:  # type: ignore[index]
        if item["chapter"] == chapter:
            return {entry["record"]: entry["text"] for entry in item["records"]}
    raise ValueError(f"{chapter}: no recovered text")


def profile_texts(chapter: str) -> dict[int, str]:
    """Return all exact record strings from a translation profile."""
    profile = load_json(PROFILES / f"{chapter}.json")
    return {
        int(index): text
        for index, text in profile.get("required_text_exact", {}).items()
    }


def local_translation(path: Path) -> tuple[dict[int, str], set[int], dict[str, object]]:
    """Load one self-contained clean-rebuild translation manifest."""
    payload = load_json(path)
    raw_texts = payload.get("texts")
    raw_preserved = payload.get("preserved_records", [])
    profile = payload.get("profile")
    if not isinstance(raw_texts, dict) or not all(
        isinstance(index, str) and index.isdigit() and isinstance(text, str)
        for index, text in raw_texts.items()
    ):
        raise ValueError(f"{path}: invalid texts table")
    if not isinstance(raw_preserved, list) or not all(
        isinstance(index, int) for index in raw_preserved
    ):
        raise ValueError(f"{path}: invalid preserved-record table")
    if not isinstance(profile, dict):
        raise ValueError(f"{path}: missing compiler profile")
    return (
        {int(index): text for index, text in raw_texts.items()},
        set(raw_preserved),
        profile,
    )


def build_text_map(
    chapter: str, record_count: int, provenance: dict[str, object]
) -> tuple[dict[int, str], set[int], list[str], str]:
    """Return canonical text, explicitly preserved records, and provenance."""
    preserved: set[int] = set()
    sources: list[str] = []

    if chapter == "PART1A":
        texts = manifest_texts(PART1A_MANIFEST)
        preserved = set(range(record_count)) - set(texts)
        sources.append(str(PART1A_MANIFEST))
        text_mode = "render-ready"
    elif chapter == "PART2F":
        texts = recovered_texts(chapter)
        texts.update(PART2F_FORMATTING_FIXES)
        sources.extend([str(RECOVERED), "inline PART2F formatting corrections"])
        text_mode = "prose"
    elif chapter == "PART3B":
        texts = profile_texts(chapter)
        preserved = set(range(record_count)) - set(texts)
        sources.append(str(PROFILES / "PART3B.json"))
        text_mode = "prose"
    elif chapter == "PART3B_":
        texts, preserved, _ = local_translation(PART3B_TRANSLATION)
        sources.append(str(PART3B_TRANSLATION))
        text_mode = "prose"
    elif chapter == "PART3C":
        texts = manifest_texts(PART3C_MANIFEST)
        texts[194] = "Ashby"
        preserved = set(range(record_count)) - set(texts)
        sources.extend(
            [str(PART3C_MANIFEST), "record 194 translated directly from source アッシュビー"]
        )
        text_mode = "render-ready"
    else:
        manifest = full_manifest_for(chapter, provenance)
        texts = manifest_texts(manifest)
        sources.append(str(manifest))
        text_mode = "render-ready"

    invalid = (set(texts) | preserved) - set(range(record_count))
    if invalid:
        raise ValueError(f"{chapter}: record indexes outside table: {sorted(invalid)}")
    overlap = set(texts) & preserved
    if overlap:
        raise ValueError(f"{chapter}: records both translated and preserved: {overlap}")
    missing = set(range(record_count)) - set(texts) - preserved
    if missing:
        raise ValueError(f"{chapter}: records lack a declared policy: {sorted(missing)}")
    return texts, preserved, sources, text_mode


def main() -> None:
    """Build and validate the canonical source directory."""
    provenance = load_json(PROVENANCE)
    if provenance.get("status") != "PASS":
        raise ValueError("source provenance audit is not passing")

    staging = HERE / "sources.new"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    index: dict[str, object] = {
        "schema_version": 1,
        "chapter_count": len(CHAPTERS),
        "chapters": [],
    }

    for chapter in CHAPTERS:
        retail_path = ORIGINAL / chapter / f"001_{chapter}.MES.unpacked"
        reference_path = GOLDEN / chapter / f"001_{chapter}.MES.unpacked"
        retail_scn_path = ORIGINAL / chapter / f"000_{chapter}.SCN.unpacked"
        retail_mes = read_mes(retail_path)
        reference_mes = read_mes(reference_path)
        if retail_mes.record_count != reference_mes.record_count:
            raise ValueError(f"{chapter}: retail/reference record-count mismatch")
        texts, preserved, text_sources, text_mode = build_text_map(
            chapter, retail_mes.record_count, provenance
        )

        profile_path = PROFILES / f"{chapter}.json"
        if chapter == "PART3B_":
            _, _, profile = local_translation(PART3B_TRANSLATION)
        else:
            profile = load_json(profile_path) if profile_path.exists() else None
        payload = {
            "schema_version": 1,
            "chapter": chapter,
            "record_count": retail_mes.record_count,
            "retail_mes": {
                "sha256": sha256(retail_path),
                "size": retail_path.stat().st_size,
                "dynamic_glyph_count": len(retail_mes.glyphs),
            },
            "retail_scn": {
                "sha256": sha256(retail_scn_path),
                "size": retail_scn_path.stat().st_size,
            },
            "playable_reference_mes": {
                "sha256": sha256(reference_path),
                "size": reference_path.stat().st_size,
                "dynamic_glyph_count": len(reference_mes.glyphs),
            },
            "profile": profile,
            "text_mode": text_mode,
            "text_sources": text_sources,
            "records": [
                {
                    "index": index_number,
                    "policy": "preserve" if index_number in preserved else "translate",
                    "text": texts.get(index_number),
                }
                for index_number in range(retail_mes.record_count)
            ],
        }
        out_path = staging / f"{chapter}.json"
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        index["chapters"].append(  # type: ignore[union-attr]
            {
                "chapter": chapter,
                "source": out_path.name,
                "record_count": retail_mes.record_count,
                "translated_records": len(texts),
                "preserved_records": len(preserved),
            }
        )

    (staging / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    staging.rename(OUT_ROOT)
    print(json.dumps({"status": "PASS", **index}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-legacy-import",
        action="store_true",
        help="explicitly permit the historical positional-manifest import",
    )
    args = parser.parse_args()
    if not args.allow_legacy_import:
        raise SystemExit(
            "Refusing to overwrite repaired canonical sources from historical positional manifests. "
            "Pass --allow-legacy-import only for a deliberate migration, then immediately run "
            "apply_translation_repairs.py and translation_validation.py."
        )
    main()

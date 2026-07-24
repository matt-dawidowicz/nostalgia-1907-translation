#!/usr/bin/env python3
"""Orchestrate and prove a deterministic retail-to-English BIN/CUE rebuild.

This is the production graph's composition root. One build verifies/extracts
retail Track 1, compiles all canonical MES files, installs them into guarded LZ
and ISO allocations, applies the frozen UI/font changes, reconstructs raw
MODE1/2352 sectors, copies Track 2 exactly, writes the CUE, and runs the complete
binary regression.

A release invokes that process twice in fresh independent trees. Hash manifests
cover intermediate MES/LZ/font/ISO artifacts as well as delivery BIN/CUE files;
nothing is published unless both manifests are identical.

``PRODUCTION_MODULES`` is also a policy boundary. Tests and runtime checks use
it to prevent historical investigation workspaces or playable older builds from
becoming dependencies. See ``docs/ARCHITECTURE.md`` for stage ownership.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from build_archives import build_archives
from build_mes_set import build_mes_set
from iso9660 import patch_fixed_extent_files
from main_patch import patch_main
from prepare_retail import prepare_retail
from raw_cd import iso_to_raw_fixed, write_two_track_cue
from regression import sha256, validate_build


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
SOURCES = HERE / "sources"
DEFAULT_BASENAME = "Nostalgia1907_CleanRebuild"
PRODUCTION_MODULES = (
    "raw_cd.py",
    "iso9660.py",
    "lz_format.py",
    "mes_format.py",
    "font_render.py",
    "scn_layout.py",
    "mes_compiler.py",
    "prepare_retail.py",
    "build_mes_set.py",
    "build_archives.py",
    "main_patch.py",
    "regression.py",
    "rebuild.py",
)


# One isolated build and its artifact manifest.


def _ensure_empty(path: Path) -> None:
    """Create a new staging directory and reject stale build contents."""
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"refusing to reuse non-empty clean-build directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _verify_production_independence() -> None:
    """Reject accidental runtime references to legacy or playable build trees."""
    forbidden = (
        "2026-" + "07-12",
        "Act4_" + "firstpass",
        "nostalgia1907_" + "tools",
    )
    for name in PRODUCTION_MODULES:
        text = (HERE / name).read_text(encoding="utf-8")
        hits = [value for value in forbidden if value in text]
        if hits:
            raise ValueError(f"production module {name} references legacy inputs: {hits}")


def _build_once(
    track1: Path,
    track2: Path,
    build_root: Path,
    product_root: Path,
    basename: str,
) -> dict[str, object]:
    """Perform one complete retail-to-test-image build and regression pass."""
    _ensure_empty(build_root)
    _ensure_empty(product_root)
    prepare_retail(track1, build_root)
    build_mes_set(build_root)
    build_archives(build_root)

    retail_main = build_root / "retail_files" / "MAIN.BIN"
    patched_main = build_root / "MAIN.BIN"
    patched_main.write_bytes(patch_main(retail_main.read_bytes()))

    index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
    replacements = {
        f"{item['chapter']}.LZ": build_root
        / "archives"
        / f"{item['chapter']}.LZ"
        for item in index["chapters"]
    }
    replacements.update(
        {
            "FIX_CODE.FNT": build_root / "FIX_CODE.FNT",
            "MAIN.BIN": patched_main,
        }
    )
    iso_report = patch_fixed_extent_files(
        build_root / "retail.iso",
        build_root / "translated.iso",
        replacements,
    )
    (build_root / "iso_patch_report.json").write_text(
        json.dumps(iso_report, indent=2) + "\n", encoding="utf-8"
    )

    output_track1 = product_root / f"{basename}_Track1.bin"
    output_track2 = product_root / f"{basename}_Track2.bin"
    output_cue = product_root / f"{basename}.cue"
    iso_to_raw_fixed(track1, build_root / "translated.iso", output_track1)
    shutil.copyfile(track2, output_track2)
    write_two_track_cue(output_cue, output_track1, output_track2)
    verification = validate_build(
        build_root, product_root, track1, track2, basename
    )
    (product_root / "verification.json").write_text(
        json.dumps(verification, indent=2) + "\n", encoding="utf-8"
    )
    return verification


def _manifest(build_root: Path, product_root: Path) -> dict[str, str]:
    """Hash all deterministic binary artifacts from one run."""
    files: dict[str, Path] = {
        "FIX_CODE.FNT": build_root / "FIX_CODE.FNT",
        "MAIN.BIN": build_root / "MAIN.BIN",
        "translated.iso": build_root / "translated.iso",
    }
    files.update(
        {f"mes/{path.name}": path for path in sorted((build_root / "mes").glob("*.MES"))}
    )
    files.update(
        {
            f"archives/{path.name}": path
            for path in sorted((build_root / "archives").glob("*.LZ"))
        }
    )
    files.update({f"product/{path.name}": path for path in sorted(product_root.glob("*.bin"))})
    files.update({f"product/{path.name}": path for path in sorted(product_root.glob("*.cue"))})
    return {name: sha256(path) for name, path in sorted(files.items())}


# Two-run determinism proof and publication.


def rebuild(
    track1: Path,
    track2: Path,
    runs_root: Path,
    delivery_root: Path,
    basename: str,
) -> dict[str, object]:
    """Build twice, prove byte identity, and publish one fresh BIN/CUE set."""
    _verify_production_independence()
    run_a_build = runs_root / "run_a" / "build"
    run_a_product = runs_root / "run_a" / "product"
    run_b_build = runs_root / "run_b" / "build"
    run_b_product = runs_root / "run_b" / "product"
    first = _build_once(track1, track2, run_a_build, run_a_product, basename)
    second = _build_once(track1, track2, run_b_build, run_b_product, basename)
    manifest_a = _manifest(run_a_build, run_a_product)
    manifest_b = _manifest(run_b_build, run_b_product)
    if manifest_a != manifest_b:
        mismatches = sorted(
            name
            for name in set(manifest_a) | set(manifest_b)
            if manifest_a.get(name) != manifest_b.get(name)
        )
        raise ValueError(f"two clean builds were not byte-identical: {mismatches}")

    _ensure_empty(delivery_root)
    for suffix in ("_Track1.bin", "_Track2.bin", ".cue"):
        name = f"{basename}{suffix}"
        shutil.copyfile(run_a_product / name, delivery_root / name)
    report = {
        "status": "PASS",
        "pipeline": "retail Japanese Track 1 -> clean extraction -> canonical translation -> fixed extents -> BIN/CUE",
        "production_legacy_dependencies": 0,
        "two_clean_builds_byte_identical": True,
        "artifact_count_compared": len(manifest_a),
        "verification": first,
        "second_verification": second,
        "artifact_sha256": manifest_a,
    }
    (delivery_root / "final_verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    notes = (
        "# Nostalgia 1907 clean rebuild\n\n"
        "Built twice, byte-for-byte identically, from the verified original Japanese BIN.\n"
        "The production pipeline does not import or copy any legacy translated build.\n\n"
        "Static checks cover all 19 chapters and 2,905 records, MES pointer/glyph bounds, "
        "the PART3C 0x3FFF limit, exhaustive adaptive/fixed layout policies, renderer-proven "
        "row and width limits, speaker-label regression, archive round trips, unchanged "
        "SCN/non-MES payloads, fixed ISO extents, ISO mutation boundaries, all MODE1 EDC/ECC "
        "sectors, retail boot data, exact Track 2 audio, and CUE formatting.\n\n"
        "All 2,759 SCN-classified visible records use adaptive renderer-aware wrapping. "
        "The remaining 123 credits, counters, static labels, and direct overlays have "
        "explicit fixed-layout policy; no record is undeclared and no classified record "
        "retains legacy manual wrapping.\n\n"
        "PART3B_ scenes 106-113 now contain 209 translated records; retail records 4 and 15 "
        "remain retail-preserved without translation or reflow because they are "
        "blank/punctuation-only window records.\n\n"
        "Manual playtesting remains the final release gate, especially dialogue formatting.\n"
    )
    (delivery_root / "TEST_NOTES.md").write_text(notes, encoding="utf-8")
    return report


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track1", type=Path)
    parser.add_argument("track2", type=Path)
    parser.add_argument("--runs-root", type=Path, default=HERE / "runs")
    parser.add_argument(
        "--delivery-root",
        type=Path,
        default=WORKSPACE / "outputs" / DEFAULT_BASENAME,
    )
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    args = parser.parse_args()
    result = rebuild(
        args.track1, args.track2, args.runs_root, args.delivery_root, args.basename
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "two_clean_builds_byte_identical": result[
                    "two_clean_builds_byte_identical"
                ],
                "delivery_root": str(args.delivery_root),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

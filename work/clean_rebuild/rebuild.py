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
it for a static local-import allowlist, tracked-data path containment, and known
historical-workspace marker audit. Retail provenance remains separately
hash-guarded. See ``docs/ARCHITECTURE.md`` for stage ownership.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
from pathlib import Path

from .build_archives import build_archives
from .build_mes_set import build_mes_set
from .iso9660 import patch_fixed_extent_files
from .source_json import load_json_object
from .main_patch import patch_main
from .prepare_retail import prepare_retail
from .raw_cd import iso_to_raw_fixed, write_two_track_cue
from .regression import validate_build
from .verification_manifest import (
    assert_exact_managed_inventory,
    collect_build_bindings,
    create_input_manifest,
    expected_build_artifacts,
    expected_delivery_artifacts,
    snapshot_artifacts,
    write_bound_verification,
)


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
SOURCES = HERE / "sources"
DEFAULT_BASENAME = "Nostalgia1907_CleanRebuild"
RELEASE_BASENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SOURCE_JSON_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.json$")
PRODUCTION_MODULES = (
    "raw_cd.py",
    "iso9660.py",
    "lz_format.py",
    "mes_format.py",
    "source_json.py",
    "font_render.py",
    "scn_layout.py",
    "renderer_format.py",
    "profile_schema.py",
    "mes_compiler.py",
    "prepare_retail.py",
    "build_mes_set.py",
    "build_archives.py",
    "main_patch.py",
    "regression.py",
    "verification_manifest.py",
    "rebuild.py",
)


# One isolated build and its artifact manifest.


def _ensure_empty(path: Path) -> None:
    """Create a new staging directory and reject stale build contents."""
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"refusing to reuse non-empty clean-build directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _validate_basename(basename: str) -> str:
    """Reject path syntax and unsafe characters in a direct build basename."""
    if not isinstance(basename, str) or not RELEASE_BASENAME.fullmatch(basename):
        raise ValueError(
            "basename must start with a letter or digit and contain only "
            "letters, digits, period, underscore, or hyphen"
        )
    return basename


def _legacy_markers() -> tuple[str, ...]:
    """Return known historical-workspace markers without self-matching source."""
    return (
        "2026-" + "07-12",
        "Act4_" + "firstpass",
        "nostalgia1907_" + "tools",
    )


def _production_data_files(root: Path) -> tuple[Path, ...]:
    """Resolve every tracked static data file consumed by production modules."""
    sources = root / "sources"
    index_path = sources / "index.json"
    index = load_json_object(index_path)
    chapters = index.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("production source index has no chapters list")
    data_files = [root / "font_patterns.json", index_path]
    seen: set[str] = set()
    for item in chapters:
        if not isinstance(item, dict) or not isinstance(item.get("source"), str):
            raise ValueError("production source index contains an invalid source entry")
        source_name = item["source"]
        source_path = Path(source_name)
        if (
            source_path.is_absolute()
            or len(source_path.parts) != 1
            or source_path.name != source_name
            or not SOURCE_JSON_NAME.fullmatch(source_name)
        ):
            raise ValueError(
                f"production source path must be one JSON filename: {source_name!r}"
            )
        if source_name in seen:
            raise ValueError(f"production source index repeats {source_name!r}")
        seen.add(source_name)
        data_files.append(sources / source_name)
    missing = [str(path) for path in data_files if not path.is_file()]
    if missing:
        raise ValueError(f"production data files are missing: {missing}")
    return tuple(data_files)


def _verify_production_independence(
    root: Path = HERE,
    production_modules: tuple[str, ...] = PRODUCTION_MODULES,
) -> dict[str, object]:
    """Audit static production imports and tracked data against legacy inputs.

    The audit proves a bounded claim: every allowlisted module exists, its
    local imports remain inside the allowlist, all tracked production data
    paths stay under the clean source directory, and production code contains
    no known historical-workspace marker. Runtime retail inputs remain
    independently protected by size and SHA-256 validation.

    Args:
        root: Clean-rebuild module directory to audit.
        production_modules: Exact local Python-module allowlist.

    Returns:
        A JSON-serializable report describing the static audit scope.

    Raises:
        ValueError: If a module/data file is missing, an import escapes the
            allowlist, a source path escapes its root, or a forbidden marker is
            present.
    """
    allowed_files = set(production_modules)
    allowed_stems = {Path(name).stem for name in production_modules}
    local_modules = {path.stem: path.name for path in root.glob("*.py")}
    local_modules.update(
        {
            path.name: f"{path.name}/__init__.py"
            for path in root.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }
    )
    import_edges: set[str] = set()
    unapproved_imports: list[str] = []
    marker_hits: list[str] = []
    scanned_files: list[Path] = []
    markers = _legacy_markers()

    for name in production_modules:
        if Path(name).name != name or Path(name).suffix != ".py":
            raise ValueError(f"invalid production module name: {name!r}")
        path = root / name
        if name not in allowed_files or not path.is_file():
            raise ValueError(f"production module is missing: {path}")
        text = path.read_text(encoding="utf-8")
        scanned_files.append(path)
        for marker in markers:
            if marker in text:
                marker_hits.append(f"{name}: {marker}")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.level != 1:
                        unapproved_imports.append(
                            f"{name} -> relative:{'.' * node.level}{node.module or ''}"
                        )
                        continue
                    if node.module:
                        imported.append(node.module.split(".", 1)[0])
                    else:
                        imported.extend(
                            alias.name.split(".", 1)[0] for alias in node.names
                        )
                elif node.module:
                    imported.append(node.module.split(".", 1)[0])
            for imported_name in imported:
                local_file = local_modules.get(imported_name)
                if local_file is None:
                    continue
                import_edges.add(f"{name} -> {local_file}")
                if imported_name not in allowed_stems:
                    unapproved_imports.append(f"{name} -> {local_file}")

    data_files = _production_data_files(root)

    if unapproved_imports or marker_hits:
        problems = []
        if unapproved_imports:
            problems.append(f"unapproved local imports: {sorted(unapproved_imports)}")
        if marker_hits:
            problems.append(f"historical-workspace markers: {sorted(marker_hits)}")
        raise ValueError("production dependency audit failed: " + "; ".join(problems))

    return {
        "status": "PASS",
        "scope": (
            "static allowlisted local imports, known code markers, and tracked "
            "production-data path containment"
        ),
        "modules_scanned": len(production_modules),
        "data_files_scanned": len(data_files),
        "local_import_edges": sorted(import_edges),
        "unapproved_local_import_count": 0,
        "known_historical_marker_hit_count": 0,
        "known_historical_markers_checked": len(markers),
        "files_scanned": [
            path.relative_to(root).as_posix() for path in sorted(scanned_files)
        ],
        "data_files_validated": [
            path.relative_to(root).as_posix() for path in data_files
        ],
    }


def _canonical_coverage(sources: Path = SOURCES) -> dict[str, object]:
    """Derive release-note coverage directly from canonical source JSON."""
    index = load_json_object(sources / "index.json")
    items = index.get("chapters")
    if not isinstance(items, list):
        raise ValueError("canonical source index has no chapters list")
    totals = {
        "record_count": 0,
        "translated_record_count": 0,
        "preserved_record_count": 0,
        "adaptive_record_count": 0,
        "fixed_record_count": 0,
        "anchor_record_count": 0,
    }
    part3b_preserved: list[int] = []
    part3b_translated = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("canonical source index contains a non-object chapter")
        chapter = item.get("chapter")
        source_name = item.get("source")
        if not isinstance(chapter, str) or not isinstance(source_name, str):
            raise ValueError("canonical source index contains an invalid chapter entry")
        if not SOURCE_JSON_NAME.fullmatch(source_name):
            raise ValueError(
                f"{chapter}: canonical source path is unsafe: {source_name!r}"
            )
        source = load_json_object(sources / source_name)
        records = source.get("records")
        if not isinstance(records, list) or source.get("record_count") != len(records):
            raise ValueError(f"{chapter}: canonical record count is inconsistent")
        translated = 0
        preserved = 0
        for index_value, record in enumerate(records):
            if not isinstance(record, dict) or record.get("index") != index_value:
                raise ValueError(
                    f"{chapter}: canonical record ordering is inconsistent"
                )
            policy = record.get("policy")
            if policy == "translate":
                translated += 1
                layout_policy = record.get("layout_policy")
                if layout_policy == "adaptive":
                    totals["adaptive_record_count"] += 1
                elif layout_policy == "fixed":
                    totals["fixed_record_count"] += 1
                elif layout_policy == "anchor":
                    totals["anchor_record_count"] += 1
                else:
                    raise ValueError(
                        f"{chapter}:{index_value:03d}: translated record has no "
                        "explicit layout policy"
                    )
            elif policy == "preserve":
                preserved += 1
            else:
                raise ValueError(f"{chapter}:{index_value:03d}: invalid record policy")
        if (
            item.get("record_count") != len(records)
            or item.get("translated_records") != translated
            or item.get("preserved_records") != preserved
        ):
            raise ValueError(f"{chapter}: source-index coverage counts are stale")
        totals["record_count"] += len(records)
        totals["translated_record_count"] += translated
        totals["preserved_record_count"] += preserved
        if chapter == "PART3B_":
            part3b_translated = translated
            part3b_preserved = [
                record["index"]
                for record in records
                if record.get("policy") == "preserve"
            ]
    if index.get("chapter_count") != len(items):
        raise ValueError("canonical source-index chapter count is stale")
    if (
        totals["adaptive_record_count"]
        + totals["fixed_record_count"]
        + totals["anchor_record_count"]
        != totals["translated_record_count"]
    ):
        raise ValueError("canonical translated layout-policy counts are incomplete")
    return {
        "chapter_count": len(items),
        **totals,
        "part3b_translated_record_count": part3b_translated,
        "part3b_preserved_record_indexes": part3b_preserved,
    }


def _render_test_notes(coverage: dict[str, object]) -> str:
    """Render release notes from validated coverage and dependency evidence."""
    preserved_indexes = ", ".join(
        str(index) for index in coverage["part3b_preserved_record_indexes"]
    )
    return (
        "# Nostalgia 1907 clean rebuild\n\n"
        "Built twice, byte-for-byte identically, from the verified original "
        "Japanese BIN.\n"
        "Source-only validation separately enforces the production dependency "
        "boundary before a release build is accepted.\n\n"
        f"Static checks cover all {coverage['chapter_count']} chapters and "
        f"{coverage['record_count']:,} records, MES pointer/glyph bounds, the "
        "PART3C 0x3FFF limit, exhaustive adaptive/fixed layout policies, "
        "renderer-proven row and width limits, speaker-label regression, archive "
        "round trips, unchanged SCN/non-MES payloads, fixed ISO extents, ISO "
        "mutation boundaries, all MODE1 EDC/ECC sectors, retail boot data, exact "
        "Track 2 audio, and CUE formatting.\n\n"
        f"The canonical source declares {coverage['adaptive_record_count']:,} "
        "translated records with adaptive renderer-aware wrapping and "
        f"{coverage['fixed_record_count']:,} translated records with explicit "
        "fixed-layout ownership. "
        f"{coverage['anchor_record_count']:,} standalone dialogue-anchor "
        "records are rendered as one blank cell; no translated record is "
        "undeclared.\n\n"
        f"PART3B_ contains {coverage['part3b_translated_record_count']:,} "
        f"translated records. Retail records {preserved_indexes} remain "
        "retail-preserved without translation or reflow because they are "
        "blank/punctuation-only window records.\n\n"
        "Static previews and measurements do not prove runtime correctness. Manual "
        "playtesting remains the final release gate, especially dialogue formatting.\n"
    )


def _chapter_names(sources: Path = SOURCES) -> tuple[str, ...]:
    """Return canonical chapter names in their declared build order."""
    index = load_json_object(sources / "index.json")
    chapters = index.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("canonical source index has no chapters list")
    names: list[str] = []
    for item in chapters:
        if not isinstance(item, dict) or not isinstance(item.get("chapter"), str):
            raise ValueError("canonical source index contains an invalid chapter entry")
        names.append(item["chapter"])
    if len(names) != len(set(names)):
        raise ValueError("canonical source index repeats a chapter")
    return tuple(names)


def _run_input_manifest(
    track1: Path,
    track2: Path,
    build_root: Path,
    basename: str,
) -> dict[str, object]:
    """Fingerprint every declared source and prepared Japanese build fixture."""
    project_manifest = load_json_object(WORKSPACE / "nostalgia1907.project.json")
    translation = project_manifest.get("translation")
    baseline = (
        translation.get("validated_baseline") if isinstance(translation, dict) else None
    )
    profile = {
        "name": "clean-rebuild-single-run",
        "validated_architectural_baseline": baseline,
        "basename": basename,
        "chapter_count": len(_chapter_names()),
    }
    command = [
        "python",
        "-m",
        "work.clean_rebuild.rebuild",
        "<ORIGINAL_TRACK1>",
        "<ORIGINAL_TRACK2>",
        "--runs-root",
        "<RUNS_ROOT>",
        "--delivery-root",
        "<DELIVERY_ROOT>",
        "--basename",
        basename,
    ]
    bindings = collect_build_bindings(
        WORKSPACE,
        HERE,
        build_root,
        PRODUCTION_MODULES,
    )
    return create_input_manifest(
        bindings,
        track1=track1,
        track2=track2,
        build_profile=profile,
        command=command,
    )


def _build_once(
    track1: Path,
    track2: Path,
    build_root: Path,
    product_root: Path,
    basename: str,
) -> dict[str, object]:
    """Perform one complete build and bind its report to inputs and outputs.

    Both output roots must be absent or empty. Every expected artifact is named
    explicitly, hashed immediately after regression, and rehashed before the
    reports are written. A modified, missing, or unexpected product artifact
    therefore cannot be presented as current verification evidence.
    """
    _ensure_empty(build_root)
    _ensure_empty(product_root)
    prepare_retail(track1, build_root)
    input_manifest = _run_input_manifest(track1, track2, build_root, basename)
    build_mes_set(build_root)
    build_archives(build_root)

    retail_main = build_root / "retail_files" / "MAIN.BIN"
    patched_main = build_root / "MAIN.BIN"
    patched_main.write_bytes(patch_main(retail_main.read_bytes()))

    index = load_json_object(SOURCES / "index.json")
    replacements = {
        f"{item['chapter']}.LZ": build_root / "archives" / f"{item['chapter']}.LZ"
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
    iso_to_raw_fixed(
        track1,
        build_root / "translated.iso",
        output_track1,
        trust_template_checksums=True,
    )
    shutil.copyfile(track2, output_track2)
    write_two_track_cue(output_cue, output_track1, output_track2)
    verification = validate_build(build_root, product_root, track1, track2, basename)

    chapters = _chapter_names()
    assert_exact_managed_inventory(
        build_root,
        product_root,
        basename,
        chapters,
    )
    artifacts = expected_build_artifacts(
        build_root,
        product_root,
        basename,
        chapters,
    )
    generated_snapshot = snapshot_artifacts(artifacts)
    return write_bound_verification(
        product_root,
        input_manifest=input_manifest,
        artifact_paths=artifacts,
        generated_snapshot=generated_snapshot,
        verification=verification,
        manifest_name="verification_manifest.json",
        report_name="verification.json",
        report_kind="clean-rebuild-run",
        explanation=(
            "This report is bound to the exact canonical sources, Japanese retail "
            "fixtures, production and verification code, configuration, original "
            "track hashes, normalized build command, runtime identity, and direct "
            "hashes of every expected artifact from this run."
        ),
    )


def _manifest(
    build_root: Path,
    product_root: Path,
    basename: str,
) -> dict[str, str]:
    """Hash the explicit artifact contract for one completed clean run."""
    artifacts = expected_build_artifacts(
        build_root,
        product_root,
        basename,
        _chapter_names(),
    )
    return {
        str(item["path"]): str(item["sha256"]) for item in snapshot_artifacts(artifacts)
    }


# Two-run determinism proof and publication.


def rebuild(
    track1: Path,
    track2: Path,
    runs_root: Path,
    delivery_root: Path,
    basename: str,
) -> dict[str, object]:
    """Build twice, prove byte identity, and publish one fresh BIN/CUE set.

    Args:
        track1: Exact original Japanese MODE1/2352 data track.
        track2: Exact original retail audio track.
        runs_root: Fresh parent for independent ``run_a`` and ``run_b`` trees.
        delivery_root: Absent or empty release destination.
        basename: Safe artifact stem supplied by higher-level orchestration.

    Returns:
        Final two-run verification report and deterministic artifact hashes.

    Raises:
        ValueError: If any input, build, regression, independence, directory,
            or byte-identity invariant fails.

    Side Effects:
        Creates two full staging builds, publishes run A's BIN/CUE only after
        equality is proven, and writes final verification and test notes.
        Existing non-empty directories are never cleaned or overwritten.
    """
    basename = _validate_basename(basename)
    coverage = _canonical_coverage()
    run_a_build = runs_root / "run_a" / "build"
    run_a_product = runs_root / "run_a" / "product"
    run_b_build = runs_root / "run_b" / "build"
    run_b_product = runs_root / "run_b" / "product"
    first = _build_once(track1, track2, run_a_build, run_a_product, basename)
    second = _build_once(track1, track2, run_b_build, run_b_product, basename)
    first_fingerprint = first["provenance"]["aggregate_input_fingerprint"]
    second_fingerprint = second["provenance"]["aggregate_input_fingerprint"]
    if first_fingerprint != second_fingerprint:
        raise ValueError(
            "two clean builds did not use the same aggregate input fingerprint"
        )
    manifest_a = _manifest(run_a_build, run_a_product, basename)
    manifest_b = _manifest(run_b_build, run_b_product, basename)
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
    delivery_artifacts = expected_delivery_artifacts(delivery_root, basename)
    delivery_snapshot = snapshot_artifacts(delivery_artifacts)
    run_manifest = load_json_object(run_a_product / "verification_manifest.json")
    report = {
        "status": "PASS",
        "pipeline": "retail Japanese Track 1 -> clean extraction -> canonical translation -> fixed extents -> BIN/CUE",
        "canonical_coverage": coverage,
        "two_clean_builds_byte_identical": True,
        "two_clean_builds_same_input_fingerprint": True,
        "artifact_count_compared": len(manifest_a),
        "verification": first,
        "second_verification": second,
        "artifact_sha256": manifest_a,
    }
    report = write_bound_verification(
        delivery_root,
        input_manifest=run_manifest["input_manifest"],
        artifact_paths=delivery_artifacts,
        generated_snapshot=delivery_snapshot,
        verification=report,
        manifest_name="final_verification_manifest.json",
        report_name="final_verification.json",
        report_kind="clean-rebuild-delivery",
        explanation=(
            "This final report rehashes the three delivered game artifacts and "
            "binds them to the same aggregate input fingerprint proven by both "
            "independent clean build runs."
        ),
    )
    notes = _render_test_notes(coverage)
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

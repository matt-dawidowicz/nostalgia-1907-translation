#!/usr/bin/env python3
"""Create cryptographic input/output bindings for clean Nostalgia 1907 runs.

The module inventories only declared, output-relevant inputs. Every input and
artifact receives a normalized logical path, byte size, and SHA-256 digest. A
canonical JSON serialization of the complete input inventory, build profile,
normalized command, and runtime identity produces one stable aggregate input
fingerprint.

Reports are written only after generated files are snapshotted and rehashed.
Missing, changed, or unexpected managed artifacts abort reporting, so an old
product cannot be presented as evidence from the current run. This module does
not build game data and never changes canonical translation sources.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .source_json import load_json_object

SCHEMA_VERSION = 1
INPUT_KIND = "nostalgia1907-input-manifest"
BOUND_KIND = "nostalgia1907-bound-verification"
VERIFICATION_MODULES = (
    "translation_formatter.py",
    "translation_validation.py",
    "translation_audit.py",
    "bomb_audit.py",
    "export_bilingual_comparison.py",
    "export_fixed_layout_review.py",
)
CONFIGURATION_FILES = (
    "font_patterns.json",
    "script_layout_rules.json",
    "translation_glossary.json",
    "translation_repairs.json",
    "translation_exemptions.json",
    "bomb_semantics.json",
)


@dataclass(frozen=True, slots=True)
class FileBinding:
    """Describe one declared file by category, logical path, and disk path."""

    group: str
    logical_path: str
    path: Path


def sha256_file(path: Path) -> str:
    """Return an uppercase SHA-256 digest without loading a whole file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one JSON-compatible value for stable aggregate hashing."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _aggregate_fingerprint(value: object) -> str:
    """Return an uppercase SHA-256 over canonical JSON bytes."""
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest().upper()


def _logical_path(value: str) -> str:
    """Validate one normalized, relative POSIX manifest path."""
    if "\\" in value:
        raise ValueError(f"logical path uses a backslash: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(
            f"logical path is not normalized and relative: {value!r}"
        )
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError(f"logical path is not normalized: {value!r}")
    return normalized


def _write_json_lf(path: Path, payload: object) -> None:
    """Write indented UTF-8 JSON with explicit LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def runtime_environment(
    dependency_names: Sequence[str] = (),
) -> dict[str, object]:
    """Record runtime versions that can affect production or evidence bytes."""
    dependencies: list[dict[str, str]] = []
    for name in sorted(set(dependency_names), key=str.casefold):
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = "NOT-INSTALLED"
        dependencies.append({"name": name, "version": version})
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "cache_tag": sys.implementation.cache_tag,
            "byteorder": sys.byteorder,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "libraries": {
            "zlib_compile_version": zlib.ZLIB_VERSION,
            "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        },
        "output_affecting_dependencies": dependencies,
    }


def _file_entry(binding: FileBinding) -> dict[str, object]:
    """Hash one declared binding into a machine-readable manifest entry."""
    logical = _logical_path(binding.logical_path)
    if not binding.group or binding.group.strip() != binding.group:
        raise ValueError(f"invalid input group name: {binding.group!r}")
    if not binding.path.is_file():
        raise ValueError(
            f"manifest input is missing: {logical} -> {binding.path}"
        )
    return {
        "group": binding.group,
        "path": logical,
        "size": binding.path.stat().st_size,
        "sha256": sha256_file(binding.path),
    }


def _input_core(manifest: Mapping[str, object]) -> dict[str, object]:
    """Return the exact input-manifest fields covered by its fingerprint."""
    return {
        "schema_version": manifest.get("schema_version"),
        "kind": manifest.get("kind"),
        "build_profile": manifest.get("build_profile"),
        "command": manifest.get("command"),
        "runtime": manifest.get("runtime"),
        "inputs": manifest.get("inputs"),
    }


def create_input_manifest(
    bindings: Sequence[FileBinding],
    *,
    track1: Path,
    track2: Path,
    build_profile: Mapping[str, object],
    command: Sequence[str],
    runtime: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Create a stable fingerprint from explicit sources, code, and disc inputs.

    Files outside ``bindings`` and the two original-track arguments are
    intentionally ignored. This allowlist is why scratch logs and unrelated
    workspace files can change without changing the release fingerprint.
    """
    declared = list(bindings)
    declared.extend(
        (
            FileBinding(
                "original_disc_inputs",
                "inputs/original_track1.bin",
                track1,
            ),
            FileBinding(
                "original_disc_inputs",
                "inputs/original_track2.bin",
                track2,
            ),
        )
    )
    if not declared:
        raise ValueError("input manifest requires declared files")
    seen: set[str] = set()
    entries: list[dict[str, object]] = []
    for binding in sorted(
        declared,
        key=lambda item: (item.group, item.logical_path),
    ):
        logical = _logical_path(binding.logical_path)
        if logical in seen:
            raise ValueError(f"input manifest repeats logical path: {logical}")
        seen.add(logical)
        entries.append(_file_entry(binding))
    core: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": INPUT_KIND,
        "build_profile": dict(build_profile),
        "command": list(command),
        "runtime": dict(runtime or runtime_environment()),
        "inputs": entries,
    }
    manifest = dict(core)
    manifest["aggregate_input_fingerprint"] = _aggregate_fingerprint(core)
    manifest["input_file_count"] = len(entries)
    manifest["input_group_count"] = len(
        {str(entry["group"]) for entry in entries}
    )
    return manifest


def validate_input_manifest(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Check one input manifest's schema, counts, and aggregate fingerprint."""
    failures: list[str] = []
    inputs = manifest.get("inputs")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        failures.append("unsupported input-manifest schema")
    if manifest.get("kind") != INPUT_KIND:
        failures.append("input-manifest kind is invalid")
    if not isinstance(inputs, list):
        failures.append("input manifest has no inputs list")
        inputs = []
    paths: list[str] = []
    groups: set[str] = set()
    for entry in inputs:
        if not isinstance(entry, dict):
            failures.append("input manifest contains a non-object entry")
            continue
        try:
            paths.append(_logical_path(str(entry.get("path", ""))))
        except ValueError as error:
            failures.append(str(error))
        group = entry.get("group")
        if not isinstance(group, str) or not group:
            failures.append("input manifest contains an invalid group")
        else:
            groups.add(group)
        size = entry.get("size")
        if not isinstance(size, int) or size < 0:
            failures.append("input manifest contains an invalid byte size")
        digest = entry.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789ABCDEF" for character in digest)
        ):
            failures.append(
                f"input manifest contains an invalid SHA-256: {digest!r}"
            )
    sortable = [
        (str(entry.get("group", "")), str(entry.get("path", "")))
        for entry in inputs
        if isinstance(entry, dict)
    ]
    if sortable != sorted(sortable):
        failures.append(
            "input manifest entries are not in stable group/path order"
        )
    if len(paths) != len(set(paths)):
        failures.append("input manifest repeats logical paths")
    if manifest.get("input_file_count") != len(inputs):
        failures.append("input-manifest file count is stale")
    if manifest.get("input_group_count") != len(groups):
        failures.append("input-manifest group count is stale")
    expected = _aggregate_fingerprint(_input_core(manifest))
    if manifest.get("aggregate_input_fingerprint") != expected:
        failures.append("aggregate input fingerprint is stale")
    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "aggregate_input_fingerprint": manifest.get(
            "aggregate_input_fingerprint"
        ),
        "input_file_count": len(inputs),
    }


def _safe_chapter_list(index_path: Path) -> list[tuple[str, str]]:
    """Load validated ``(chapter, source JSON)`` pairs from the source index."""
    index = load_json_object(index_path)
    items = index.get("chapters")
    if not isinstance(items, list):
        raise ValueError("canonical source index has no chapters list")
    chapters: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(
                "canonical source index contains a non-object chapter"
            )
        chapter = item.get("chapter")
        source_name = item.get("source")
        if not isinstance(chapter, str) or not isinstance(source_name, str):
            raise ValueError(
                "canonical source index contains an invalid chapter"
            )
        if Path(source_name).name != source_name or not source_name.endswith(
            ".json"
        ):
            raise ValueError(f"unsafe canonical source path: {source_name!r}")
        chapters.append((chapter, source_name))
    if len(chapters) != len({chapter for chapter, _ in chapters}):
        raise ValueError("canonical source index repeats a chapter")
    return chapters


def collect_build_bindings(
    project_root: Path,
    clean_root: Path,
    build_root: Path,
    production_modules: Sequence[str],
) -> list[FileBinding]:
    """Collect sources, fresh Japanese fixtures, code, rules, and config.

    ``build_root`` must be the current run immediately after ``prepare_retail``.
    Only the known prepared-retail contract is included; generated translated
    MES/LZ/ISO/BIN artifacts are bound separately as outputs.
    """
    source_root = clean_root / "sources"
    index_path = source_root / "index.json"
    chapters = _safe_chapter_list(index_path)
    bindings: list[FileBinding] = [
        FileBinding(
            "canonical_translation_sources",
            "work/clean_rebuild/sources/index.json",
            index_path,
        )
    ]
    for chapter, source_name in chapters:
        bindings.append(
            FileBinding(
                "canonical_translation_sources",
                f"work/clean_rebuild/sources/{source_name}",
                source_root / source_name,
            )
        )
        bindings.extend(
            (
                FileBinding(
                    "japanese_source_fixtures",
                    f"prepared_retail/retail_archives/{chapter}.LZ",
                    build_root / "retail_archives" / f"{chapter}.LZ",
                ),
                FileBinding(
                    "japanese_source_fixtures",
                    f"prepared_retail/retail_unpacked/{chapter}/{chapter}.MES",
                    build_root
                    / "retail_unpacked"
                    / chapter
                    / f"{chapter}.MES",
                ),
                FileBinding(
                    "japanese_source_fixtures",
                    f"prepared_retail/retail_unpacked/{chapter}/{chapter}.SCN",
                    build_root
                    / "retail_unpacked"
                    / chapter
                    / f"{chapter}.SCN",
                ),
            )
        )
    for relative in (
        "retail.iso",
        "retail_report.json",
        "retail_files/FIX_CODE.FNT",
        "retail_files/MAIN.BIN",
    ):
        bindings.append(
            FileBinding(
                "japanese_source_fixtures",
                f"prepared_retail/{relative}",
                build_root / relative,
            )
        )
    for name in production_modules:
        if Path(name).name != name or not name.endswith(".py"):
            raise ValueError(f"invalid production module name: {name!r}")
        bindings.append(
            FileBinding(
                "production_python",
                f"work/clean_rebuild/{name}",
                clean_root / name,
            )
        )
    for name in VERIFICATION_MODULES:
        if name in production_modules:
            continue
        bindings.append(
            FileBinding(
                "verification_and_layout_python",
                f"work/clean_rebuild/{name}",
                clean_root / name,
            )
        )
    for name in CONFIGURATION_FILES:
        bindings.append(
            FileBinding(
                "layout_glossary_overrides_and_configuration",
                f"work/clean_rebuild/{name}",
                clean_root / name,
            )
        )
    for name in ("nostalgia1907.py", "nostalgia1907.project.json"):
        bindings.append(
            FileBinding(
                "operator_and_project_configuration",
                name,
                project_root / name,
            )
        )
    return bindings


def expected_build_artifacts(
    build_root: Path,
    product_root: Path,
    basename: str,
    chapters: Sequence[str],
) -> dict[str, Path]:
    """Return the exact generated run artifacts that a report must hash."""
    artifacts: dict[str, Path] = {
        "build/FIX_CODE.FNT": build_root / "FIX_CODE.FNT",
        "build/MAIN.BIN": build_root / "MAIN.BIN",
        "build/translated.iso": build_root / "translated.iso",
        "build/reports/retail_report.json": build_root / "retail_report.json",
        "build/reports/mes_report.json": build_root / "mes_report.json",
        "build/reports/archive_report.json": build_root
        / "archive_report.json",
        "build/reports/iso_patch_report.json": build_root
        / "iso_patch_report.json",
        f"product/{basename}_Track1.bin": product_root
        / f"{basename}_Track1.bin",
        f"product/{basename}_Track2.bin": product_root
        / f"{basename}_Track2.bin",
        f"product/{basename}.cue": product_root / f"{basename}.cue",
    }
    for chapter in chapters:
        artifacts[f"build/mes/{chapter}.MES"] = (
            build_root / "mes" / f"{chapter}.MES"
        )
        artifacts[f"build/archives/{chapter}.LZ"] = (
            build_root / "archives" / f"{chapter}.LZ"
        )
    return dict(sorted(artifacts.items()))


def expected_delivery_artifacts(
    delivery_root: Path,
    basename: str,
) -> dict[str, Path]:
    """Return the exact three game artifacts published by a clean release."""
    return {
        f"delivery/{basename}.cue": delivery_root / f"{basename}.cue",
        f"delivery/{basename}_Track1.bin": delivery_root
        / f"{basename}_Track1.bin",
        f"delivery/{basename}_Track2.bin": delivery_root
        / f"{basename}_Track2.bin",
    }


def _directory_files(root: Path) -> set[str]:
    """Return relative POSIX file names below one directory."""
    if not root.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def assert_exact_managed_inventory(
    build_root: Path,
    product_root: Path,
    basename: str,
    chapters: Sequence[str],
) -> None:
    """Reject missing or stale files in the build's managed output locations."""
    expected_mes = {f"{chapter}.MES" for chapter in chapters}
    expected_archives = {f"{chapter}.LZ" for chapter in chapters}
    expected_product = {
        f"{basename}_Track1.bin",
        f"{basename}_Track2.bin",
        f"{basename}.cue",
    }
    checks = (
        ("MES", build_root / "mes", expected_mes),
        ("archive", build_root / "archives", expected_archives),
        ("product", product_root, expected_product),
    )
    problems: list[str] = []
    for label, root, expected in checks:
        actual = _directory_files(root)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing:
            problems.append(f"{label} missing {missing}")
        if unexpected:
            problems.append(f"{label} unexpected {unexpected}")
    required = {
        "FIX_CODE.FNT": build_root / "FIX_CODE.FNT",
        "MAIN.BIN": build_root / "MAIN.BIN",
        "translated.iso": build_root / "translated.iso",
        "retail_report.json": build_root / "retail_report.json",
        "mes_report.json": build_root / "mes_report.json",
        "archive_report.json": build_root / "archive_report.json",
        "iso_patch_report.json": build_root / "iso_patch_report.json",
    }
    missing_required = sorted(
        logical for logical, path in required.items() if not path.is_file()
    )
    if missing_required:
        problems.append(f"build missing {missing_required}")
    if problems:
        raise ValueError(
            "managed artifact inventory failed: " + "; ".join(problems)
        )


def snapshot_artifacts(
    artifacts: Mapping[str, Path],
) -> list[dict[str, object]]:
    """Hash an explicit generated-artifact mapping in stable logical order."""
    if not artifacts:
        raise ValueError("artifact snapshot requires at least one path")
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for logical, path in sorted(artifacts.items()):
        logical = _logical_path(logical)
        if logical in seen:
            raise ValueError(
                f"artifact snapshot repeats logical path: {logical}"
            )
        seen.add(logical)
        if not path.is_file():
            raise ValueError(
                f"generated artifact is missing: {logical} -> {path}"
            )
        entries.append(
            {
                "path": logical,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def _bound_core(manifest: Mapping[str, object]) -> dict[str, object]:
    """Return the exact bound-manifest fields covered by its fingerprint."""
    return {
        "schema_version": manifest.get("schema_version"),
        "kind": manifest.get("kind"),
        "report_kind": manifest.get("report_kind"),
        "aggregate_input_fingerprint": manifest.get(
            "aggregate_input_fingerprint"
        ),
        "input_manifest": manifest.get("input_manifest"),
        "outputs": manifest.get("outputs"),
    }


def write_bound_verification(
    output_root: Path,
    *,
    input_manifest: Mapping[str, object],
    artifact_paths: Mapping[str, Path],
    generated_snapshot: Sequence[Mapping[str, object]],
    verification: Mapping[str, object],
    manifest_name: str,
    report_name: str,
    report_kind: str,
    explanation: str,
) -> dict[str, object]:
    """Write machine and human reports only for exact current artifacts."""
    input_check = validate_input_manifest(input_manifest)
    if input_check["status"] != "PASS":
        raise ValueError(
            "input manifest is invalid: " + "; ".join(input_check["failures"])
        )
    expected_snapshot = [dict(item) for item in generated_snapshot]
    if snapshot_artifacts(artifact_paths) != expected_snapshot:
        raise ValueError("generated artifact snapshot is stale")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / manifest_name
    report_path = output_root / report_name
    if manifest_path.exists() or report_path.exists():
        raise ValueError(
            "refusing to overwrite an existing verification report"
        )
    core: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": BOUND_KIND,
        "report_kind": report_kind,
        "aggregate_input_fingerprint": input_manifest[
            "aggregate_input_fingerprint"
        ],
        "input_manifest": dict(input_manifest),
        "outputs": expected_snapshot,
    }
    machine = dict(core)
    machine["output_fingerprint"] = _aggregate_fingerprint(core)
    _write_json_lf(manifest_path, machine)
    if snapshot_artifacts(artifact_paths) != expected_snapshot:
        manifest_path.unlink(missing_ok=True)
        raise ValueError(
            "generated artifact snapshot is stale after manifest write"
        )
    report = dict(verification)
    report["provenance"] = {
        "explanation": explanation,
        "aggregate_input_fingerprint": input_manifest[
            "aggregate_input_fingerprint"
        ],
        "input_file_count": input_manifest["input_file_count"],
        "input_group_count": input_manifest["input_group_count"],
        "build_profile": input_manifest["build_profile"],
        "command": input_manifest["command"],
        "runtime": input_manifest["runtime"],
        "machine_manifest": {
            "filename": manifest_name,
            "size": manifest_path.stat().st_size,
            "sha256": sha256_file(manifest_path),
            "output_fingerprint": machine["output_fingerprint"],
        },
        "outputs": expected_snapshot,
    }
    _write_json_lf(report_path, report)
    if snapshot_artifacts(artifact_paths) != expected_snapshot:
        report_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise ValueError(
            "generated artifact snapshot is stale after report write"
        )
    return report


def validate_bound_verification(
    manifest_path: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, object]:
    """Reopen a bound manifest and verify its input and current output hashes."""
    failures: list[str] = []
    try:
        manifest = load_json_object(manifest_path)
    except (OSError, ValueError) as error:
        return {
            "status": "FAIL",
            "failure_count": 1,
            "failures": [f"cannot read bound verification manifest: {error}"],
        }
    if manifest.get("schema_version") != SCHEMA_VERSION:
        failures.append("unsupported bound-manifest schema")
    if manifest.get("kind") != BOUND_KIND:
        failures.append("bound-manifest kind is invalid")
    input_manifest = manifest.get("input_manifest")
    if not isinstance(input_manifest, dict):
        failures.append("bound manifest has no input manifest")
    else:
        input_check = validate_input_manifest(input_manifest)
        failures.extend(
            f"input: {failure}" for failure in input_check["failures"]
        )
        if manifest.get("aggregate_input_fingerprint") != input_manifest.get(
            "aggregate_input_fingerprint"
        ):
            failures.append("bound and embedded input fingerprints differ")
    expected_output_fingerprint = _aggregate_fingerprint(_bound_core(manifest))
    if manifest.get("output_fingerprint") != expected_output_fingerprint:
        failures.append("bound output fingerprint is stale")
    try:
        current = snapshot_artifacts(artifact_paths)
    except ValueError as error:
        failures.append(str(error))
        current = []
    if current != manifest.get("outputs"):
        failures.append(
            "bound outputs differ from current generated artifacts"
        )
    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "aggregate_input_fingerprint": manifest.get(
            "aggregate_input_fingerprint"
        ),
        "output_fingerprint": manifest.get("output_fingerprint"),
        "output_count": len(current),
    }

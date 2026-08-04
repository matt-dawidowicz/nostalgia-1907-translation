#!/usr/bin/env python3
"""Safe operator interface for the Nostalgia 1907 translation toolchain.

The command handlers in this module deliberately contain little binary-format
logic. They resolve the project/configuration contract, verify guarded inputs,
and compose the focused modules under ``work/clean_rebuild``. This keeps one
supported workflow for translators while leaving the lower-level modules
independently readable for reverse-engineering work.

Command flow
------------
``doctor`` checks the environment and retail inputs. ``prepare`` creates a
hash-locked, ignored retail reference. ``edit`` changes canonical English by
stable record ID. ``compare`` and ``validate`` produce review evidence.
``build`` performs full validation, delegates the deterministic two-run clean
build, and defaults to a second deterministic North American region stage.

Safety model
------------
Paths and hashes come from ``nostalgia1907.project.json`` plus an optional
untracked local configuration. Build outputs must be fresh and non-overlapping;
a normal build validates before writing. Expected operator mistakes become
short :class:`ToolError` messages instead of partial recovery or silent
fallbacks.

See ``docs/ARCHITECTURE.md`` and ``docs/DEVELOPMENT.md`` for the production
graph, generated reports, and lower-level module ownership.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


MANIFEST_NAME = "nostalgia1907.project.json"
LOCAL_CONFIG_NAME = "nostalgia1907.local.json"
RELEASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DEFAULT_BUILD_BASENAME = "Nostalgia1907_CleanRebuild"
DEFAULT_RUNS_DIRECTORY = "runs_current"


class ToolError(RuntimeError):
    """Report an actionable operator error without a Python traceback."""


# Project discovery, configuration, and immutable input guards.


def find_project_root(explicit: Path | None = None) -> Path:
    """Find the checkout that owns the project manifest."""
    candidates = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    candidates.extend((Path.cwd(), Path(__file__).resolve().parent))
    visited: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        for directory in (candidate, *candidate.parents):
            if directory in visited:
                continue
            visited.add(directory)
            if (directory / MANIFEST_NAME).is_file():
                return directory
    raise ToolError(
        f"could not find {MANIFEST_NAME}; run from the repository or use --project-root"
    )


def load_manifest(root: Path) -> dict[str, Any]:
    """Load and minimally validate the frozen project contract.

    Args:
        root: Checkout root containing ``nostalgia1907.project.json``.

    Returns:
        Parsed schema-version-1 manifest.

    Raises:
        ToolError: If the file is missing, invalid JSON, or uses an unsupported
            schema. Individual nested contracts are validated at their point of
            use so diagnostics retain operator context.
    """
    path = root / MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ToolError(f"missing project manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ToolError(f"invalid project manifest: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise ToolError(
            f"unsupported project manifest schema: {payload.get('schema_version')}"
        )
    return payload


def load_local_config(root: Path) -> dict[str, Any]:
    """Load optional untracked machine-specific paths."""
    path = root / LOCAL_CONFIG_NAME
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"invalid {LOCAL_CONFIG_NAME}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ToolError(f"{LOCAL_CONFIG_NAME} must contain a JSON object")
    return payload


def rooted(root: Path, value: str | Path) -> Path:
    """Resolve a project-relative or absolute path."""
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def sha256(path: Path) -> str:
    """Hash a file without reading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def normalized_text_sha256(path: Path) -> str:
    """Hash text bytes after canonicalizing CRLF and CR line endings to LF."""
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest().upper()


def default_input_path(
    root: Path,
    manifest: dict[str, Any],
    local: dict[str, Any],
    key: str,
    override: Path | None,
) -> Path:
    """Resolve CLI override, local config, or conventional retail-input path."""
    if override is not None:
        return override.expanduser().resolve()
    if local.get(key):
        return rooted(root, local[key])
    spec = manifest["retail_inputs"][key]
    return rooted(root, manifest["paths"]["retail_input"]) / spec["filename"]


def file_check(
    name: str,
    path: Path,
    spec: dict[str, Any],
    *,
    required: bool,
) -> dict[str, Any]:
    """Return a machine-readable file existence, size, and hash check."""
    result: dict[str, Any] = {
        "name": name,
        "path": str(path),
        "required": required,
    }
    if not path.is_file():
        result.update(
            status="FAIL" if required else "SKIP",
            detail="file not found",
        )
        return result
    actual_size = path.stat().st_size
    expected_size = spec.get("size")
    if expected_size is not None and actual_size != expected_size:
        result.update(
            status="FAIL",
            detail=f"size mismatch: expected {expected_size}, got {actual_size}",
        )
        return result
    actual_hash = sha256(path)
    expected_hash = str(spec["sha256"]).upper()
    if actual_hash != expected_hash:
        result.update(
            status="FAIL",
            detail=f"SHA-256 mismatch: expected {expected_hash}, got {actual_hash}",
        )
        return result
    result.update(
        status="PASS", detail=f"verified {actual_size} bytes", sha256=actual_hash
    )
    return result


def require_file(name: str, path: Path, spec: dict[str, Any]) -> None:
    """Raise an actionable error unless a guarded input is exact."""
    result = file_check(name, path, spec, required=True)
    if result["status"] != "PASS":
        raise ToolError(f"{name}: {result['detail']} ({path})")


# Read-only readiness checks. Each check returns the same status/detail/path
# shape so ``doctor --json`` remains useful to scripts as well as humans.


def source_index_check(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate the tracked canonical chapter inventory without retail data.

    The normalized-text hash permits platform line endings but no semantic JSON
    change. Chapter and record totals are cross-checked independently.

    Returns:
        A doctor-compatible status mapping; ordinary mismatches are reported,
        not raised.
    """
    clean = rooted(root, manifest["paths"]["clean_rebuild"])
    path = clean / "sources" / "index.json"
    if not path.is_file():
        return {
            "name": "canonical source index",
            "status": "FAIL",
            "required": True,
            "path": str(path),
            "detail": "file not found",
        }
    expected_hash = manifest["translation"]["source_index_text_sha256"]
    actual_hash = normalized_text_sha256(path)
    if actual_hash != expected_hash:
        return {
            "name": "canonical source index",
            "status": "FAIL",
            "required": True,
            "path": str(path),
            "detail": (
                "normalized-text SHA-256 mismatch: "
                f"expected {expected_hash}, got {actual_hash}"
            ),
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    chapter_count = payload.get("chapter_count")
    record_count = sum(
        item.get("record_count", 0) for item in payload.get("chapters", [])
    )
    expected_chapters = manifest["translation"]["chapter_count"]
    expected_records = manifest["translation"]["record_count"]
    if (chapter_count, record_count) != (expected_chapters, expected_records):
        return {
            "name": "canonical source index",
            "status": "FAIL",
            "required": True,
            "path": str(path),
            "detail": (
                f"inventory mismatch: expected {expected_chapters}/{expected_records}, "
                f"got {chapter_count}/{record_count}"
            ),
        }
    return {
        "name": "canonical source index",
        "status": "PASS",
        "required": True,
        "path": str(path),
        "detail": f"{chapter_count} chapters, {record_count} records",
        "sha256": actual_hash,
    }


def retail_reference_check(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Check whether the prepared retail tree matches frozen input contracts.

    This inexpensive readiness check trusts only the preparation report's
    Track 1 and logical ISO sizes/hashes. Deeper member validation belongs to
    preparation and the downstream retail-backed gates.
    """
    reference = rooted(root, manifest["paths"]["retail_reference"])
    report_path = reference / "retail_report.json"
    if not report_path.is_file():
        return {
            "name": "prepared retail reference",
            "status": "WARN",
            "required": False,
            "path": str(reference),
            "detail": "not prepared; run `python nostalgia1907.py prepare`",
        }
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "name": "prepared retail reference",
            "status": "FAIL",
            "required": True,
            "path": str(report_path),
            "detail": f"invalid report: {exc}",
        }
    retail = manifest["retail_inputs"]
    expected = (
        retail["track1"]["size"],
        retail["track1"]["sha256"],
        retail["retail_iso"]["size"],
        retail["retail_iso"]["sha256"],
    )
    actual = (
        report.get("track1_size"),
        report.get("track1_sha256"),
        report.get("iso_size"),
        report.get("iso_sha256"),
    )
    if actual != expected:
        return {
            "name": "prepared retail reference",
            "status": "FAIL",
            "required": True,
            "path": str(report_path),
            "detail": "report does not match the frozen retail input/ISO contract",
        }
    return {
        "name": "prepared retail reference",
        "status": "PASS",
        "required": False,
        "path": str(reference),
        "detail": "hash-locked retail reference is ready",
    }


def doctor_report(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    """Inspect whether the checkout is ready to prepare, validate, and build.

    Required Python, canonical-source, and original-track checks determine
    the overall status. Prepared retail data, BIOS, and FFmpeg are
    reported according to whether their optional workflows were configured.

    Returns:
        A machine-readable report without modifying the checkout.
    """
    manifest = load_manifest(root)
    local = load_local_config(root)
    minimum = tuple(int(part) for part in manifest["tool"]["python_minimum"].split("."))
    checks: list[dict[str, Any]] = [
        {
            "name": "Python",
            "status": "PASS" if sys.version_info[:2] >= minimum else "FAIL",
            "required": True,
            "path": sys.executable,
            "detail": (
                f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; "
                f"minimum {manifest['tool']['python_minimum']}"
            ),
        },
        source_index_check(root, manifest),
    ]
    for key, label in (
        ("track1", "original Japanese Track 1"),
        ("track2", "original Japanese Track 2"),
    ):
        path = default_input_path(root, manifest, local, key, getattr(args, key))
        checks.append(
            file_check(label, path, manifest["retail_inputs"][key], required=True)
        )
    checks.append(retail_reference_check(root, manifest))

    bios_value = args.us_bios or local.get("us_bios")
    if bios_value:
        bios_path = rooted(root, bios_value)
        checks.append(
            file_check(
                "optional U.S. BIOS",
                bios_path,
                manifest["us_bios_test"]["bios"],
                required=False,
            )
        )
    else:
        checks.append(
            {
                "name": "optional U.S. BIOS",
                "status": "SKIP",
                "required": False,
                "path": "",
                "detail": f"not configured in {LOCAL_CONFIG_NAME}",
            }
        )

    ffmpeg_value = args.ffmpeg or local.get("ffmpeg") or shutil.which("ffmpeg")
    if ffmpeg_value:
        ffmpeg_path = rooted(root, ffmpeg_value)
        checks.append(
            {
                "name": "optional FFmpeg",
                "status": "PASS" if ffmpeg_path.is_file() else "WARN",
                "required": False,
                "path": str(ffmpeg_path),
                "detail": (
                    "available"
                    if ffmpeg_path.is_file()
                    else "configured path not found"
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "optional FFmpeg",
                "status": "SKIP",
                "required": False,
                "path": "",
                "detail": "needed only for English audio-review synthesis",
            }
        )

    failures = [check for check in checks if check["status"] == "FAIL"]
    warnings = [check for check in checks if check["status"] == "WARN"]
    return {
        "status": "FAIL" if failures else "PASS",
        "project_root": str(root),
        "tool_version": manifest["tool"]["version"],
        "validated_baseline": manifest["translation"]["validated_baseline"],
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "checks": checks,
    }


def print_doctor(report: dict[str, Any]) -> None:
    """Render the doctor report for a human operator."""
    print(
        f"Nostalgia 1907 tool {report['tool_version']} "
        f"(validated baseline {report['validated_baseline']})"
    )
    print(f"Project: {report['project_root']}")
    for check in report["checks"]:
        location = f" — {check['path']}" if check.get("path") else ""
        print(f"[{check['status']}] {check['name']}: {check['detail']}{location}")
    if report["status"] == "PASS":
        retail_ready = any(
            check["name"] == "prepared retail reference" and check["status"] == "PASS"
            for check in report["checks"]
        )
        if retail_ready:
            print("Ready to validate or build.")
        else:
            print(
                "Original inputs verified. Run `python nostalgia1907.py prepare` next."
            )
    else:
        print("Not ready. Resolve the failed required checks above.")


# Subprocess boundary. Lower-level scripts keep their native reports and exit
# codes; this layer adds only a readable stage label and a concise failure.


def run_command(command: Sequence[str], *, root: Path, label: str) -> None:
    """Run one existing project command and preserve its native output."""
    print(f"\n== {label} ==", flush=True)
    completed = subprocess.run(list(command), cwd=root, check=False)
    if completed.returncode:
        raise ToolError(f"{label} failed with exit code {completed.returncode}")


def run_script(root: Path, relative: str, *arguments: str, label: str) -> None:
    """Run an existing Python script under the current interpreter."""
    run_command(
        (sys.executable, str(rooted(root, relative)), *arguments),
        root=root,
        label=label,
    )


def require_retail_reference(root: Path, manifest: dict[str, Any]) -> Path:
    """Require the hash-locked prepared retail tree used by review tools."""
    result = retail_reference_check(root, manifest)
    if result["status"] != "PASS":
        raise ToolError(f"prepared retail reference is not ready: {result['detail']}")
    return rooted(root, manifest["paths"]["retail_reference"])


# Supported operator command handlers.


def command_doctor(root: Path, args: argparse.Namespace) -> int:
    """Run environment and input diagnostics."""
    report = doctor_report(root, args)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_doctor(report)
    return 0 if report["status"] == "PASS" else 1


def command_prepare(root: Path, args: argparse.Namespace) -> int:
    """Prepare and recheck the guarded retail reference from original Track 1.

    The complete input is size/hash checked before the lower-level extraction
    command runs. A postcondition check then confirms the resulting report.

    Side Effects:
        Creates the ignored prepared-retail tree declared by the manifest.
    """
    manifest = load_manifest(root)
    local = load_local_config(root)
    track1 = default_input_path(root, manifest, local, "track1", args.track1)
    require_file(
        "original Japanese Track 1", track1, manifest["retail_inputs"]["track1"]
    )
    reference = rooted(root, manifest["paths"]["retail_reference"])
    run_script(
        root,
        "work/clean_rebuild/prepare_retail.py",
        str(track1),
        "--build-root",
        str(reference),
        label="Prepare retail reference",
    )
    result = retail_reference_check(root, manifest)
    if result["status"] != "PASS":
        raise ToolError(result["detail"])
    print(f"Prepared retail reference: {reference}")
    return 0


def command_edit(root: Path, args: argparse.Namespace) -> int:
    """Preview or apply canonical ID-keyed English wording changes.

    Preview mode writes nothing. Batch mode delegates one reviewed file.
    Single-record apply mode creates a temporary batch file, delegates the same
    atomic validator/writer, and removes the temporary file in ``finally``.
    """
    validate_edit_request(args)
    manifest = load_manifest(root)
    retail = require_retail_reference(root, manifest)
    formatter = "work/clean_rebuild/translation_formatter.py"
    if args.changes:
        run_script(
            root,
            formatter,
            "--retail-root",
            str(retail),
            "--changes",
            str(args.changes.expanduser().resolve()),
            label="Apply reviewed wording changes",
        )
        return 0
    if not args.apply:
        run_script(
            root,
            formatter,
            "--retail-root",
            str(retail),
            "--record",
            args.record,
            "--text",
            args.text,
            label="Preview wording change",
        )
        return 0
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="nostalgia1907-change-",
            delete=False,
        ) as handle:
            json.dump({"changes": {args.record: args.text}}, handle, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        run_script(
            root,
            formatter,
            "--retail-root",
            str(retail),
            "--changes",
            str(temporary),
            label="Apply wording change",
        )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return 0


def validate_edit_request(args: argparse.Namespace) -> None:
    """Reject incomplete or ambiguous edit command combinations."""
    if args.changes:
        if args.record or args.text is not None or args.apply:
            raise ToolError(
                "--changes cannot be combined with RECORD, --text, or --apply; "
                "a reviewed change file is applied as one validated batch"
            )
        return
    if not args.record or args.text is None:
        raise ToolError("edit requires RECORD and --text, or --changes FILE")


def comparison_paths(root: Path, manifest: dict[str, Any]) -> tuple[Path, Path]:
    """Return the comparison package root and its canonical JSON."""
    output = rooted(root, manifest["paths"]["comparison_output"])
    return output, output / "Nostalgia1907_Japanese_English_Comparison.json"


def operator_python_sources(root: Path, manifest: dict[str, Any]) -> list[Path]:
    """List project-owned Python sources without entering vendored local runtimes."""
    directories = (
        rooted(root, manifest["paths"]["clean_rebuild"]),
        root / "work" / "region_variant",
        root / "work" / "audio_localization",
        root / "tests",
    )
    sources = [root / "nostalgia1907.py"]
    for directory in directories:
        sources.extend(sorted(directory.glob("*.py")))
    return sources


def command_compare(root: Path, args: argparse.Namespace) -> int:
    """Regenerate the deterministic Japanese/English review package.

    A prepared retail reference is mandatory. The lower-level exporter owns
    alignment, metadata-free bitmap encoding, exact package inventory, and
    deterministic archive checks without a Pillow dependency.
    """
    manifest = load_manifest(root)
    retail = require_retail_reference(root, manifest)
    default_output, _ = comparison_paths(root, manifest)
    output = args.output.expanduser().resolve() if args.output else default_output
    run_script(
        root,
        "work/clean_rebuild/export_bilingual_comparison.py",
        "--retail-root",
        str(retail),
        "--output-root",
        str(output),
        label="Regenerate bilingual comparison package",
    )
    return 0


def command_validate(root: Path, args: argparse.Namespace) -> int:
    """Run static, audio, renderer, comparison, and semantic validation.

    Stages run sequentially so the first failing layer retains its native
    diagnostic. Comparison regeneration is the only material output unless the
    caller explicitly skips it; audit scripts may also refresh ignored reports.
    """
    manifest = load_manifest(root)
    retail = require_retail_reference(root, manifest)
    python_sources = operator_python_sources(root, manifest)
    run_command(
        (
            sys.executable,
            "-m",
            "py_compile",
            *(str(path) for path in python_sources),
        ),
        root=root,
        label="Python static compilation",
    )
    run_script(
        root,
        "work/audio_localization/test_audio_localization.py",
        label="Audio companion unit tests",
    )
    run_script(
        root,
        "work/clean_rebuild/translation_formatter.py",
        "--retail-root",
        str(retail),
        label="Renderer-aware layout audit",
    )
    run_script(
        root,
        "work/clean_rebuild/test_script_layout.py",
        "-v",
        label="Script layout tests",
    )
    _, comparison_json = comparison_paths(root, manifest)
    if not args.skip_comparison:
        command_compare(root, argparse.Namespace(output=None))
    validation_args = ["--comparison-json", str(comparison_json)]
    if args.skip_comparison:
        validation_args.append("--allow-missing-comparison")
    run_script(
        root,
        "work/clean_rebuild/translation_validation.py",
        *validation_args,
        label="Semantic and generated-artifact validation",
    )
    print("\nAll requested validation stages passed.")
    return 0


def release_basename(name: str | None) -> str:
    """Return the neutral basename or normalize an optional output label."""
    if name is None:
        return DEFAULT_BUILD_BASENAME
    if not RELEASE_RE.fullmatch(name):
        raise ToolError(
            "release name must start with a letter or digit and contain only "
            "letters, digits, period, underscore, or hyphen"
        )
    if name.startswith("Nostalgia1907_"):
        return name
    return f"{DEFAULT_BUILD_BASENAME}_{name}"


# Build-output guards are intentionally checked before the expensive
# validation/build stages and never delete or reuse existing artifacts.


def directory_state(path: Path) -> str:
    """Describe whether a planned build directory is safe to initialize."""
    if not path.exists():
        return "absent"
    if not path.is_dir():
        return "not-a-directory"
    return "non-empty" if next(path.iterdir(), None) is not None else "empty"


def require_fresh_build_directory(label: str, path: Path) -> None:
    """Require an absent or empty build directory without deleting anything."""
    state = directory_state(path)
    if state not in {"absent", "empty"}:
        raise ToolError(
            f"{label} must be absent or empty, but is {state}: {path}; "
            "choose a new path or move the existing artifacts"
        )


def require_separate_build_directories(runs: Path, delivery: Path) -> None:
    """Reject equal or nested run/delivery roots before a build starts."""
    if runs == delivery or runs in delivery.parents or delivery in runs.parents:
        raise ToolError(
            "runs root and delivery root must be separate, non-overlapping paths: "
            f"{runs} / {delivery}"
        )


def command_build(root: Path, args: argparse.Namespace) -> int:
    """Build a deterministic BIN/CUE for the selected console region.

    Exact input hashes and non-overlapping output roots are resolved before the
    dry-run boundary. A real build additionally requires fresh destinations,
    runs the complete validation gate, and delegates two-run byte-identity
    proof. North American builds then wrap that proven clean result twice and
    publish only the region-adjusted delivery.
    """
    manifest = load_manifest(root)
    local = load_local_config(root)
    track1 = default_input_path(root, manifest, local, "track1", args.track1)
    track2 = default_input_path(root, manifest, local, "track2", args.track2)
    require_file(
        "original Japanese Track 1", track1, manifest["retail_inputs"]["track1"]
    )
    require_file(
        "original Japanese Track 2", track2, manifest["retail_inputs"]["track2"]
    )
    region = getattr(args, "region", None) or manifest["build"]["default_region"]
    if region not in {"north-america", "japan"}:
        raise ToolError(f"unsupported build region: {region!r}")
    base_basename = release_basename(args.name)
    basename = (
        f"{base_basename}_NorthAmerica" if region == "north-america" else base_basename
    )
    bios: Path | None = None
    if region == "north-america":
        bios_value = getattr(args, "us_bios", None) or local.get("us_bios")
        if not bios_value:
            raise ToolError(
                f"U.S. BIOS path is required; pass --us-bios or set it in "
                f"{LOCAL_CONFIG_NAME}"
            )
        bios = rooted(root, bios_value)
        require_file("U.S. BIOS", bios, manifest["us_bios_test"]["bios"])
    runs = (
        args.runs_root.expanduser().resolve()
        if args.runs_root
        else root / "work" / "clean_rebuild" / DEFAULT_RUNS_DIRECTORY
    )
    delivery = (
        args.output.expanduser().resolve()
        if args.output
        else rooted(root, manifest["paths"]["outputs"]) / basename
    )
    require_separate_build_directories(runs, delivery)
    plan = {
        "region": region,
        "track1": str(track1),
        "track2": str(track2),
        "basename": basename,
        "runs_root": str(runs),
        "runs_root_state": directory_state(runs),
        "delivery_root": str(delivery),
        "delivery_root_state": directory_state(delivery),
        "independent_clean_builds": 2,
        "independent_region_builds": 2 if region == "north-america" else 0,
        "validation": "full semantic/layout/static preflight",
    }
    if bios is not None:
        plan["us_bios"] = str(bios)
        plan["clean_stage_basename"] = base_basename
        plan["clean_stage_delivery"] = str(runs / "clean_delivery")
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    require_fresh_build_directory("runs root", runs)
    require_fresh_build_directory("delivery root", delivery)
    command_validate(root, argparse.Namespace(skip_comparison=False))
    if region == "japan":
        run_script(
            root,
            "work/clean_rebuild/rebuild.py",
            str(track1),
            str(track2),
            "--runs-root",
            str(runs),
            "--delivery-root",
            str(delivery),
            "--basename",
            basename,
            label=f"Deterministic clean rebuild {args.name}",
        )
        return 0

    if bios is None:  # Defensive narrowing; region resolution required it above.
        raise ToolError("North American build did not resolve a U.S. BIOS")
    clean_runs = runs / "clean_runs"
    clean_delivery = runs / "clean_delivery"
    region_runs = runs / "north_america_runs"
    run_script(
        root,
        "work/clean_rebuild/rebuild.py",
        str(track1),
        str(track2),
        "--runs-root",
        str(clean_runs),
        "--delivery-root",
        str(clean_delivery),
        "--basename",
        base_basename,
        label=f"Deterministic clean rebuild stage {args.name}",
    )
    baseline_track1 = clean_delivery / f"{base_basename}_Track1.bin"
    baseline_track2 = clean_delivery / f"{base_basename}_Track2.bin"
    if not baseline_track1.is_file() or not baseline_track2.is_file():
        raise ToolError("clean build returned without its proven BIN artifacts")
    baseline_track1_sha256 = sha256(baseline_track1)
    run_script(
        root,
        "work/region_variant/build_us_bios_test.py",
        str(baseline_track1),
        str(baseline_track2),
        str(bios),
        "--runs-root",
        str(region_runs),
        "--delivery-root",
        str(delivery),
        "--basename",
        basename,
        "--expected-track1-sha256",
        baseline_track1_sha256,
        label=f"Deterministic North American region stage {args.name}",
    )
    return 0


# CLI grammar and process-level error translation.


def parser() -> argparse.ArgumentParser:
    """Build the complete command-line grammar without parsing process state."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--project-root",
        type=Path,
        help=f"checkout containing {MANIFEST_NAME}; normally auto-detected",
    )
    commands = result.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="check dependencies, inputs, and setup")
    doctor.add_argument("--track1", type=Path)
    doctor.add_argument("--track2", type=Path)
    doctor.add_argument("--us-bios", type=Path)
    doctor.add_argument("--ffmpeg", type=Path)
    doctor.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    doctor.set_defaults(handler=command_doctor)

    prepare = commands.add_parser(
        "prepare", help="prepare the hash-locked retail reference"
    )
    prepare.add_argument("--track1", type=Path)
    prepare.set_defaults(handler=command_prepare)

    edit = commands.add_parser(
        "edit", help="preview or apply canonical wording changes"
    )
    edit.add_argument("record", nargs="?", help="stable CHAPTER:NNN record ID")
    edit.add_argument("--text", help="proposed canonical English")
    edit.add_argument("--changes", type=Path, help="reviewed ID-keyed JSON change file")
    edit.add_argument(
        "--apply", action="store_true", help="write RECORD/--text after validation"
    )
    edit.set_defaults(handler=command_edit)

    compare = commands.add_parser(
        "compare", help="regenerate the bilingual review package"
    )
    compare.add_argument("--output", type=Path)
    compare.set_defaults(handler=command_compare)

    validate = commands.add_parser(
        "validate", help="run static, layout, comparison, and semantic checks"
    )
    validate.add_argument(
        "--skip-comparison",
        action="store_true",
        help="skip comparison regeneration and allow it to be absent",
    )
    validate.set_defaults(handler=command_validate)

    build = commands.add_parser(
        "build",
        help="build deterministic BIN/CUE; North America is the default region",
    )
    build.add_argument(
        "--name",
        help="optional descriptive output label; omit for the neutral release name",
    )
    build.add_argument("--track1", type=Path)
    build.add_argument("--track2", type=Path)
    build.add_argument(
        "--region",
        choices=("north-america", "japan"),
        help="console region; defaults to the project policy (North America)",
    )
    build.add_argument("--us-bios", type=Path)
    build.add_argument("--runs-root", type=Path)
    build.add_argument("--output", type=Path)
    build.add_argument(
        "--dry-run", action="store_true", help="show resolved inputs/outputs only"
    )
    build.set_defaults(handler=command_build)

    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Run the unified tool and translate expected operator failures.

    Args:
        argv: Optional explicit arguments for tests or embedding. ``None`` uses
            the process command line.

    Returns:
        Handler status, two for expected setup/data errors, or 130 for user
        cancellation. Unexpected programming errors retain their traceback.
    """
    args = parser().parse_args(argv)
    try:
        root = find_project_root(args.project_root)
        return int(args.handler(root, args))
    except (ToolError, FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Canceled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

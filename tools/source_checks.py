#!/usr/bin/env python3
"""Run the repository's complete source-only validation contract."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from tools import source_health, source_manifest, style_audit
from work.clean_rebuild import rebuild as clean_rebuild


ROOT = Path(__file__).resolve().parents[1]
CHECK_PATHS = ("nostalgia1907.py", "tools", "tests", "work")
MYPY_TARGETS = (
    "tools/repository_inventory.py",
    "work/clean_rebuild/source_json.py",
    "work/clean_rebuild/raw_cd.py",
)


class SourceCheckError(RuntimeError):
    """Report a failed source-only validation stage."""


def _run(command: Sequence[str], *, root: Path, label: str) -> None:
    """Run one external check and preserve its native diagnostics."""
    print(f"\n== {label} ==", flush=True)
    completed = subprocess.run(tuple(command), cwd=root, check=False)
    if completed.returncode:
        raise SourceCheckError(f"{label} failed with exit code {completed.returncode}")


def run_source_checks(root: Path, *, strict_release: bool) -> None:
    """Run every source-only gate used by contributors and CI."""
    root = root.resolve()
    print("\n== Source-tree health audit ==", flush=True)
    health = source_health.audit(root, strict_release=strict_release)
    if health["status"] != "PASS":
        for failure in cast(list[str], health["failures"]):
            print(f"- {failure}")
        raise SourceCheckError("source-tree health audit failed")
    print(f"PASS: {health['files_checked']} files checked ({health['inventory_mode']}).")

    print("\n== Source review manifest ==", flush=True)
    valid, differences = source_manifest.check_manifest(root)
    if not valid:
        for difference in differences[: source_manifest.MAX_DIFF_LINES]:
            print(f"- {difference}")
        raise SourceCheckError("source review manifest is stale")
    print(f"{source_manifest.MANIFEST_NAME}: PASS")

    print("\n== Production dependency policy ==", flush=True)
    dependency: dict[str, Any] = clean_rebuild._verify_production_independence()
    print(
        f"PASS: {dependency['modules_scanned']} production modules and "
        f"{dependency['data_files_scanned']} tracked data files checked."
    )

    _run((sys.executable, "-m", "compileall", "-q", *CHECK_PATHS), root=root, label="Maintained Python compilation")
    _run((sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"), root=root, label="Source-only tests")
    _run((sys.executable, "-m", "ruff", "check", *CHECK_PATHS), root=root, label="Ruff lint checks")
    _run((sys.executable, "-m", "mypy", *MYPY_TARGETS), root=root, label="Static type checks")

    print("\n== Public API documentation audit ==", flush=True)
    documentation = style_audit.audit(root)
    violations = cast(list[dict[str, Any]], documentation["violations"])
    if documentation["status"] != "PASS":
        for violation in violations:
            print(f"{violation['path']}:{violation['line']}: {violation['rule']} {violation['message']}")
        raise SourceCheckError("public API documentation audit failed")
    print(f"PASS: {documentation['files_checked']} maintained Python files checked.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse source-check command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--strict-release", action="store_true", help="audit exact tracked/release inventory")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run source checks and return a shell-friendly status."""
    args = parse_args(argv)
    try:
        run_source_checks(args.root, strict_release=args.strict_release)
    except (SourceCheckError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("\nAll source-only checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

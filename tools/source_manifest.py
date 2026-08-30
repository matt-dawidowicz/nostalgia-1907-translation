#!/usr/bin/env python3
"""Generate and verify the source-only review manifest."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "MANIFEST.sha256"
HEADER = (
    "# SHA-256 inventory for the source-only review bundle.\n"
    "# MANIFEST.sha256 itself is intentionally excluded from this list.\n"
)


class ManifestInventoryError(RuntimeError):
    """Report that a deterministic source inventory could not be enumerated."""


def _git_tracked_files(root: Path) -> tuple[Path, ...] | None:
    """Return tracked files when ``root`` is a Git checkout, otherwise ``None``."""
    if not (root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ("git", "-C", str(root), "ls-files", "-z", "--cached"),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ManifestInventoryError(
            "could not enumerate Git-tracked source files"
        ) from exc
    relative_paths = tuple(
        Path(os.fsdecode(raw_path))
        for raw_path in completed.stdout.split(b"\0")
        if raw_path
    )
    missing = [path for path in relative_paths if not (root / path).is_file()]
    if missing:
        names = ", ".join(path.as_posix() for path in missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise ManifestInventoryError(
            f"tracked source files are missing from the checkout: {names}{suffix}"
        )
    return relative_paths


def manifest_files(root: Path) -> tuple[Path, ...]:
    """Return the exact files represented by the review manifest.

    Git checkouts use the tracked inventory so untracked local inputs and build
    products cannot affect the manifest. Unpacked source bundles use every file
    except Git metadata, which makes the same manifest verify the archive that a
    reviewer actually received.
    """
    tracked = _git_tracked_files(root)
    if tracked is not None:
        candidates = tracked
    else:
        candidates = tuple(
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file()
            and not (
                path.relative_to(root).parts
                and path.relative_to(root).parts[0] == ".git"
            )
        )
    return tuple(
        sorted(
            (path for path in candidates if path.as_posix() != MANIFEST_NAME),
            key=lambda path: path.as_posix(),
        )
    )


def sha256(path: Path) -> str:
    """Return the uppercase SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def render_manifest(root: Path) -> str:
    """Return canonical manifest text for one checkout or source bundle."""
    lines = [HEADER]
    for relative in manifest_files(root):
        lines.append(f"{sha256(root / relative)}  {relative.as_posix()}\n")
    return "".join(lines)


def manifest_diff(expected: str, actual: str) -> tuple[str, ...]:
    """Return concise line-oriented diagnostics for a stale manifest."""
    expected_lines = set(expected.splitlines()[2:])
    actual_lines = set(actual.splitlines()[2:])
    missing = sorted(expected_lines - actual_lines)
    unexpected = sorted(actual_lines - expected_lines)
    messages: list[str] = []
    messages.extend(f"missing or changed: {line}" for line in missing)
    messages.extend(f"unexpected or stale: {line}" for line in unexpected)
    if expected.splitlines()[:2] != actual.splitlines()[:2]:
        messages.insert(0, "manifest header is not canonical")
    return tuple(messages)


def check_manifest(root: Path) -> tuple[bool, tuple[str, ...]]:
    """Compare the tracked manifest with freshly rendered source inventory."""
    path = root / MANIFEST_NAME
    if not path.is_file():
        return False, (f"missing {MANIFEST_NAME}",)
    expected = render_manifest(root)
    actual = path.read_text(encoding="utf-8")
    return expected == actual, manifest_diff(expected, actual)


def main() -> None:
    """Check the review manifest, or rewrite it when explicitly requested."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite MANIFEST.sha256 from the exact source inventory",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    path = root / MANIFEST_NAME
    if args.write:
        path.write_text(render_manifest(root), encoding="utf-8", newline="\n")
        print(f"updated {path}")
        return
    valid, differences = check_manifest(root)
    if valid:
        print(f"{MANIFEST_NAME}: PASS")
        return
    print(f"{MANIFEST_NAME}: FAIL")
    for difference in differences[:20]:
        print(f"- {difference}")
    if len(differences) > 20:
        print(f"- ... and {len(differences) - 20} more differences")
    print(f"Run: python tools/source_manifest.py --root {root} --write")
    raise SystemExit(1)


if __name__ == "__main__":
    main()

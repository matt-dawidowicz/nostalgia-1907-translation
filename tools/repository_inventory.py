#!/usr/bin/env python3
"""Enumerate repository files for source-only validation tools."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class RepositoryInventoryError(RuntimeError):
    """Report that Git-backed source inventory could not be enumerated."""


def git_tracked_files(root: Path) -> tuple[Path, ...] | None:
    """Return cached Git paths, or ``None`` for an unpacked source tree."""
    if not (root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ("git", "-C", str(root), "ls-files", "-z", "--cached"),
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RepositoryInventoryError(
            "could not enumerate Git-tracked source files"
        ) from error
    relative_paths = tuple(
        Path(os.fsdecode(raw_path))
        for raw_path in completed.stdout.split(b"\0")
        if raw_path
    )
    missing = tuple(path for path in relative_paths if not (root / path).is_file())
    if missing:
        names = ", ".join(path.as_posix() for path in missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise RepositoryInventoryError(
            f"tracked source files are missing from the checkout: {names}{suffix}"
        )
    return relative_paths

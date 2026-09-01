#!/usr/bin/env python3
"""Audit a media-free source checkout for structural and text hygiene issues."""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import tomllib
from collections.abc import Iterable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".gitattributes",
    ".gitignore",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sha256",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
FORBIDDEN_MEDIA_SUFFIXES = {
    ".apng",
    ".avif",
    ".bin",
    ".bmp",
    ".bst",
    ".cue",
    ".dmy",
    ".fnt",
    ".frz",
    ".gif",
    ".heic",
    ".ico",
    ".iso",
    ".jfif",
    ".jpeg",
    ".jpg",
    ".lz",
    ".mcr",
    ".mes",
    ".pcm",
    ".png",
    ".sav",
    ".scn",
    ".srm",
    ".sta",
    ".state",
    ".svg",
    ".tif",
    ".tiff",
    ".wav",
    ".webp",
}
FORBIDDEN_SAVE_STATE_SUFFIX_PREFIXES = (".ss", ".st", ".zs")
LOCAL_ONLY_FILENAMES = frozenset({"nostalgia1907.local.json"})
FORBIDDEN_RELEASE_SUFFIXES = frozenset(
    {".dll", ".dylib", ".exe", ".lib", ".onnx", ".pyc", ".pyd", ".pyo", ".so"}
)
EXCLUDED_DIRECTORY_NAMES = {
    ".agents",
    ".codex",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "outputs",
    "retail_input",
    "retail_reference",
}
EXCLUDED_DIRECTORY_PREFIXES = ("runs",)
FORBIDDEN_RELEASE_DIRECTORY_NAMES = frozenset(
    name for name in EXCLUDED_DIRECTORY_NAMES if name != ".git"
)
RETIRED_GENERATED_FILENAMES = frozenset(
    {
        "recovered_compiled_text.json",
        "translation_delta.json",
        "inspect_translation_delta.py",
    }
)


class DuplicateJsonKeyError(ValueError):
    """Report a duplicate key while loading a JSON source file."""


class SourceInventoryError(RuntimeError):
    """Report that a strict release inventory could not be enumerated safely."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one JSON object while rejecting duplicate keys at every level."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _is_excluded(path: Path) -> bool:
    """Return whether a relative path belongs to generated or local-only state."""
    for part in path.parts[:-1]:
        if part in EXCLUDED_DIRECTORY_NAMES:
            return True
        if part.endswith(".egg-info"):
            return True
        if any(part.startswith(prefix) for prefix in EXCLUDED_DIRECTORY_PREFIXES):
            return True
    return False


def _is_git_metadata(path: Path) -> bool:
    """Return whether a package-relative path is internal Git metadata."""
    return bool(path.parts) and path.parts[0] == ".git"


def _is_release_local_state(path: Path) -> bool:
    """Return whether a release member belongs to generated or private state."""
    for part in path.parts[:-1]:
        if part in FORBIDDEN_RELEASE_DIRECTORY_NAMES or part.endswith(".egg-info"):
            return True
        if any(part.startswith(prefix) for prefix in EXCLUDED_DIRECTORY_PREFIXES):
            return True
    return path.suffix.lower() in FORBIDDEN_RELEASE_SUFFIXES


def _git_tracked_files(root: Path) -> tuple[Path, ...] | None:
    """Return Git-tracked files, or ``None`` for an unpacked source package."""
    if not (root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ("git", "-C", str(root), "ls-files", "-z", "--cached"),
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SourceInventoryError(
            "strict release audit could not enumerate Git-tracked files"
        ) from exc
    relative_paths = tuple(
        Path(os.fsdecode(raw_path))
        for raw_path in completed.stdout.split(b"\0")
        if raw_path
    )
    missing = [
        path.as_posix()
        for path in relative_paths
        if not (root / path).is_file()
    ]
    if missing:
        joined = ", ".join(missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise SourceInventoryError(
            f"strict release audit found missing tracked files: {joined}{suffix}"
        )
    return relative_paths


def iter_source_files(root: Path) -> Iterable[Path]:
    """Yield development source files while ignoring documented local state."""
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        if path.is_file() and not _is_excluded(path.relative_to(root)):
            yield path


def iter_release_files(root: Path) -> tuple[str, tuple[Path, ...]]:
    """Return the exact tracked or unpacked-package inventory for publication."""
    tracked = _git_tracked_files(root)
    if tracked is not None:
        return "git-tracked", tuple(root / relative for relative in tracked)
    files = tuple(
        path
        for path in sorted(
            root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
        )
        if path.is_file() and not _is_git_metadata(path.relative_to(root))
    )
    return "package-members", files


def _check_text(path: Path, relative: str, failures: list[str]) -> None:
    """Validate UTF-8, LF endings, trailing whitespace, and final newline."""
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"{relative}: not valid UTF-8: {exc}")
        return
    if b"\r" in data and path.suffix.lower() != ".ps1":
        failures.append(f"{relative}: contains CR characters; source must use LF")
    if path.suffix.lower() == ".ps1" and b"\n" in data.replace(b"\r\n", b""):
        failures.append(
            f"{relative}: PowerShell source must use consistent CRLF endings"
        )
    if data and not data.endswith(b"\n"):
        failures.append(f"{relative}: missing final newline")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.rstrip(" \t") != line:
            failures.append(f"{relative}:{line_number}: trailing whitespace")


def _check_structured_source(path: Path, relative: str, failures: list[str]) -> None:
    """Parse Python, JSON, and TOML files with strict source-level checks."""
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            ast.parse(text, filename=relative)
        elif path.suffix == ".json":
            json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
        elif path.suffix == ".toml":
            tomllib.loads(text)
    except (
        SyntaxError,
        json.JSONDecodeError,
        DuplicateJsonKeyError,
        tomllib.TOMLDecodeError,
    ) as exc:
        failures.append(f"{relative}: parse failure: {exc}")


def _is_numbered_save_state(suffix: str) -> bool:
    """Return whether a suffix matches a common numbered emulator state form."""
    return (
        len(suffix) == 4
        and suffix[:3] in FORBIDDEN_SAVE_STATE_SUFFIX_PREFIXES
        and suffix[3].isdigit()
    )


def audit(root: Path, *, strict_release: bool = False) -> dict[str, object]:
    """Return a deterministic report for one development or release inventory."""
    failures: list[str] = []
    files_checked = 0
    text_files_checked = 0
    structured_files_checked = 0
    forbidden_media: list[str] = []
    local_only_files: list[str] = []
    release_local_state: list[str] = []
    retired_generated: list[str] = []

    try:
        if strict_release:
            inventory_mode, files = iter_release_files(root)
        else:
            inventory_mode = "development-filtered"
            files = tuple(iter_source_files(root))
    except SourceInventoryError as exc:
        inventory_mode = "unavailable"
        files = ()
        failures.append(str(exc))

    for path in files:
        relative = path.relative_to(root).as_posix()
        files_checked += 1
        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_MEDIA_SUFFIXES or _is_numbered_save_state(suffix):
            forbidden_media.append(relative)
        if strict_release and path.name.casefold() in LOCAL_ONLY_FILENAMES:
            local_only_files.append(relative)
        if strict_release and _is_release_local_state(path.relative_to(root)):
            release_local_state.append(relative)
        if (
            path.name in RETIRED_GENERATED_FILENAMES
            or path.name.startswith("recover_bonus_") and path.suffix == ".json"
        ):
            retired_generated.append(relative)
        if suffix in TEXT_SUFFIXES or path.name in {"LICENSE", "Makefile"}:
            text_files_checked += 1
            _check_text(path, relative, failures)
        if suffix in {".json", ".py", ".toml"}:
            structured_files_checked += 1
            _check_structured_source(path, relative, failures)

    if forbidden_media:
        failures.extend(
            f"{relative}: forbidden game media, generated image, or emulator state"
            for relative in forbidden_media
        )
    if local_only_files:
        failures.extend(
            f"{relative}: local-only configuration cannot enter a source release"
            for relative in local_only_files
        )
    if release_local_state:
        failures.extend(
            f"{relative}: generated or private local state cannot enter a source release"
            for relative in release_local_state
        )
    if retired_generated:
        failures.extend(
            f"{relative}: retired generated recovery output belongs outside source"
            for relative in retired_generated
        )
    return {
        "status": "PASS" if not failures else "FAIL",
        "root": str(root.resolve()),
        "strict_release": strict_release,
        "inventory_mode": inventory_mode,
        "files_checked": files_checked,
        "text_files_checked": text_files_checked,
        "structured_files_checked": structured_files_checked,
        "forbidden_media_count": len(forbidden_media),
        "local_only_file_count": len(local_only_files),
        "release_local_state_count": len(release_local_state),
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> None:
    """Run the source audit and emit its machine-readable report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--strict-release",
        action="store_true",
        help=(
            "audit the exact Git-tracked or unpacked-package inventory, including "
            "normally ignored retail/output directory names"
        ),
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = audit(args.root, strict_release=args.strict_release)
    payload = json.dumps(report, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

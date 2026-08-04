#!/usr/bin/env python3
"""Audit a media-free source checkout for structural and text hygiene issues."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job.
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".gitattributes",
    ".gitignore",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
FORBIDDEN_MEDIA_SUFFIXES = {
    ".bin",
    ".cue",
    ".dmy",
    ".fnt",
    ".iso",
    ".lz",
    ".mes",
    ".pcm",
    ".png",
    ".scn",
    ".wav",
}
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


class DuplicateJsonKeyError(ValueError):
    """Report a duplicate key while loading a JSON source file."""


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
        if any(part.startswith(prefix) for prefix in EXCLUDED_DIRECTORY_PREFIXES):
            return True
    return False


def iter_source_files(root: Path) -> Iterable[Path]:
    """Yield source-tree files in deterministic relative-path order."""
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        if path.is_file() and not _is_excluded(path.relative_to(root)):
            yield path


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


def audit(root: Path) -> dict[str, object]:
    """Return a deterministic report for one source checkout."""
    failures: list[str] = []
    files_checked = 0
    text_files_checked = 0
    structured_files_checked = 0
    forbidden_media: list[str] = []

    for path in iter_source_files(root):
        relative = path.relative_to(root).as_posix()
        files_checked += 1
        if path.suffix.lower() in FORBIDDEN_MEDIA_SUFFIXES:
            forbidden_media.append(relative)
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES or path.name in {"LICENSE", "Makefile"}:
            text_files_checked += 1
            _check_text(path, relative, failures)
        if suffix in {".json", ".py", ".toml"}:
            structured_files_checked += 1
            _check_structured_source(path, relative, failures)

    if forbidden_media:
        failures.extend(
            f"{relative}: forbidden game-media or generated-asset file in source checkout"
            for relative in forbidden_media
        )
    return {
        "status": "PASS" if not failures else "FAIL",
        "root": str(root.resolve()),
        "files_checked": files_checked,
        "text_files_checked": text_files_checked,
        "structured_files_checked": structured_files_checked,
        "forbidden_media_count": len(forbidden_media),
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> None:
    """Run the source audit and emit its machine-readable report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    report = audit(args.root)
    payload = json.dumps(report, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit maintained Python against the project's PEP 8/257 profile.

The audit intentionally uses only the standard library so a source checkout can
enforce the documented layout and docstring contract before optional formatter
dependencies are installed. Black provides mechanical formatting; this script
guards the repository policy that Black alone cannot express.
"""

from __future__ import annotations

import argparse
import ast
from io import StringIO
import json
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


LINE_LENGTH = 88
MAINTAINED_DIRECTORIES = (
    "tools",
    "tests",
    "work/clean_rebuild",
    "work/region_variant",
    "work/audio_localization",
)


@dataclass(frozen=True)
class StyleViolation:
    """Describe one actionable source-style violation."""

    path: str
    line: int
    rule: str
    message: str


def project_root() -> Path:
    """Return the repository root containing this audit tool."""
    return Path(__file__).resolve().parents[1]


def iter_maintained_python(root: Path) -> tuple[Path, ...]:
    """Return all Python files covered by the maintained-code policy.

    Historical forensic directories are deliberately excluded: they document
    past reverse-engineering experiments and are not production dependencies.
    """
    paths = [root / "nostalgia1907.py"]
    for relative in MAINTAINED_DIRECTORIES:
        directory = root / relative
        if directory.is_dir():
            paths.extend(directory.rglob("*.py"))
    return tuple(sorted(paths))


def _docstring_nodes(tree: ast.Module) -> Iterable[ast.AST]:
    """Yield the module and every class or callable that needs a docstring."""
    yield tree
    yield from (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _symbol_name(node: ast.AST) -> str:
    """Return a stable display name for a documented AST symbol."""
    return "<module>" if isinstance(node, ast.Module) else node.name  # type: ignore[attr-defined]


def _audit_docstrings(path: Path, tree: ast.Module, root: Path) -> list[StyleViolation]:
    """Return PEP 257 violations for every maintained symbol in one module."""
    violations: list[StyleViolation] = []
    relative = path.relative_to(root).as_posix()
    for node in _docstring_nodes(tree):
        line_number = getattr(node, "lineno", 1)
        symbol = _symbol_name(node)
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            violations.append(
                StyleViolation(
                    relative,
                    line_number,
                    "D100",
                    f"{symbol} is missing a docstring.",
                )
            )
            continue
        lines = docstring.splitlines()
        if not lines or not lines[0].strip():
            violations.append(
                StyleViolation(
                    relative,
                    line_number,
                    "D101",
                    f"{symbol} has an empty docstring summary.",
                )
            )
            continue
        if lines[0].rstrip()[-1:] not in ".!?":
            violations.append(
                StyleViolation(
                    line_number=line_number,
                    path=relative,
                    rule="D102",
                    message=f"{symbol} docstring summary must end with punctuation.",
                )
            )
        if len(lines) > 1 and lines[1].strip():
            violations.append(
                StyleViolation(
                    line_number=line_number,
                    path=relative,
                    rule="D103",
                    message=f"{symbol} multiline docstring needs a blank second line.",
                )
            )
    return violations


def _audit_lines(path: Path, root: Path) -> list[StyleViolation]:
    """Return line-length, tab, and trailing-whitespace violations for a file."""
    violations: list[StyleViolation] = []
    relative = path.relative_to(root).as_posix()
    source = path.read_text(encoding="utf-8")
    literal_lines = _string_literal_lines(source)
    for line_number, line in enumerate(source.splitlines(), 1):
        if len(line) > LINE_LENGTH and line_number not in literal_lines:
            violations.append(
                StyleViolation(
                    relative,
                    line_number,
                    "E501",
                    f"Line has {len(line)} characters; limit is {LINE_LENGTH}.",
                )
            )
        if line.rstrip(" \t") != line:
            violations.append(
                StyleViolation(
                    relative,
                    line_number,
                    "W291",
                    "Line has trailing whitespace.",
                )
            )
        if line.startswith("\t"):
            violations.append(
                StyleViolation(
                    relative,
                    line_number,
                    "W191",
                    "Line uses a tab for indentation.",
                )
            )
    return violations


def _string_literal_lines(source: str) -> set[int]:
    """Return physical lines occupied by atomic string or bytes literals.

    Long serialized HTML, CSS, reports, hashes, and fixture data should remain
    byte-stable rather than being mechanically split. Black shares this policy:
    it wraps syntax but preserves atomic literal data.
    """
    lines: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.STRING or tokenize.tok_name[
                token.type
            ].startswith("FSTRING"):
                lines.update(range(token.start[0], token.end[0] + 1))
    except tokenize.TokenError:
        # Syntax failures are reported separately by the AST check.
        return lines
    return lines


def audit(root: Path) -> dict[str, object]:
    """Audit maintained Python and return a deterministic JSON-ready report."""
    violations: list[StyleViolation] = []
    paths = iter_maintained_python(root)
    for path in paths:
        violations.extend(_audit_lines(path, root))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            violations.append(
                StyleViolation(
                    path.relative_to(root).as_posix(),
                    error.lineno or 1,
                    "E999",
                    f"Cannot parse Python source: {error.msg}.",
                )
            )
            continue
        violations.extend(_audit_docstrings(path, tree, root))
    ordered = sorted(violations, key=lambda item: (item.path, item.line, item.rule))
    return {
        "status": "PASS" if not ordered else "FAIL",
        "line_length": LINE_LENGTH,
        "files_checked": len(paths),
        "violations": [asdict(violation) for violation in ordered],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the source-style audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=project_root(),
        help="Repository root to audit (default: this tool's repository).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete report as formatted JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the audit, print its report, and return a shell-friendly status."""
    arguments = parse_args(argv)
    report = audit(arguments.root.resolve())
    if arguments.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status']}: {report['files_checked']} files checked; "
            f"{len(report['violations'])} violations."
        )
        for violation in report["violations"]:
            print(
                f"{violation['path']}:{violation['line']}: "
                f"{violation['rule']} {violation['message']}"
            )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

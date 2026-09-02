#!/usr/bin/env python3
"""Audit maintained Python public APIs against the project's docstring contract.

Ruff owns generic Python linting. This audit requires structured documentation
for maintained modules and public APIs while leaving private helper documentation
to technical necessity and review.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


MAINTAINED_DIRECTORIES = (
    "tools",
    "tests",
    "work/clean_rebuild",
    "work/region_variant",
)
DOCUMENTED_NODES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class DocumentationViolation:
    """Describe one actionable documentation-policy violation."""

    path: str
    line: int
    rule: str
    message: str


def project_root() -> Path:
    """Return the repository root containing this audit tool."""
    return Path(__file__).resolve().parents[1]


def iter_maintained_python(root: Path) -> tuple[Path, ...]:
    """Return all Python files covered by the maintained-code policy."""
    paths = [root / "nostalgia1907.py"]
    for relative in MAINTAINED_DIRECTORIES:
        directory = root / relative
        if directory.is_dir():
            paths.extend(directory.rglob("*.py"))
    return tuple(sorted(paths))


def _docstring_nodes(tree: ast.Module) -> Iterable[ast.AST]:
    """Yield the module and every maintained symbol that needs a docstring."""
    yield tree
    for node in tree.body:
        if not isinstance(node, DOCUMENTED_NODES) or node.name.startswith("_"):
            continue
        yield node
        if isinstance(node, ast.ClassDef):
            yield from (
                member
                for member in node.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not member.name.startswith("_")
            )


def _symbol_name(node: ast.AST) -> str:
    """Return a stable display name for a documented AST symbol."""
    if isinstance(node, ast.Module):
        return "<module>"
    if isinstance(node, DOCUMENTED_NODES):
        return node.name
    raise TypeError(f"unsupported documented node: {type(node).__name__}")


def _audit_docstrings(
    path: Path,
    tree: ast.Module,
    root: Path,
) -> list[DocumentationViolation]:
    """Return documentation violations for every maintained symbol in one module."""
    violations: list[DocumentationViolation] = []
    relative = path.relative_to(root).as_posix()
    for node in _docstring_nodes(tree):
        line_number = getattr(node, "lineno", 1)
        symbol = _symbol_name(node)
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            violations.append(
                DocumentationViolation(
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
                DocumentationViolation(
                    relative,
                    line_number,
                    "D101",
                    f"{symbol} has an empty docstring summary.",
                )
            )
            continue
        if lines[0].rstrip()[-1:] not in ".!?":
            violations.append(
                DocumentationViolation(
                    relative,
                    line_number,
                    "D102",
                    f"{symbol} docstring summary must end with punctuation.",
                )
            )
        if len(lines) > 1 and lines[1].strip():
            violations.append(
                DocumentationViolation(
                    relative,
                    line_number,
                    "D103",
                    f"{symbol} multiline docstring needs a blank second line.",
                )
            )
    return violations


def audit(root: Path) -> dict[str, object]:
    """Audit maintained docstrings and return a deterministic JSON-ready report."""
    violations: list[DocumentationViolation] = []
    paths = iter_maintained_python(root)
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            violations.append(
                DocumentationViolation(
                    path.relative_to(root).as_posix(),
                    error.lineno or 1,
                    "D000",
                    f"Cannot inspect docstrings because source does not parse: {error.msg}.",
                )
            )
            continue
        violations.extend(_audit_docstrings(path, tree, root))
    ordered = sorted(violations, key=lambda item: (item.path, item.line, item.rule))
    return {
        "status": "PASS" if not ordered else "FAIL",
        "files_checked": len(paths),
        "violations": [asdict(violation) for violation in ordered],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the documentation audit."""
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
            f"{len(report['violations'])} documentation violations."
        )
        for violation in report["violations"]:
            print(
                f"{violation['path']}:{violation['line']}: "
                f"{violation['rule']} {violation['message']}"
            )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

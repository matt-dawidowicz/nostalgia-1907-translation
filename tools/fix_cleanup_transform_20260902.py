#!/usr/bin/env python3
"""Repair one-shot cleanup transforms and align architectural regression tests."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    """Write transformed UTF-8 source with canonical LF line endings."""
    path.write_text(text, encoding="utf-8", newline="\n")


def repair_release_note_escape() -> None:
    """Restore an escaped newline sequence in transformed release-note source."""
    path = ROOT / "work" / "clean_rebuild" / "rebuild.py"
    text = path.read_text(encoding="utf-8")
    broken = (
        '        "Source-only validation separately enforces the production dependency "\n'
        '        "boundary before a release build is accepted.\n\n"\n'
    )
    fixed = (
        '        "Source-only validation separately enforces the production dependency "\n'
        '        "boundary before a release build is accepted.\\n\\n"\n'
    )
    if broken not in text:
        raise RuntimeError("expected transformed release-note newline was not found")
    text = text.replace(broken, fixed, 1)
    ast.parse(text, filename=str(path))
    write_text(path, text)


def align_code_invariant_tests() -> None:
    """Point integration-fixture and release-note tests at their new ownership."""
    path = ROOT / "tests" / "test_code_invariants.py"
    text = path.read_text(encoding="utf-8")
    import_anchor = "from work.clean_rebuild import translation_formatter\n"
    if import_anchor not in text:
        raise RuntimeError("test_code_invariants.py: import anchor changed")
    text = text.replace(
        import_anchor,
        import_anchor + "\nimport test_script_layout_integration as layout_tests\n",
        1,
    )
    old_notes = '''            notes = clean_rebuild._render_test_notes(\n                coverage,\n                {"modules_scanned": 2, "data_files_scanned": 3},\n            )\n'''
    if old_notes not in text:
        raise RuntimeError("test_code_invariants.py: release-note call baseline changed")
    text = text.replace(
        old_notes,
        "            notes = clean_rebuild._render_test_notes(coverage)\n",
        1,
    )
    write_text(path, text)


def align_source_health_tests() -> None:
    """Make source-health regressions defend the repository-local tool model."""
    path = ROOT / "tests" / "test_source_health.py"
    text = path.read_text(encoding="utf-8")
    old_dependency = '''    def test_runtime_dependencies_are_empty(self) -> None:\n        """Keep source-health and production tooling standard-library only."""\n        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))\n        self.assertEqual(project["project"]["dependencies"], [])\n'''
    new_dependency = '''    def test_repository_has_no_runtime_package_metadata(self) -> None:\n        """Keep the directly executed production toolchain dependency-free."""\n        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))\n        self.assertNotIn("project", project)\n        self.assertNotIn("build-system", project)\n        requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")\n        self.assertIn("ruff==", requirements)\n        self.assertIn("mypy==", requirements)\n'''
    if old_dependency not in text:
        raise RuntimeError("test_source_health.py: dependency test baseline changed")
    text = text.replace(old_dependency, new_dependency, 1)
    text = text.replace(
        '        self.assertIn("python tools/source_health.py --root . --strict-release", text)\n',
        '        self.assertIn("python -m tools.source_checks --root . --strict-release", text)\n',
        1,
    )
    write_text(path, text)


def align_cli_tests() -> None:
    """Replace package-era and duplicated-validation expectations in CLI tests."""
    path = ROOT / "tests" / "test_tool_cli.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("import re\n", "", 1)

    old_version = '''    def test_package_and_manifest_versions_match(self) -> None:\n        """Require packaging metadata to match the operator manifest version."""\n        manifest = nostalgia1907.load_manifest(ROOT)\n        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")\n        match = re.search(r'(?m)^version = "([^\"]+)"$', pyproject)\n        self.assertIsNotNone(match)\n        self.assertEqual(match.group(1), manifest["tool"]["version"])\n'''
    new_version = '''    def test_repository_is_not_a_distribution_package(self) -> None:\n        """Keep project versioning in the operator manifest, not package metadata."""\n        manifest = nostalgia1907.load_manifest(ROOT)\n        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")\n        self.assertNotIn("[project]", pyproject)\n        self.assertNotIn("[build-system]", pyproject)\n        self.assertRegex(manifest["tool"]["version"], r"^[0-9]+\\.[0-9]+\\.[0-9]+$")\n'''
    if old_version not in text:
        raise RuntimeError("test_tool_cli.py: package-version test baseline changed")
    text = text.replace(old_version, new_version, 1)

    text, count = re.subn(
        r'    def test_static_source_inventory_excludes_vendored_runtimes\(self\) -> None:\n.*?\n    def test_validate_runs_every_source_gate_before_retail_gates',
        '    def test_validate_runs_every_source_gate_before_retail_gates',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("test_tool_cli.py: obsolete static-inventory tests baseline changed")

    old_expected = '''        self.assertEqual(\n            events,\n            [\n                "tools/source_health.py",\n                "Python static compilation",\n                "Source-only unit tests",\n                "tools/style_audit.py",\n                "retail",\n                "work/clean_rebuild/translation_formatter.py",\n                "work/clean_rebuild/test_script_layout.py",\n                "comparison",\n                "work/clean_rebuild/translation_validation.py",\n            ],\n        )\n'''
    new_expected = '''        self.assertEqual(\n            events,\n            [\n                "tools/source_checks.py",\n                "retail",\n                "work/clean_rebuild/translation_formatter.py",\n                "comparison",\n                "work/clean_rebuild/translation_validation.py",\n            ],\n        )\n'''
    if old_expected not in text:
        raise RuntimeError("test_tool_cli.py: validation-order expectation baseline changed")
    text = text.replace(old_expected, new_expected, 1)
    write_text(path, text)


def main() -> None:
    """Apply all post-transform corrections and parse-check changed Python modules."""
    repair_release_note_escape()
    align_code_invariant_tests()
    align_source_health_tests()
    align_cli_tests()
    for path in (
        ROOT / "work" / "clean_rebuild" / "rebuild.py",
        ROOT / "tests" / "test_code_invariants.py",
        ROOT / "tests" / "test_source_health.py",
        ROOT / "tests" / "test_tool_cli.py",
    ):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print("Cleanup transforms and regression expectations aligned.")


if __name__ == "__main__":
    main()

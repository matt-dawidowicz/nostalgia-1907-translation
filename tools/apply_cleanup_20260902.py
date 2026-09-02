#!/usr/bin/env python3
"""Apply the audited repository-local toolchain cleanup once."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROFILE_FIELDS = {
    "choice_render_cell_limit",
    "require_choice_segments",
    "exclude_choice_segments_from_wrap",
    "infer_scn_layouts",
    "infer_all_replacement_segments",
    "require_selector_window_segments",
    "scn_selector_window_subtypes",
    "validate_runtime_row_boundaries",
    "validate_text_hygiene",
    "validate_wrapped_text_integrity",
    "validate_scn_floating_row_limits",
    "validate_single_option_transition_rows",
    "no_pad_final_row_segments",
    "single_option_transition_row_exclude",
    "preserve_previous_wrapped_text",
    "preserve_previous_wrapped_text_exclude",
}


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with LF line endings."""
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: Path, old: str, new: str) -> None:
    """Replace one exact source fragment and fail if the baseline differs."""
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}")
    write_text(path, text.replace(old, new))


def regex_once(path: Path, pattern: str, replacement: str) -> None:
    """Apply one DOTALL regex replacement and reject an unexpected baseline."""
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{path}: expected one regex replacement, found {count}")
    write_text(path, updated)


def configure_repository_local_tools() -> None:
    """Remove distribution metadata while retaining Ruff and mypy configuration."""
    write_text(
        ROOT / "pyproject.toml",
        '''[tool.ruff]\nline-length = 88\ntarget-version = "py312"\n\n[tool.ruff.lint]\nselect = ["E4", "E7", "E9", "F", "UP"]\n\n[tool.mypy]\npython_version = "3.12"\ncheck_untyped_defs = true\nno_implicit_optional = true\nwarn_redundant_casts = true\nwarn_unused_configs = true\nwarn_unused_ignores = true\n''',
    )
    write_text(ROOT / "requirements-dev.txt", "mypy==2.3.1\nruff==0.16.5\n")


def add_shared_inventory() -> None:
    """Add one Git inventory primitive used by both source audits."""
    write_text(
        ROOT / "tools" / "repository_inventory.py",
        '''#!/usr/bin/env python3\n"""Enumerate repository files for source-only validation tools."""\n\nfrom __future__ import annotations\n\nimport os\nimport subprocess\nfrom pathlib import Path\n\n\nclass RepositoryInventoryError(RuntimeError):\n    """Report that Git-backed source inventory could not be enumerated."""\n\n\ndef git_tracked_files(root: Path) -> tuple[Path, ...] | None:\n    """Return cached Git paths, or ``None`` for an unpacked source tree."""\n    if not (root / ".git").exists():\n        return None\n    try:\n        completed = subprocess.run(\n            ("git", "-C", str(root), "ls-files", "-z", "--cached"),\n            check=True,\n            capture_output=True,\n        )\n    except (OSError, subprocess.CalledProcessError) as error:\n        raise RepositoryInventoryError(\n            "could not enumerate Git-tracked source files"\n        ) from error\n    relative_paths = tuple(\n        Path(os.fsdecode(raw_path))\n        for raw_path in completed.stdout.split(b"\\0")\n        if raw_path\n    )\n    missing = tuple(path for path in relative_paths if not (root / path).is_file())\n    if missing:\n        names = ", ".join(path.as_posix() for path in missing[:5])\n        suffix = " ..." if len(missing) > 5 else ""\n        raise RepositoryInventoryError(\n            f"tracked source files are missing from the checkout: {names}{suffix}"\n        )\n    return relative_paths\n''',
    )


def refactor_source_health() -> None:
    """Share Git inventory and prune excluded directories before descending."""
    path = ROOT / "tools" / "source_health.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("import os\nimport subprocess\n", "")
    text = text.replace(
        "from pathlib import Path\n",
        "from pathlib import Path\n\nfrom tools.repository_inventory import RepositoryInventoryError, git_tracked_files\n",
    )
    text, count = re.subn(
        r"def _git_tracked_files\(root: Path\) -> tuple\[Path, \.\.\.\] \| None:\n.*?\n\ndef iter_source_files",
        '''def _git_tracked_files(root: Path) -> tuple[Path, ...] | None:\n    """Return Git-tracked files while preserving this tool's error type."""\n    try:\n        return git_tracked_files(root)\n    except RepositoryInventoryError as error:\n        raise SourceInventoryError(str(error)) from error\n\n\ndef _excluded_directory_name(name: str) -> bool:\n    """Return whether development traversal should skip a directory entirely."""\n    return (\n        name in EXCLUDED_DIRECTORY_NAMES\n        or name.endswith(".egg-info")\n        or any(name.startswith(prefix) for prefix in EXCLUDED_DIRECTORY_PREFIXES)\n    )\n\n\ndef iter_source_files''',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("source_health.py: Git inventory helper baseline changed")
    text, count = re.subn(
        r"def iter_source_files\(root: Path\) -> Iterable\[Path\]:\n.*?\n\ndef iter_release_files",
        '''def iter_source_files(root: Path) -> Iterable[Path]:\n    """Yield source files while pruning generated/local trees before descent."""\n    for directory, directory_names, file_names in root.walk(top_down=True):\n        directory_names[:] = sorted(\n            name for name in directory_names if not _excluded_directory_name(name)\n        )\n        for name in sorted(file_names):\n            yield directory / name\n\n\ndef iter_release_files''',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("source_health.py: development walker baseline changed")
    write_text(path, text)


def refactor_source_manifest() -> None:
    """Make the source manifest use the same Git inventory implementation."""
    path = ROOT / "tools" / "source_manifest.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("import os\nimport subprocess\n", "")
    text = text.replace(
        "from pathlib import Path\n",
        "from pathlib import Path\n\nfrom tools.repository_inventory import RepositoryInventoryError, git_tracked_files\n",
    )
    text, count = re.subn(
        r"def _git_tracked_files\(root: Path\) -> tuple\[Path, \.\.\.\] \| None:\n.*?\n\ndef manifest_files",
        '''def _git_tracked_files(root: Path) -> tuple[Path, ...] | None:\n    """Return tracked files while preserving manifest-specific diagnostics."""\n    try:\n        return git_tracked_files(root)\n    except RepositoryInventoryError as error:\n        raise ManifestInventoryError(str(error)) from error\n\n\ndef manifest_files''',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("source_manifest.py: Git inventory helper baseline changed")
    write_text(path, text)


def add_authoritative_source_checks() -> None:
    """Create one source-check entry point shared by CI and local validation."""
    write_text(
        ROOT / "tools" / "source_checks.py",
        '''#!/usr/bin/env python3\n"""Run the repository's complete source-only validation contract."""\n\nfrom __future__ import annotations\n\nimport argparse\nimport subprocess\nimport sys\nfrom collections.abc import Sequence\nfrom pathlib import Path\nfrom typing import Any, cast\n\nfrom tools import source_health, source_manifest, style_audit\nfrom work.clean_rebuild import rebuild as clean_rebuild\n\n\nROOT = Path(__file__).resolve().parents[1]\nCHECK_PATHS = ("nostalgia1907.py", "tools", "tests", "work")\nMYPY_TARGETS = (\n    "tools/repository_inventory.py",\n    "work/clean_rebuild/source_json.py",\n    "work/clean_rebuild/raw_cd.py",\n)\n\n\nclass SourceCheckError(RuntimeError):\n    """Report a failed source-only validation stage."""\n\n\ndef _run(command: Sequence[str], *, root: Path, label: str) -> None:\n    """Run one external check and preserve its native diagnostics."""\n    print(f"\\n== {label} ==", flush=True)\n    completed = subprocess.run(tuple(command), cwd=root, check=False)\n    if completed.returncode:\n        raise SourceCheckError(f"{label} failed with exit code {completed.returncode}")\n\n\ndef run_source_checks(root: Path, *, strict_release: bool) -> None:\n    """Run every source-only gate used by contributors and CI."""\n    root = root.resolve()\n    print("\\n== Source-tree health audit ==", flush=True)\n    health = source_health.audit(root, strict_release=strict_release)\n    if health["status"] != "PASS":\n        for failure in cast(list[str], health["failures"]):\n            print(f"- {failure}")\n        raise SourceCheckError("source-tree health audit failed")\n    print(f"PASS: {health['files_checked']} files checked ({health['inventory_mode']}).")\n\n    print("\\n== Source review manifest ==", flush=True)\n    valid, differences = source_manifest.check_manifest(root)\n    if not valid:\n        for difference in differences[: source_manifest.MAX_DIFF_LINES]:\n            print(f"- {difference}")\n        raise SourceCheckError("source review manifest is stale")\n    print(f"{source_manifest.MANIFEST_NAME}: PASS")\n\n    print("\\n== Production dependency policy ==", flush=True)\n    dependency: dict[str, Any] = clean_rebuild._verify_production_independence()\n    print(\n        f"PASS: {dependency['modules_scanned']} production modules and "\n        f"{dependency['data_files_scanned']} tracked data files checked."\n    )\n\n    _run((sys.executable, "-m", "compileall", "-q", *CHECK_PATHS), root=root, label="Maintained Python compilation")\n    _run((sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"), root=root, label="Source-only tests")\n    _run((sys.executable, "-m", "ruff", "check", *CHECK_PATHS), root=root, label="Ruff lint checks")\n    _run((sys.executable, "-m", "mypy", *MYPY_TARGETS), root=root, label="Static type checks")\n\n    print("\\n== Public API documentation audit ==", flush=True)\n    documentation = style_audit.audit(root)\n    violations = cast(list[dict[str, Any]], documentation["violations"])
    if documentation["status"] != "PASS":\n        for violation in violations:\n            print(f"{violation['path']}:{violation['line']}: {violation['rule']} {violation['message']}")\n        raise SourceCheckError("public API documentation audit failed")\n    print(f"PASS: {documentation['files_checked']} maintained Python files checked.")\n\n\ndef parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:\n    """Parse source-check command-line arguments."""\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument("--root", type=Path, default=ROOT)\n    parser.add_argument("--strict-release", action="store_true", help="audit exact tracked/release inventory")\n    return parser.parse_args(argv)\n\n\ndef main(argv: Sequence[str] | None = None) -> int:\n    """Run source checks and return a shell-friendly status."""\n    args = parse_args(argv)\n    try:\n        run_source_checks(args.root, strict_release=args.strict_release)\n    except (SourceCheckError, ValueError, OSError) as error:\n        print(f"ERROR: {error}", file=sys.stderr)\n        return 1\n    print("\\nAll source-only checks passed.")\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n''',
    )


def remove_legacy_profile_state() -> None:
    """Delete migration-only profile fields and make future reintroduction fail."""
    source_root = ROOT / "work" / "clean_rebuild" / "sources"
    index = json.loads((source_root / "index.json").read_text(encoding="utf-8"))
    removed = 0
    for item in index["chapters"]:
        path = source_root / item["source"]
        source = json.loads(path.read_text(encoding="utf-8"))
        profile = source.get("profile")
        if isinstance(profile, dict):
            for field in tuple(profile):
                if field in LEGACY_PROFILE_FIELDS:
                    del profile[field]
                    removed += 1
        write_text(path, json.dumps(source, ensure_ascii=False, indent=2) + "\n")
    if not removed:
        raise RuntimeError("expected at least one legacy profile field")

    path = ROOT / "work" / "clean_rebuild" / "profile_schema.py"
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r"LEGACY_PROFILE_FIELDS = frozenset\(\n.*?\n\)\n\n",
        "",
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("profile_schema.py: legacy field declaration not found")
    text = text.replace(
        "    unknown = set(profile) - ACTIVE_PROFILE_FIELDS - LEGACY_PROFILE_FIELDS\n",
        "    unknown = set(profile) - ACTIVE_PROFILE_FIELDS\n",
    )
    text = text.replace(
        '    """Validate profile identity and return present legacy no-op fields.\n',
        '    """Validate profile identity and reject retired or unknown fields.\n',
    )
    text = text.replace(
        "        Legacy field names present in the profile. They are accepted for\n        provenance but have no production effect.\n",
        "        An empty compatibility set. Retired migration fields are rejected.\n",
    )
    text = text.replace(
        "    return frozenset(set(profile).intersection(LEGACY_PROFILE_FIELDS))\n",
        "    return frozenset()\n",
    )
    write_text(path, text)

    path = ROOT / "tests" / "test_profile_schema.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'from pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nCLEAN = ROOT / "work" / "clean_rebuild"\nSOURCES = CLEAN / "sources"\n\nfrom work.clean_rebuild.profile_schema import profile_text_failures, validate_profile  # noqa: E402\nfrom work.clean_rebuild.source_json import load_json_object  # noqa: E402\n',
        'from pathlib import Path\n\nfrom work.clean_rebuild.profile_schema import profile_text_failures, validate_profile\nfrom work.clean_rebuild.source_json import load_json_object\n\n\nROOT = Path(__file__).resolve().parents[1]\nCLEAN = ROOT / "work" / "clean_rebuild"\nSOURCES = CLEAN / "sources"\n',
    )
    old = '''    def test_all_canonical_profiles_and_text_rules_pass(self) -> None:\n        """Validate every tracked profile without requiring retail fixtures."""\n        index = load_json_object(SOURCES / "index.json")\n        legacy_fields: set[str] = set()\n        for item in index["chapters"]:\n            source = load_json_object(SOURCES / item["source"])\n            chapter = source["chapter"]\n            with self.subTest(chapter=chapter):\n                legacy_fields.update(\n                    validate_profile(source.get("profile"), chapter=chapter)\n                )\n                self.assertEqual(\n                    profile_text_failures(\n                        source.get("profile"),\n                        source["records"],\n                        chapter=chapter,\n                    ),\n                    [],\n                )\n        self.assertIn("validate_wrapped_text_integrity", legacy_fields)\n        self.assertIn("choice_render_cell_limit", legacy_fields)\n'''
    new = '''    def test_all_canonical_profiles_and_text_rules_pass(self) -> None:\n        """Validate every tracked profile without retired migration fields."""\n        index = load_json_object(SOURCES / "index.json")\n        for item in index["chapters"]:\n            source = load_json_object(SOURCES / item["source"])\n            chapter = source["chapter"]\n            with self.subTest(chapter=chapter):\n                self.assertEqual(validate_profile(source.get("profile"), chapter=chapter), frozenset())\n                self.assertEqual(\n                    profile_text_failures(source.get("profile"), source["records"], chapter=chapter),\n                    [],\n                )\n\n    def test_retired_profile_field_is_rejected(self) -> None:\n        """Prevent migration-era no-op settings from returning to canonical data."""\n        with self.assertRaisesRegex(ValueError, "unknown fields"):\n            validate_profile({"schema_version": 1, "choice_render_cell_limit": None}, chapter="TEST")\n'''
    if old not in text:
        raise RuntimeError("test_profile_schema.py: legacy-profile test baseline changed")
    text = text.replace(old, new)
    text = text.replace(
        '    """Keep live profile settings distinct from accepted legacy metadata."""\n',
        '    """Keep canonical renderer profiles limited to live production fields."""\n',
    )
    write_text(path, text)


def consolidate_cli_validation() -> None:
    """Reuse strict JSON loading and the same source gate used by CI."""
    path = ROOT / "nostalgia1907.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from typing import Any\n",
        "from typing import Any\n\nfrom work.clean_rebuild.source_json import load_json_object as _strict_load_json_object\n",
    )
    text, count = re.subn(
        r"class DuplicateJsonKeyError\(ValueError\):\n.*?\n\n# Project discovery, configuration, and immutable input guards\.",
        '''def load_json_object(path: Path, *, label: str) -> dict[str, Any]:\n    """Load one strict UTF-8 JSON object and translate expected input errors."""\n    try:\n        return _strict_load_json_object(path)\n    except FileNotFoundError as error:\n        raise ToolError(f"missing {label}: {path}") from error\n    except ValueError as error:\n        raise ToolError(f"invalid {label}: {error}") from error\n\n\n# Project discovery, configuration, and immutable input guards.''',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("nostalgia1907.py: duplicate JSON loader baseline changed")
    text, count = re.subn(
        r"def operator_python_sources\(root: Path, manifest: dict\[str, Any\]\) -> list\[Path\]:\n.*?\n\ndef command_compare",
        "def command_compare",
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("nostalgia1907.py: obsolete source enumerator baseline changed")
    start = text.index("def command_validate(root: Path, args: argparse.Namespace) -> int:")
    retail_marker = "    retail = require_retail_reference(root, manifest)\n"
    retail_index = text.index(retail_marker, start)
    manifest_marker = "    manifest = load_manifest(root)\n"
    manifest_index = text.index(manifest_marker, start) + len(manifest_marker)
    prefix = text[:manifest_index]
    suffix = text[retail_index:]
    source_gate = '''    run_script(\n        root,\n        "tools/source_checks.py",\n        "--root",\n        str(root),\n        "--strict-release",\n        label="Complete source-only validation",\n    )\n'''
    text = prefix + source_gate + suffix
    text = text.replace(
        '    run_script(\n        root,\n        "work/clean_rebuild/test_script_layout.py",\n        "-v",\n        label="Script layout tests",\n    )\n',
        "",
    )
    text = text.replace(
        "    except (ToolError, FileNotFoundError, PermissionError, ValueError) as exc:\n",
        "    except (ToolError, FileNotFoundError, PermissionError) as exc:\n",
    )
    write_text(path, text)


def move_integration_test() -> None:
    """Move the retail-backed layout suite out of byte-producing source code."""
    old = ROOT / "work" / "clean_rebuild" / "test_script_layout.py"
    new = ROOT / "tests" / "test_script_layout_integration.py"
    text = old.read_text(encoding="utf-8")
    text = text.replace("from . import mes_compiler\n", "from work.clean_rebuild import mes_compiler\n")
    text = re.sub(r"from \.([A-Za-z0-9_]+) import ", r"from work.clean_rebuild.\1 import ", text)
    write_text(new, text)
    old.unlink()

    path = ROOT / "tests" / "test_code_invariants.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("from work.clean_rebuild import test_script_layout as layout_tests  # noqa: E402\n", "")
    text = text.replace("  # noqa: E402", "")
    write_text(path, text)

    path = ROOT / "work" / "clean_rebuild" / "verification_manifest.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('    "test_script_layout.py",\n', "")
    text = text.replace(
        '    for name in ("nostalgia1907.py", "nostalgia1907.project.json", "pyproject.toml"):\n',
        '    for name in ("nostalgia1907.py", "nostalgia1907.project.json"):\n',
    )
    write_text(path, text)


def relocate_static_dependency_audit() -> None:
    """Keep source architecture checks out of each deterministic binary build."""
    path = ROOT / "work" / "clean_rebuild" / "rebuild.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "def _render_test_notes(\n    coverage: dict[str, object],\n    dependency_audit: dict[str, object],\n) -> str:\n",
        "def _render_test_notes(coverage: dict[str, object]) -> str:\n",
    )
    text, count = re.subn(
        r'        f"A static production dependency audit scanned "\n.*?        "Retail inputs remain separately size- and SHA-256-guarded\.\\n\\n"\n',
        '        "Source-only validation separately enforces the production dependency "\n        "boundary before a release build is accepted.\\n\\n"\n',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("rebuild.py: dependency note baseline changed")
    text = text.replace("    dependency_audit = _verify_production_independence()\n", "")
    text = text.replace('        "production_dependency_audit": dependency_audit,\n', "")
    text = text.replace("    notes = _render_test_notes(coverage, dependency_audit)\n", "    notes = _render_test_notes(coverage)\n")
    write_text(path, text)


def relax_private_docstring_ceremony() -> None:
    """Enforce documentation on public APIs while retaining useful private prose."""
    path = ROOT / "tools" / "style_audit.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "    yield tree\n    yield from (node for node in ast.walk(tree) if isinstance(node, DOCUMENTED_NODES))\n",
        '''    yield tree\n    for node in tree.body:\n        if not isinstance(node, DOCUMENTED_NODES) or node.name.startswith("_"):\n            continue\n        yield node\n        if isinstance(node, ast.ClassDef):\n            yield from (\n                member\n                for member in node.body\n                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))\n                and not member.name.startswith("_")\n            )\n''',
    )
    text = text.replace(
        '"""Audit maintained Python against the project\'s docstring contract.\n\nRuff owns generic Python linting in contributor and CI environments. This\nstandard-library audit keeps only the repository-specific documentation policy:\nevery maintained module, class, function, method, and nested helper must have a\nstructured docstring with a non-empty punctuated summary.\n"""',
        '"""Audit maintained Python public APIs against the project\'s docstring contract.\n\nRuff owns generic Python linting. This audit requires structured documentation\nfor maintained modules and public APIs while leaving private helper documentation\nto technical necessity and review.\n"""',
    )
    write_text(path, text)

    path = ROOT / "tests" / "test_documentation.py"
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r"    def test_maintained_python_has_complete_pep257_coverage\(self\) -> None:\n.*?\n\n\nif __name__ == \"__main__\":",
        '''    def test_maintained_python_has_documented_public_api(self) -> None:\n        """Require structural docstrings on modules and public top-level APIs."""\n        callable_nodes = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)\n        for path in maintained_python():\n            tree = ast.parse(path.read_text(encoding="utf-8"))\n            nodes = [tree]\n            for node in tree.body:\n                if isinstance(node, callable_nodes) and not node.name.startswith("_"):\n                    nodes.append(node)\n                    if isinstance(node, ast.ClassDef):\n                        nodes.extend(\n                            member\n                            for member in node.body\n                            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))\n                            and not member.name.startswith("_")\n                        )\n            for node in nodes:\n                name = "<module>" if node is tree else node.name\n                with self.subTest(path=path.relative_to(ROOT), symbol=name):\n                    docstring = ast.get_docstring(node, clean=False)\n                    self.assertIsNotNone(docstring)\n                    lines = (docstring or "").splitlines()\n                    self.assertTrue(lines and lines[0].strip())\n                    self.assertRegex(lines[0].rstrip(), r"[.!?]$")\n                    if len(lines) > 1:\n                        self.assertEqual(lines[1].strip(), "")\n\n\nif __name__ == "__main__":''',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("test_documentation.py: exhaustive docstring test baseline changed")
    write_text(path, text)

    write_text(
        ROOT / "docs" / "DOCSTRING_STANDARD.md",
        '''# Python documentation standard\n\nThe Python source is part of the preservation record for this project. A future\nmaintainer should be able to understand why a parser, formatter, validator, or\nwriter exists without reconstructing its intent from a generated disc image.\n\n## Supported scope\n\nThe automated contract applies to maintained modules and their public top-level\nclasses, functions, and methods. Private and nested helpers require docstrings\nwhen their behavior is non-obvious, binary-format-sensitive, stateful, or\notherwise benefits from an explicit contract. This avoids ceremonial prose on\nself-explanatory implementation details while preserving documentation where it\nprotects reverse-engineered behavior.\n\n## Formatting profile\n\nPython 3.12 is the minimum supported interpreter. Ruff owns generic linting and\nmodernization checks with the repository's 88-column target. Source text uses\nUTF-8, LF line endings, a final newline, and no trailing whitespace.\n\n## Docstrings\n\nFor maintained public APIs:\n\n1. Write a concise summary ending in punctuation.\n2. Put a blank line after the summary in a multi-line docstring.\n3. Describe purpose and project context rather than restating the symbol name.\n4. Document inputs and outputs whose units, ownership, shape, or constraints are\n   not obvious from type annotations.\n5. Identify meaningful filesystem writes, subprocesses, mutation, and caches.\n6. State recoverable failure conditions where doing so helps callers.\n7. Record assumptions that protect disc layout, determinism, translation data,\n   renderer behavior, or retail provenance.\n\nPrivate helpers should be documented when the reason for their existence is not\nclear from their name, types, module documentation, and nearby comments. Binary\nformat constants and unusual algorithms should retain strong explanations even\nwhen their symbols are private.\n\n## Explanatory comments\n\nComments should explain why a non-obvious step exists, especially around disc\ngeometry, reverse-engineered formats, renderer behavior, or deterministic\noutput. Avoid narrating obvious Python syntax or duplicating a docstring.\n\n## Review checklist\n\n1. Run `python -m tools.source_checks --root . --strict-release`.\n2. Confirm public API documentation still describes behavior.\n3. Confirm non-obvious private binary/renderer logic still has useful context.\n4. Keep comments synchronized with the implementation.\n5. For documentation-only edits, verify executable behavior is unchanged.\n\nAutomation enforces structural coverage on maintained public APIs; human review\nremains responsible for technical accuracy and useful context.\n''',
    )


def update_repository_docs() -> None:
    """Describe direct-checkout execution rather than package installation."""
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "python -m pip install -e .\n",
        "# The toolchain runs directly from this checkout; no project install is required.\n",
    )
    text = text.replace(
        'The production and operator tooling has no third-party runtime dependencies.\nContributors who run the full source-quality suite should install the `dev`\nextra, which currently pins Ruff:\n\n```powershell\npython -m pip install -e ".[dev]"\n```',
        'The production and operator tooling has no third-party runtime dependencies.\nContributors who run the source-quality suite install the repository-local\ndevelopment requirements (Ruff and mypy):\n\n```powershell\npython -m pip install -r requirements-dev.txt\n```',
    )
    text = text.replace(
        "python tools/source_health.py --root . --strict-release\npython tools/source_manifest.py --root .\npython -m compileall -q nostalgia1907.py tools tests work\npython -m unittest discover -s tests -v\npython -m ruff check nostalgia1907.py tools tests work\npython tools/style_audit.py --root .\n",
        "python -m tools.source_checks --root . --strict-release\n",
    )
    write_text(path, text)

    for relative in (
        "CONTRIBUTING.md",
        "docs/DEVELOPMENT.md",
        "docs/GETTING_STARTED.md",
        "docs/ARCHITECTURE.md",
        "docs/WHOLE_GAME_TESTING.md",
    ):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        text = text.replace('python -m pip install -e ".[dev]"', "python -m pip install -r requirements-dev.txt")
        text = text.replace("python -m pip install -e .", "# no project install is required")
        text = text.replace('pip install -e ".[dev]"', "pip install -r requirements-dev.txt")
        text = text.replace("work/clean_rebuild/test_script_layout.py", "tests/test_script_layout_integration.py")
        text = text.replace("work.clean_rebuild.test_script_layout", "tests/test_script_layout_integration.py")
        write_text(path, text)


def update_ci() -> None:
    """Use the same source-check command across supported interpreters and OSes."""
    write_text(
        ROOT / ".github" / "workflows" / "source-checks.yml",
        '''name: Source checks\n\non:\n  push:\n  pull_request:\n\npermissions:\n  contents: read\n\nconcurrency:\n  group: source-checks-${{ github.workflow }}-${{ github.ref }}\n  cancel-in-progress: true\n\njobs:\n  source-tests:\n    name: ${{ matrix.os }} / Python ${{ matrix.python-version }}\n    runs-on: ${{ matrix.os }}\n    strategy:\n      fail-fast: false\n      matrix:\n        include:\n          - os: ubuntu-latest\n            python-version: "3.12"\n          - os: ubuntu-latest\n            python-version: "3.13"\n          - os: ubuntu-latest\n            python-version: "3.14"\n          - os: windows-latest\n            python-version: "3.14"\n\n    steps:\n      - name: Check out source\n        uses: actions/checkout@v7\n\n      - name: Set up Python\n        uses: actions/setup-python@v7\n        with:\n          python-version: ${{ matrix.python-version }}\n          cache: pip\n          cache-dependency-path: requirements-dev.txt\n\n      - name: Install source-quality tools\n        run: python -m pip install -r requirements-dev.txt\n\n      - name: Run complete source-only validation\n        run: python -m tools.source_checks --root . --strict-release\n''',
    )


def ensure_legacy_profiles_are_gone() -> None:
    """Fail the one-shot migration if canonical source still contains retired fields."""
    source_root = ROOT / "work" / "clean_rebuild" / "sources"
    index = json.loads((source_root / "index.json").read_text(encoding="utf-8"))
    for item in index["chapters"]:
        source = json.loads((source_root / item["source"]).read_text(encoding="utf-8"))
        profile = source.get("profile") or {}
        leftovers = LEGACY_PROFILE_FIELDS.intersection(profile)
        if leftovers:
            raise RuntimeError(f"{item['chapter']}: retired fields remain: {sorted(leftovers)}")


def main() -> None:
    """Apply all non-byte-semantic repository cleanup transformations."""
    configure_repository_local_tools()
    add_shared_inventory()
    refactor_source_health()
    refactor_source_manifest()
    add_authoritative_source_checks()
    remove_legacy_profile_state()
    consolidate_cli_validation()
    move_integration_test()
    relocate_static_dependency_audit()
    relax_private_docstring_ceremony()
    update_repository_docs()
    update_ci()
    ensure_legacy_profiles_are_gone()
    print("Repository-local cleanup applied successfully.")


if __name__ == "__main__":
    main()

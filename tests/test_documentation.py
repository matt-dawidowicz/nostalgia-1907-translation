"""Repository documentation contracts for new contributors."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    "architecture": ROOT / "docs" / "ARCHITECTURE.md",
    "editing": ROOT / "docs" / "TRANSLATION_EDITING.md",
    "formats": ROOT / "docs" / "BINARY_FORMATS.md",
    "development": ROOT / "docs" / "DEVELOPMENT.md",
}
DOCSTRING_GUIDE = ROOT / "docs" / "DOCSTRING_STANDARD.md"
MAINTAINED_PYTHON = (
    ROOT / "nostalgia1907.py",
    ROOT / "work" / "clean_rebuild" / "raw_cd.py",
    ROOT / "work" / "clean_rebuild" / "iso9660.py",
    ROOT / "work" / "clean_rebuild" / "lz_format.py",
    ROOT / "work" / "clean_rebuild" / "mes_format.py",
    ROOT / "work" / "clean_rebuild" / "font_render.py",
    ROOT / "work" / "clean_rebuild" / "scn_layout.py",
    ROOT / "work" / "clean_rebuild" / "mes_compiler.py",
    ROOT / "work" / "clean_rebuild" / "prepare_retail.py",
    ROOT / "work" / "clean_rebuild" / "build_mes_set.py",
    ROOT / "work" / "clean_rebuild" / "build_archives.py",
    ROOT / "work" / "clean_rebuild" / "main_patch.py",
    ROOT / "work" / "clean_rebuild" / "regression.py",
    ROOT / "work" / "clean_rebuild" / "verification_manifest.py",
    ROOT / "work" / "clean_rebuild" / "rebuild.py",
    ROOT / "work" / "clean_rebuild" / "translation_formatter.py",
    ROOT / "work" / "clean_rebuild" / "translation_validation.py",
    ROOT / "work" / "clean_rebuild" / "translation_audit.py",
    ROOT / "work" / "clean_rebuild" / "bomb_audit.py",
    ROOT / "work" / "clean_rebuild" / "export_bilingual_comparison.py",
    ROOT / "work" / "clean_rebuild" / "export_fixed_layout_review.py",
    ROOT / "work" / "clean_rebuild" / "export_translation_proposals.py",
    ROOT / "work" / "clean_rebuild" / "test_script_layout.py",
    ROOT / "work" / "region_variant" / "build_us_bios_test.py",
    ROOT / "work" / "audio_localization" / "audio_localization.py",
)


class DocumentationTests(unittest.TestCase):
    """Keep contributor guides synchronized with production structure."""

    def test_contributor_documents_exist_and_are_linked(self) -> None:
        """Keep required contributor guides discoverable from entry documents."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        for name, path in DOCS.items():
            with self.subTest(document=name):
                self.assertTrue(path.is_file())
                relative = path.relative_to(ROOT).as_posix()
                self.assertIn(relative, readme)
                self.assertIn(relative, contributing)

    def test_python_documentation_standard_is_linked(self) -> None:
        """Keep the docstring/comment contract visible to contributors."""
        self.assertTrue(DOCSTRING_GUIDE.is_file())
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        development = DOCS["development"].read_text(encoding="utf-8")
        self.assertIn("docs/DOCSTRING_STANDARD.md", contributing)
        self.assertIn("DOCSTRING_STANDARD.md", development)

    def test_architecture_lists_every_production_module(self) -> None:
        """Require architecture documentation for every active production module."""
        rebuild = ROOT / "work" / "clean_rebuild" / "rebuild.py"
        tree = ast.parse(rebuild.read_text(encoding="utf-8"))
        modules: tuple[str, ...] | None = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "PRODUCTION_MODULES"
                for target in node.targets
            ):
                modules = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(modules)
        architecture = DOCS["architecture"].read_text(encoding="utf-8")
        for module in modules or ():
            with self.subTest(module=module):
                self.assertIn(f"`{module}`", architecture)

    def test_editing_guide_documents_the_canonical_record_contract(self) -> None:
        """Keep canonical record ownership explicit in the editor guide."""
        editing = DOCS["editing"].read_text(encoding="utf-8")
        for token in (
            "CHAPTER:NNN",
            '`policy: "translate"`',
            '`policy: "preserve"`',
            '`layout_policy: "adaptive"`',
            '`layout_policy: "fixed"`',
            "zero-based",
            "SCN",
        ):
            with self.subTest(token=token):
                self.assertIn(token, editing)

    def test_format_guide_documents_all_binary_layers(self) -> None:
        """Keep the binary-format guide aligned with every supported layer."""
        formats = DOCS["formats"].read_text(encoding="utf-8")
        for heading in (
            "Raw Track 1",
            "ISO 9660",
            "Chapter LZ archive",
            "MES script container",
            "Font cells",
            "SCN renderer references",
            "CUE and Track 2",
        ):
            with self.subTest(heading=heading):
                self.assertRegex(formats, rf"(?m)^## .*{re.escape(heading)}")

    def test_determinism_and_binding_scope_is_documented(self) -> None:
        """Keep package determinism and report-binding limitations explicit."""
        development = DOCS["development"].read_text(encoding="utf-8")
        architecture = DOCS["architecture"].read_text(encoding="utf-8")
        for token in (
            "CPython major/minor",
            "fresh output roots",
            "verification_manifest.py",
            "aggregate input fingerprint",
            "runtime claim",
        ):
            with self.subTest(token=token):
                self.assertIn(token, development + architecture)

    def test_guides_contain_no_machine_specific_absolute_paths(self) -> None:
        """Reject local Windows paths from portable contributor documentation."""
        documents = [ROOT / "CONTRIBUTING.md", *DOCS.values(), DOCSTRING_GUIDE]
        windows_absolute = re.compile(r"(?i)\b[A-Z]:[\\/]")
        for path in documents:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(windows_absolute.search(text))

    def test_maintained_python_has_complete_pep257_coverage(self) -> None:
        """Require a structurally valid docstring on every maintained symbol."""
        callable_nodes = (
            ast.ClassDef,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
        )
        for path in MAINTAINED_PYTHON:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            nodes = [tree, *ast.walk(tree)]
            for node in nodes:
                if node is not tree and not isinstance(node, callable_nodes):
                    continue
                name = "<module>" if node is tree else node.name
                with self.subTest(path=path.relative_to(ROOT), symbol=name):
                    docstring = ast.get_docstring(node, clean=False)
                    self.assertIsNotNone(docstring)
                    lines = (docstring or "").splitlines()
                    self.assertTrue(lines and lines[0].strip())
                    self.assertRegex(lines[0].rstrip(), r"[.!?]$")
                    if len(lines) > 1:
                        self.assertEqual(lines[1].strip(), "")


if __name__ == "__main__":
    unittest.main()

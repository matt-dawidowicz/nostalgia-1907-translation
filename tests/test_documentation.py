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


class DocumentationTests(unittest.TestCase):
    """Keep contributor guides synchronized with production structure."""

    def test_contributor_documents_exist_and_are_linked(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        for name, path in DOCS.items():
            with self.subTest(document=name):
                self.assertTrue(path.is_file())
                relative = path.relative_to(ROOT).as_posix()
                self.assertIn(relative, readme)
                self.assertIn(relative, contributing)

    def test_architecture_lists_every_production_module(self) -> None:
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

    def test_guides_contain_no_machine_specific_absolute_paths(self) -> None:
        documents = [ROOT / "CONTRIBUTING.md", *DOCS.values()]
        windows_absolute = re.compile(r"(?i)\b[A-Z]:[\\/]")
        for path in documents:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(windows_absolute.search(text))


if __name__ == "__main__":
    unittest.main()

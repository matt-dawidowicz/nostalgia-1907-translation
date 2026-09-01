"""Regression tests for the maintained Python documentation audit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import style_audit


ROOT = Path(__file__).resolve().parents[1]


class StyleAuditTests(unittest.TestCase):
    """Keep repository-specific docstring checks deterministic."""

    def test_current_maintained_source_passes(self) -> None:
        """Require every maintained Python file to satisfy the docstring policy."""
        report = style_audit.audit(ROOT)
        self.assertEqual(report["status"], "PASS", report["violations"])
        self.assertEqual(
            report["files_checked"],
            len(style_audit.iter_maintained_python(ROOT)),
        )

    def test_audit_reports_missing_docstrings(self) -> None:
        """Report module and callable documentation omissions directly."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "nostalgia1907.py"
            path.write_text("def missing():\n    pass\n", encoding="utf-8")
            report = style_audit.audit(root)
        violations = [
            item for item in report["violations"] if item["rule"] == "D100"
        ]
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(len(violations), 2)
        self.assertTrue(all(item["path"] == "nostalgia1907.py" for item in violations))


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the maintained Python style audit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import style_audit


ROOT = Path(__file__).resolve().parents[1]


class StyleAuditTests(unittest.TestCase):
    """Keep PEP 8/257 checks deterministic and repository-wide."""

    def test_current_maintained_source_passes(self) -> None:
        """Require every maintained Python file to satisfy the shared profile."""
        report = style_audit.audit(ROOT)
        self.assertEqual(report["status"], "PASS", report["violations"])
        self.assertEqual(
            report["files_checked"],
            len(style_audit.iter_maintained_python(ROOT)),
        )

    def test_audit_reports_line_and_docstring_contracts(self) -> None:
        """Report readable violations for a deliberately malformed source file."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "nostalgia1907.py"
            path.write_text(
                "def missing():\n" "    " + "x" * 90 + " = 1  \n",
                encoding="utf-8",
            )
            report = style_audit.audit(root)
        violations = {(item["rule"], item["path"]) for item in report["violations"]}
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(("D100", "nostalgia1907.py"), violations)
        self.assertIn(("E501", "nostalgia1907.py"), violations)
        self.assertIn(("W291", "nostalgia1907.py"), violations)

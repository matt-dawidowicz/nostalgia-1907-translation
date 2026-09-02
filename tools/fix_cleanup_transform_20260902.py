#!/usr/bin/env python3
"""Repair the one-shot cleanup's escaped release-note newline."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "work" / "clean_rebuild" / "rebuild.py"


def main() -> None:
    """Restore an escaped newline sequence and verify the transformed module parses."""
    text = PATH.read_text(encoding="utf-8")
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
    ast.parse(text, filename=str(PATH))
    PATH.write_text(text, encoding="utf-8", newline="\n")
    print("Cleanup source-note rewrite repaired.")


if __name__ == "__main__":
    main()

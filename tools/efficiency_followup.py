#!/usr/bin/env python3
"""Apply non-autofixable PEP 8 import-order repairs for the campaign."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _replace_once(relative: str, old: str, new: str) -> None:
    """Replace one exact fragment and fail if source drifted."""
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{relative}: import-order target is not unique")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def main() -> None:
    """Move six intentionally delayed test imports into PEP 8 import position."""
    _replace_once(
        "tests/test_comparison_export.py",
        '''

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"

from work.clean_rebuild import export_bilingual_comparison as comparison  # noqa: E402
''',
        '''
from work.clean_rebuild import export_bilingual_comparison as comparison


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
''',
    )
    _replace_once(
        "tests/test_ellipsis_style.py",
        '''

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"

from work.clean_rebuild.renderer_format import (  # noqa: E402
    normalize_ellipsis_style,
    reconstruct_wrapped_text,
    wrap_words,
)
from work.clean_rebuild.scn_layout import Layout  # noqa: E402
from work.clean_rebuild.translation_formatter import _renderer_boundary_failures  # noqa: E402
from work.clean_rebuild.scn_layout import RecordContract  # noqa: E402
from work.clean_rebuild.font_render import _bytes_matrix, render_compact_cluster  # noqa: E402
''',
        '''
from work.clean_rebuild.font_render import _bytes_matrix, render_compact_cluster
from work.clean_rebuild.renderer_format import (
    normalize_ellipsis_style,
    reconstruct_wrapped_text,
    wrap_words,
)
from work.clean_rebuild.scn_layout import Layout, RecordContract
from work.clean_rebuild.translation_formatter import _renderer_boundary_failures


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
''',
    )
    _replace_once(
        "tests/test_renderer_boundary_audit.py",
        '''

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"

from work.clean_rebuild.scn_layout import Layout, RecordContract  # noqa: E402
from work.clean_rebuild import mes_compiler  # noqa: E402
from work.clean_rebuild import translation_formatter  # noqa: E402
''',
        '''
from work.clean_rebuild import mes_compiler, translation_formatter
from work.clean_rebuild.scn_layout import Layout, RecordContract


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
''',
    )
    _replace_once(
        "tests/test_review_exports.py",
        '''

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
SOURCES = CLEAN / "sources"
EVIDENCE = CLEAN / "bomb_semantics.json"

from work.clean_rebuild import export_fixed_layout_review as fixed_review  # noqa: E402
''',
        '''
from work.clean_rebuild import export_fixed_layout_review as fixed_review


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
SOURCES = CLEAN / "sources"
EVIDENCE = CLEAN / "bomb_semantics.json"
''',
    )
    _replace_once(
        "tests/test_verification_manifest.py",
        '''

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"

from work.clean_rebuild import verification_manifest as provenance  # noqa: E402
''',
        '''
from work.clean_rebuild import verification_manifest as provenance


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
''',
    )


if __name__ == "__main__":
    main()

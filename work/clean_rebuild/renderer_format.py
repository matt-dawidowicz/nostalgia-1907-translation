#!/usr/bin/env python3
"""Share semantic normalization and SCN-aware prose wrapping.

The compiler and review formatter must not maintain independent ideas of a
safe renderer row. This module owns semantic whitespace normalization,
ellipsis style, visible-cell measurement, word wrapping, row reconstruction,
and token-boundary validation. It does not encode MES bytes or infer SCN
contracts; callers supply a proven :class:`scn_layout.Layout`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from scn_layout import Layout


ELLIPSIS_CAPITALIZED_FOLLOWERS = frozenset(
    (
        "Ashby",
        "Bartender",
        "Betty",
        "Britain",
        "Britain's",
        "Braque's",
        "Charlie",
        "Chief",
        "I",
        "I'll",
        "I'm",
        "I've",
        "Ilyu",
        "ITO",
        "Japanese",
        "Japan",
        "Kasuke",
        "Mr",
        "Navigator",
        "Nostalgia",
        "Tainui",
        "Tsar",
        "Voysey",
        "Voysey's",
        "Yamada",
    )
)
ELLIPSIS_FOLLOWER = re.compile(
    r"\.\.\.(?P<gap>[ \t]*)(?P<newline>\r?\n)?"
    r"(?P<quote>[\"']?)(?P<word>[A-Za-z0-9][A-Za-z0-9'-]*)"
)


def measure_literal(text: str) -> int:
    """Return the number of two-character cells used by one visible row."""
    return (len(text) + 1) // 2


def normalize_semantic_text(text: str) -> str:
    """Remove legacy line wrapping while preserving the English wording."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_ellipsis_style(text: str) -> str:
    """Remove post-ellipsis spaces and lower ordinary following words.

    The translation's dialogue style treats an ellipsis as an attached pause:
    ``"Wait... What?"`` becomes ``"Wait...what?"``. Names, proper adjectives,
    direct-address titles, acronyms, and grammatical first-person forms retain
    their established capitalization through an explicit reviewed exception
    set. Fixed-layout newlines and preceding row padding are retained.

    Args:
        text: Canonical English in adaptive or explicit fixed layout.

    Returns:
        Text with spaces after an ellipsis removed and ordinary followers
        lowercased.
    """

    def replace(match: re.Match[str]) -> str:
        """Rewrite one ellipsis boundary while retaining fixed row padding."""
        gap = match.group("gap") if match.group("newline") else ""
        newline = match.group("newline") or ""
        quote = match.group("quote")
        word = match.group("word")
        follower = word if word in ELLIPSIS_CAPITALIZED_FOLLOWERS else word.lower()
        return f"...{gap}{newline}{quote}{follower}"

    return ELLIPSIS_FOLLOWER.sub(replace, text)


def _ellipsis_atoms(source_word: str) -> tuple[str, ...]:
    """Split one whitespace token at style-approved zero-space ellipses."""
    parts = source_word.split("...")
    if len(parts) == 1:
        return (source_word,)
    atoms = [f"{part}..." for part in parts[:-1]]
    if parts[-1]:
        atoms.append(parts[-1])
    return tuple(atom for atom in atoms if atom)


def reconstruct_wrapped_text(rows: Sequence[str]) -> str:
    """Rebuild semantic prose without restoring spaces after ellipses."""
    if not rows:
        return ""
    rebuilt = rows[0]
    for row in rows[1:]:
        rebuilt += "" if rebuilt.endswith("...") else " "
        rebuilt += row
    return normalize_semantic_text(rebuilt)


def wrap_words(text: str, layout: Layout) -> list[str]:
    """Wrap prose at spaces or ellipses using the proven visible geometry.

    Ordinary words remain indivisible. A token that cannot fit in an empty
    renderer row is split only so the caller can report an exact semantic
    boundary failure rather than hanging or truncating. Production compilation
    rejects that result through :func:`wrapped_row_failures`.
    """
    rows: list[str] = []
    for paragraph in text.split("\n"):
        source_words = paragraph.split()
        if not source_words:
            rows.append("")
            continue
        current = ""
        for word_index, source_word in enumerate(source_words):
            atoms = _ellipsis_atoms(source_word)
            for atom_index, atom in enumerate(atoms):
                separator = " " if word_index and atom_index == 0 else ""
                remainder = atom
                while remainder:
                    row_index = len(rows)
                    cells = layout.visible_cells(row_index)
                    if current:
                        candidate = f"{current}{separator}{remainder}"
                        if measure_literal(candidate) <= cells:
                            current = candidate
                            remainder = ""
                        else:
                            rows.append(current)
                            current = ""
                        continue
                    if measure_literal(remainder) <= cells:
                        current = remainder
                        remainder = ""
                        continue
                    maximum_chars = cells * 2
                    rows.append(remainder[:maximum_chars])
                    remainder = remainder[maximum_chars:]
        if current:
            rows.append(current)
    return rows


def renderer_tokens(text: str) -> list[str]:
    """Return lexical tokens while treating an ellipsis as a soft row edge."""
    return re.sub(r"\.\.\.(?=\S)", "... ", text).split()


def wrapped_row_failures(
    semantic: str,
    rows: Sequence[str],
    layout: Layout,
) -> list[str]:
    """Return semantic or geometric failures in visible renderer rows.

    This is the authoritative shared guard used by both review previews and
    MES compilation. A safe result reconstructs the exact normalized semantic
    string, preserves every source token whole and in order, and fits every
    row inside the SCN-derived visible-cell capacity.
    """
    failures: list[str] = []
    rebuilt = reconstruct_wrapped_text(rows)
    source_tokens = renderer_tokens(semantic)
    rendered_tokens = [token for row in rows for token in renderer_tokens(row)]
    if source_tokens != rendered_tokens:
        mismatch = next(
            (
                index
                for index, (source, rendered) in enumerate(
                    zip(source_tokens, rendered_tokens, strict=False)
                )
                if source != rendered
            ),
            min(len(source_tokens), len(rendered_tokens)),
        )
        source_token = (
            source_tokens[mismatch] if mismatch < len(source_tokens) else "<end>"
        )
        rendered_token = (
            rendered_tokens[mismatch] if mismatch < len(rendered_tokens) else "<end>"
        )
        failures.append(
            "renderer row boundary splits or alters source token "
            f"{mismatch + 1}: {source_token!r} -> {rendered_token!r}"
        )
    elif rebuilt != semantic:
        failures.append("wrapped rows do not reconstruct the semantic text")

    for row_index, row in enumerate(rows):
        permitted_cells = layout.visible_cells(row_index)
        used_cells = measure_literal(row)
        if used_cells > permitted_cells:
            failures.append(
                f"row {row_index + 1} uses {used_cells} visible cells; "
                f"renderer permits {permitted_cells}"
            )
    return failures

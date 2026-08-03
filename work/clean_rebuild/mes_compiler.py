#!/usr/bin/env python3
"""Compile one canonical chapter into a structurally valid MES container.

The compiler joins three authorities: retail MES supplies record count,
preserved bytes, and retained glyphs; retail SCN supplies renderer contracts;
canonical JSON supplies record policy and English. It never inserts, deletes,
or reorders a record.

Adaptive records are normalized to semantic text, wrapped against the visible
SCN-derived geometry, and padded to the engine's runtime stride. Fixed records
retain explicit source layout. English characters become deterministic 12x12
cells, identical cells share dynamic glyphs, and preserved records keep their
retail glyph bitmaps through index remapping.

The output is rejected if it violates a retail hash guard, record policy,
renderer row limit, 16-bit pointer range, runtime dynamic-glyph capacity, or the
proven PART3C hard boundary. The result is parsed again before it is returned.

See ``docs/ARCHITECTURE.md`` for pipeline ownership and
``docs/BINARY_FORMATS.md`` for MES/font encoding.
"""

from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from font_render import GLYPH_BYTES, stored_cell, validate_text
from mes_format import DYNAMIC_PREFIX_START, MesFormatError, parse_mes
from scn_layout import (
    LABEL_ROLES,
    PROSE_ROLES,
    ROLE_CHOICE,
    Layout,
    infer_contracts,
    infer_layouts,
    infer_roles,
    infer_row_limits,
)


DYNAMIC_GLYPHS_PER_PREFIX = 0xFF
RUNTIME_DYNAMIC_GLYPH_LIMIT = 1020
PART3C_HARD_LIMIT = 0x3FFF
FIXED_BLANK_CELL_CODE = 0x48
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
FIXED_ENGLISH_UNITS = (
    # These cells form a shared English dictionary, not a chapter-specific
    # workaround.  Each one is a display-identical 12x12 cell installed in an
    # otherwise unused fixed-font slot.  One-byte references let every chapter
    # retain a left-aligned pair phase without paying a two-byte dynamic
    # reference for common cells.  The chosen codes are checked against every
    # preserved retail record by the integration suite before a build is made.
    (0x02, "literal", " c"), (0x03, "literal", " s"),
    (0x04, "literal", " o"), (0x05, "literal", "on"),
    (0x06, "literal", "li"), (0x08, "literal", ","),
    (0x84, "literal", "nd"), (0x47, "literal", "ss"),
    (0x23, "literal", "in"),
    # Shared opaque-position spacer. The compiler verifies that translated
    # chapters do not collide with a byte-preserved retail use of this slot.
    (FIXED_BLANK_CELL_CODE, "literal", "  "),
    (0x40, "literal", " y"), (0x1F, "literal", "ou"),
    (0x19, "literal", "no"), (0x36, "literal", "an"),
    (0x1B, "literal", "ng"), (0x41, "literal", "t "),
    (0x2D, "literal", " a"), (0x0A, "literal", " t"),
    (0x44, "literal", "he"), (0x8D, "literal", " i"),
    (0xB6, "literal", "it"), (0x1A, "literal", "s"),
    (0x4B, "literal", "ar"), (0x87, "literal", "e "),
    (0x8A, "literal", "is"), (0x50, "literal", "er"),
    (0x2E, "literal", ". "), (0x4E, "literal", "Th"),
    (0x43, "literal", "th"), (0x25, "literal", "en"),
    (0xE4, "literal", "r "), (0x51, "literal", "d "),
    (0x33, "literal", "yo"), (0x4A, "literal", "u "),
    (0x3B, "literal", "ri"), (0x46, "literal", "me"),
    (0x3E, "literal", "? "), (0xBE, "literal", " I"),
    (0x3A, "literal", " w"), (0x3F, "literal", "n "),
    (0x45, "literal", "wi"), (0xA5, "literal", "I "),
    (0xD2, "literal", "st"), (0x35, "compact", "..."),
    (0x0D, "literal", "at"), (0x37, "literal", "ll"),
    (0x4F, "literal", " m"), (0x42, "literal", "y "),
    (0xBC, "literal", "ve"), (0x39, "literal", "re"),
    (0x27, "literal", "te"), (0x3D, "literal", "o "),
    (0x09, "literal", "g"), (0x0B, "literal", ".."),
    (0x0C, "literal", "hi"), (0x0E, "literal", "le"),
    (0x0F, "literal", "ha"), (0x11, "literal", "to"),
    (0x12, "literal", "co"), (0x13, "literal", "l"),
    (0x14, "literal", "be"), (0x15, "literal", "or"),
    (0x16, "literal", "de"), (0x17, "literal", "ot"),
    (0x18, "literal", "Yo"), (0x1C, "literal", "ca"),
    (0x1D, "literal", "si"), (0x1E, "literal", "ed"),
    (0x20, "literal", " n"), (0x21, "literal", "Ru"),
    (0x22, "literal", "ia"), (0x24, "literal", "as"),
    (0x26, "literal", "es"), (0x28, "literal", " b"),
    (0x29, "literal", "a"), (0x2A, "literal", "se"),
    (0x2B, "literal", "ow"), (0x2C, "literal", "e."),
    (0x2F, "literal", "el"), (0x30, "literal", "sh"),
    (0x31, "literal", "fe"), (0x32, "literal", "nt"),
    (0x34, "literal", "ti"), (0x38, "literal", "ct"),
    (0x3C, "literal", "ly"), (0x49, "literal", "al"),
    (0x4C, "literal", "ea"), (0x4D, "literal", " e"),
    (0x52, "literal", "io"), (0x53, "literal", "ry"),
    (0x54, "literal", "Wh"), (0x55, "literal", "wh"),
    (0x56, "literal", "rs"), (0x57, "literal", " f"),
    (0x58, "literal", "Fo"), (0x59, "literal", " l"),
    (0x5A, "literal", "wa"), (0x5B, "literal", "do"),
    (0x5C, "literal", "il"), (0x5D, "literal", "tr"),
    (0x5E, "literal", " k"), (0x5F, "literal", "w"),
    (0x60, "literal", "ur"), (0x61, "literal", "ne"),
    (0x62, "literal", "us"), (0x63, "literal", "pe"),
    (0x64, "literal", " d"), (0x65, "literal", "ab"),
    (0x66, "literal", "ce"), (0x67, "literal", "ke"),
    (0x68, "literal", "ai"), (0x69, "literal", "am"),
)


class CompileError(ValueError):
    """Raised when canonical text cannot be compiled within runtime limits."""


@dataclass(frozen=True)
class BuildResult:
    """Compiled bytes and the measurements required by regression checks."""

    data: bytes
    record_count: int
    translated_records: int
    preserved_records: int
    split_offset: int
    dynamic_glyphs: int
    rendered_cells: int
    scn_layout_records: int
    fixed_spill_count: int
    fixed_spill_occurrences: int
    fixed_font_patches: tuple[tuple[int, str], ...]
    glyph_order: str


Cell = tuple[str, str]
BLANK_CELL: Cell = ("literal", "  ")


# Text normalization, wrapping, and cell planning. These functions operate on
# semantic English and renderer contracts; they do not write MES bytes.


@dataclass
class RowPlan:
    """One left-aligned runtime row.

    ``alternate`` remains part of the compact-row optimizer's data contract,
    but normal compilation deliberately leaves it unavailable. A former
    shifted packing alternative placed a literal blank before the first source
    character. It improved glyph reuse but visibly indented selected rows, so
    display position takes priority over that storage optimization.
    """

    record: int
    prefix: tuple[Cell, ...]
    primary: tuple[Cell, ...]
    alternate: tuple[Cell, ...] | None
    selected_alternate: bool = False

    def cells(self) -> tuple[Cell, ...]:
        """Return the currently selected complete row."""
        body = self.alternate if self.selected_alternate else self.primary
        if body is None:
            raise CompileError("row selected a missing alternate phase")
        return self.prefix + body


def _dynamic_code(index: int) -> bytes:
    """Encode one zero-based dynamic glyph index."""
    if not 0 <= index < 16 * DYNAMIC_GLYPHS_PER_PREFIX:
        raise CompileError(f"dynamic glyph index {index} is not encodable")
    return bytes(
        (
            DYNAMIC_PREFIX_START + index // DYNAMIC_GLYPHS_PER_PREFIX,
            index % DYNAMIC_GLYPHS_PER_PREFIX + 1,
        )
    )


def _remap_preserved(record: bytes, mapping: dict[int, int]) -> bytes:
    """Remap dynamic references in a byte-preserved retail record."""
    output = bytearray()
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value < DYNAMIC_PREFIX_START:
            output.append(value)
            offset += 1
            continue
        if offset + 1 >= len(record) or record[offset + 1] == 0:
            raise CompileError("preserved record has a truncated dynamic reference")
        old_index = (value - DYNAMIC_PREFIX_START) * 0xFF + record[offset + 1] - 1
        if old_index not in mapping:
            raise CompileError(f"preserved dynamic glyph {old_index} was not retained")
        output.extend(_dynamic_code(mapping[old_index]))
        offset += 2
    return bytes(output)


def _measure_literal(text: str) -> int:
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
    set. Fixed-layout newlines and any preceding row padding are retained as
    renderer-owned boundaries, while the following ordinary word is still
    normalized.

    Args:
        text: Canonical English text in adaptive or explicit fixed layout.

    Returns:
        The same text with spaces after an ellipsis removed and ordinary next
        words lowercased.

    Side Effects:
        None.
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
    """Split one whitespace token at style-approved zero-space ellipses.

    An ellipsis can join two semantic words without a literal space, yet it is
    still a safe renderer row boundary. Each returned atom retains the
    ellipsis on the preceding text so the compiled bitmap never gains a space.

    Args:
        source_word: One non-whitespace portion of canonical English.

    Returns:
        One or more nonempty, renderable atoms in source order.

    Side Effects:
        None.
    """
    parts = source_word.split("...")
    if len(parts) == 1:
        return (source_word,)
    atoms = [f"{part}..." for part in parts[:-1]]
    if parts[-1]:
        atoms.append(parts[-1])
    return tuple(atom for atom in atoms if atom)


def _reconstruct_wrapped_text(rows: list[str]) -> str:
    """Rebuild semantic prose from formatter rows without restoring ellipse gaps.

    Ordinary renderer row boundaries represent a source space. A boundary
    immediately after ``...`` instead represents the approved zero-space pause
    style, so it must not reintroduce a space during audit reconstruction.

    Args:
        rows: Visible, unpadded formatter rows in display order.

    Returns:
        Normalized semantic English represented by the rows.

    Side Effects:
        None.
    """
    if not rows:
        return ""
    rebuilt = rows[0]
    for row in rows[1:]:
        rebuilt += "" if rebuilt.endswith("...") else " "
        rebuilt += row
    return normalize_semantic_text(rebuilt)


def _wrap_words(text: str, layout: Layout) -> list[str]:
    """Wrap prose at spaces or ellipses without fragmenting ordinary words.

    A row break after an ellipsis is legal even though the canonical style
    deliberately omits a following space. Any other source word remains
    indivisible unless it exceeds a complete renderer row by itself.
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
                        if _measure_literal(candidate) <= cells:
                            current = candidate
                            remainder = ""
                        else:
                            rows.append(current)
                            current = ""
                        continue
                    if _measure_literal(remainder) <= cells:
                        current = remainder
                        remainder = ""
                        continue
                    maximum_chars = cells * 2
                    rows.append(remainder[:maximum_chars])
                    remainder = remainder[maximum_chars:]
        if current:
            rows.append(current)
    return rows


def _compact_cluster(unit: str) -> bool:
    """Return whether three source characters safely share one cell."""
    return (
        unit == "..."
        or (
            len(unit) == 3
            and unit[1] == "'"
            and unit[0].isalpha()
            and unit[2].isalpha()
        )
        or (
            len(unit) == 3
            and unit[1] == "."
            and unit[0].isdigit()
            and unit[2].isdigit()
        )
    )


def _pack_row(line: str) -> tuple[int, tuple[Cell, ...]] | None:
    """Pack one left-aligned row with safe punctuation clusters.

    The first source character must occupy the first visible character slot.
    Punctuation compression may reduce storage only within that fixed visual
    placement; it must never introduce a leading blank to change pair phase.
    """
    cell_count = (len(line) + 1) // 2
    packed = line
    start = 0

    cache: dict[int, tuple[int, tuple[Cell, ...]]] = {}

    def best(index: int) -> tuple[int, tuple[Cell, ...]]:
        """Return the best deterministic cell packing from ``index`` onward."""
        if index >= len(packed):
            return 0, ()
        if index in cache:
            return cache[index]
        pair = packed[index : index + 2]
        score, remainder = best(index + len(pair))
        choices = [(score, (("literal", pair),) + remainder)]
        cluster = packed[index : index + 3]
        if _compact_cluster(cluster):
            cluster_score, cluster_remainder = best(index + 3)
            choices.append(
                (
                    cluster_score + 1,
                    (("compact", cluster),) + cluster_remainder,
                )
            )
        result = max(choices, key=lambda item: (item[0], -len(item[1])))
        cache[index] = result
        return result

    punctuation_count, suffix = best(start)
    units = suffix
    if len(units) > cell_count:
        return None
    units += (("literal", "  "),) * (cell_count - len(units))
    return punctuation_count, units


def _row_plan(record: int, line: str, prefix: tuple[Cell, ...] = ()) -> RowPlan:
    """Build one position-preserving packed row for the runtime renderer."""
    packed = _pack_row(line)
    if packed is None:
        return RowPlan(record, prefix, (), None)
    return RowPlan(
        record=record,
        prefix=prefix,
        primary=packed[1],
        alternate=None,
    )


def _prose_rows(text: str, layout: Layout | None) -> list[tuple[tuple[Cell, ...], str]]:
    """Wrap prose with any native one-time lower-dialogue gutter preserved."""
    if layout is None:
        return [((), line) for line in text.split("\n")]
    rows = _wrap_words(text, layout)
    output: list[tuple[tuple[Cell, ...], str]] = []
    for row_index, row in enumerate(rows):
        runtime_cells = layout.runtime_cells(row_index)
        if _measure_literal(row) > runtime_cells:
            raise CompileError(
                f"wrapped row {row!r} exceeds runtime stride {runtime_cells}"
            )
        padded = row.ljust(runtime_cells * 2)
        prefix = (BLANK_CELL,) * layout.anchor_cells(row_index)
        output.append((prefix, padded))
    return output


def _optimize_phases(
    rows: list[RowPlan],
    retained_glyphs: list[bytes],
    fixed_by_bitmap: dict[bytes, int],
) -> None:
    """Choose row phases that minimize actual record-plus-glyph-tail bytes."""
    retained = set(retained_glyphs)
    row_glyphs = {
        id(row): (
            Counter(stored_cell(*cell) for cell in row.primary),
            (
                Counter(stored_cell(*cell) for cell in row.alternate)
                if row.alternate is not None
                else None
            ),
        )
        for row in rows
    }

    def byte_cost(references: Counter[bytes]) -> int:
        """Measure encoded references plus newly required dynamic glyph bytes."""
        record_bytes = sum(
            count * (1 if glyph in fixed_by_bitmap else 2)
            for glyph, count in references.items()
        )
        dynamic_glyphs = sum(
            glyph not in fixed_by_bitmap or glyph in retained for glyph in references
        )
        return record_bytes + dynamic_glyphs * GLYPH_BYTES

    def subtract(references: Counter[bytes], values: Counter[bytes]) -> None:
        """Remove one row's multiset from the mutable global reference count."""
        for glyph, count in values.items():
            remaining = references[glyph] - count
            if remaining:
                references[glyph] = remaining
            else:
                del references[glyph]

    best_cost: int | None = None
    best_selection: tuple[bool, ...] | None = None
    for start_alternate, reverse in (
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    ):
        for row in rows:
            row.selected_alternate = start_alternate and row.alternate is not None
        references: Counter[bytes] = Counter(retained_glyphs)
        for row in rows:
            primary, alternate = row_glyphs[id(row)]
            references.update(alternate if row.selected_alternate else primary)
        ordered_rows = list(reversed(rows)) if reverse else rows
        while True:
            changed = False
            for row in ordered_rows:
                primary, alternate = row_glyphs[id(row)]
                if alternate is None:
                    continue
                current = alternate if row.selected_alternate else primary
                candidate = primary if row.selected_alternate else alternate
                before = byte_cost(references)
                subtract(references, current)
                references.update(candidate)
                if byte_cost(references) < before:
                    row.selected_alternate = not row.selected_alternate
                    changed = True
                else:
                    subtract(references, candidate)
                    references.update(current)
            if not changed:
                break
        final_cost = byte_cost(references)
        selection = tuple(row.selected_alternate for row in rows)
        if best_cost is None or (final_cost, selection) < (best_cost, best_selection):
            best_cost = final_cost
            best_selection = selection
    if best_selection is None:
        raise CompileError("row phase optimizer produced no candidate")
    for row, selected in zip(rows, best_selection):
        row.selected_alternate = selected


def compile_mes(
    retail_data: bytes,
    scn_data: bytes,
    canonical: dict[str, object],
    *,
    glyph_order: str = "first-use",
) -> BuildResult:
    """Compile one canonical chapter against hash-locked retail MES and SCN.

    The returned :class:`BuildResult` contains both bytes and capacity metrics
    used by later regression stages. No input mapping or byte string is
    modified in place.
    """
    chapter = canonical.get("chapter")
    if not isinstance(chapter, str):
        raise CompileError("canonical source has no chapter name")
    if glyph_order not in {"first-use", "bitmap", "frequency"}:
        raise CompileError(f"unsupported dynamic glyph order {glyph_order!r}")
    retail = parse_mes(retail_data, source=f"retail {chapter}")
    retail_guard = canonical.get("retail_mes")
    scn_guard = canonical.get("retail_scn")
    if not isinstance(retail_guard, dict) or not isinstance(scn_guard, dict):
        raise CompileError(f"{chapter}: canonical retail hash guards are missing")
    actual_mes_hash = hashlib.sha256(retail_data).hexdigest().upper()
    actual_scn_hash = hashlib.sha256(scn_data).hexdigest().upper()
    if retail_guard.get("size") != len(retail_data) or retail_guard.get("sha256") != actual_mes_hash:
        raise CompileError(f"{chapter}: retail MES does not match the canonical hash guard")
    if scn_guard.get("size") != len(scn_data) or scn_guard.get("sha256") != actual_scn_hash:
        raise CompileError(f"{chapter}: retail SCN does not match the canonical hash guard")
    if canonical.get("record_count") != retail.record_count:
        raise CompileError(f"{chapter}: canonical and retail record counts disagree")
    raw_records = canonical.get("records")
    if not isinstance(raw_records, list) or len(raw_records) != retail.record_count:
        raise CompileError(f"{chapter}: canonical record table is incomplete")
    text_mode = canonical.get("text_mode")
    if text_mode not in {"render-ready", "prose", "adaptive", "preserve"}:
        raise CompileError(f"{chapter}: invalid text mode {text_mode!r}")

    translated: dict[int, str] = {}
    adaptive_indexes: set[int] = set()
    preserved: set[int] = set()
    for expected_index, record in enumerate(raw_records):
        if not isinstance(record, dict) or record.get("index") != expected_index:
            raise CompileError(f"{chapter}: canonical record indexes are not contiguous")
        policy = record.get("policy")
        if policy == "translate" and isinstance(record.get("text"), str):
            translated[expected_index] = record["text"]
            validate_text(record["text"])
            layout_policy = record.get("layout_policy")
            if layout_policy not in {None, "legacy", "fixed", "adaptive"}:
                raise CompileError(
                    f"{chapter}:{expected_index:03d} has invalid layout policy"
                )
            if layout_policy == "adaptive":
                adaptive_indexes.add(expected_index)
        elif policy == "preserve" and record.get("text") is None:
            preserved.add(expected_index)
        else:
            raise CompileError(f"{chapter}: invalid record policy at {expected_index}")
    if set(range(retail.record_count)) != set(translated) | preserved:
        raise CompileError(f"{chapter}: every record must have exactly one policy")
    if not translated and len(preserved) == retail.record_count:
        return BuildResult(
            data=retail_data,
            record_count=retail.record_count,
            translated_records=0,
            preserved_records=retail.record_count,
            split_offset=retail.split_offset,
            dynamic_glyphs=len(retail.glyphs),
            rendered_cells=0,
            scn_layout_records=0,
            fixed_spill_count=0,
            fixed_spill_occurrences=0,
            fixed_font_patches=(),
            glyph_order="retail-preserved",
        )

    profile = canonical.get("profile")
    if profile is not None and not isinstance(profile, dict):
        raise CompileError(f"{chapter}: embedded profile is invalid")
    if text_mode == "adaptive":
        adaptive_indexes = set(translated)
    needs_layouts = text_mode == "prose" or bool(adaptive_indexes)
    layouts = (
        infer_layouts(
            scn_data,
            retail.record_count,
            set(translated),
            profile,
            retail_records=retail.records,
        )
        if needs_layouts
        else {}
    )
    roles = (
        infer_roles(scn_data, retail.record_count, set(translated), profile)
        if adaptive_indexes
        else {}
    )
    row_limits = (
        infer_row_limits(scn_data, retail.record_count, set(translated), profile)
        if adaptive_indexes
        else {}
    )
    retained_indexes = sorted(
        index
        for record_index in preserved
        for index in _dynamic_indexes(retail.records[record_index])
    )
    retained_indexes = sorted(set(retained_indexes))
    old_to_new = {old: new for new, old in enumerate(retained_indexes)}
    glyphs = [retail.glyphs[index] for index in retained_indexes]
    bitmap_to_index = {bitmap: index for index, bitmap in enumerate(glyphs)}
    row_plans: list[RowPlan] = []
    rows_by_record: dict[int, list[RowPlan]] = {index: [] for index in translated}
    for index, text in sorted(translated.items()):
        adaptive_record = index in adaptive_indexes
        if text_mode == "render-ready" and not adaptive_record:
            row_specs = [((), line) for line in text.split("\n")]
        else:
            working = text
            if adaptive_record:
                record_roles = roles.get(index, frozenset())
                if layouts.get(index) is not None or record_roles & (
                    PROSE_ROLES | LABEL_ROLES | {ROLE_CHOICE}
                ):
                    working = normalize_ellipsis_style(normalize_semantic_text(text))
            row_specs = _prose_rows(working, layouts.get(index))
        max_rows = row_limits.get(index) if adaptive_record else None
        if max_rows is not None and len(row_specs) > max_rows:
            raise CompileError(
                f"{chapter}:{index:03d} uses {len(row_specs)} rows in a "
                f"floating window with a {max_rows}-row limit"
            )
        for prefix, line in row_specs:
            plan = _row_plan(index, line, prefix)
            row_plans.append(plan)
            rows_by_record[index].append(plan)
    fixed_by_bitmap: dict[bytes, int] = {}
    patches: list[tuple[int, str]] = []
    preserved_fixed_codes = {
        value
        for record_index in preserved
        for value in retail.records[record_index]
        if 1 <= value < DYNAMIC_PREFIX_START
    }
    for code, style, unit in FIXED_ENGLISH_UNITS:
        if code in preserved_fixed_codes:
            raise CompileError(
                f"{chapter}: fixed English code 0x{code:02X} is used by a "
                "byte-preserved retail record"
            )
        bitmap = stored_cell(style, unit)
        previous = fixed_by_bitmap.get(bitmap)
        if previous is not None and previous != code:
            raise CompileError(
                f"fixed English dictionary aliases codes 0x{previous:02X} and 0x{code:02X}"
            )
        fixed_by_bitmap[bitmap] = code
        patches.append((code, bitmap.hex().upper()))
    fixed_font_patches = tuple(patches)
    _optimize_phases(row_plans, glyphs, fixed_by_bitmap)

    generated_frequency: Counter[bytes] = Counter(
        stored_cell(*cell)
        for row in row_plans
        for cell in row.cells()
        if stored_cell(*cell) not in fixed_by_bitmap
    )
    generated_first_use: list[bytes] = []
    seen_generated = set(glyphs)
    for row in row_plans:
        for cell in row.cells():
            bitmap = stored_cell(*cell)
            if bitmap in fixed_by_bitmap or bitmap in seen_generated:
                continue
            seen_generated.add(bitmap)
            generated_first_use.append(bitmap)
    if glyph_order == "first-use":
        generated = generated_first_use
    elif glyph_order == "bitmap":
        generated = sorted(generated_first_use)
    else:
        generated = sorted(
            generated_first_use,
            key=lambda bitmap: (-generated_frequency[bitmap], bitmap),
        )
    glyphs.extend(generated)
    bitmap_to_index = {bitmap: index for index, bitmap in enumerate(glyphs)}

    output_records: list[bytes] = []
    rendered_cells = 0
    fixed_spill_occurrences = 0
    for index in range(retail.record_count):
        if index in preserved:
            output_records.append(_remap_preserved(retail.records[index], old_to_new))
            continue
        units = [cell for row in rows_by_record[index] for cell in row.cells()]
        rendered_cells += len(units)
        encoded = bytearray()
        for unit in units:
            bitmap = stored_cell(*unit)
            fixed_code = fixed_by_bitmap.get(bitmap)
            if fixed_code is not None:
                encoded.append(fixed_code)
                fixed_spill_occurrences += 1
                continue
            dynamic_index = bitmap_to_index.get(bitmap)
            if dynamic_index is None:
                raise CompileError("generated glyph was absent from the ordered bank")
            encoded.extend(_dynamic_code(dynamic_index))
        encoded.append(0)
        output_records.append(bytes(encoded))

    if len(glyphs) > RUNTIME_DYNAMIC_GLYPH_LIMIT:
        raise CompileError(
            f"{chapter}: {len(glyphs)} dynamic glyphs exceed the runtime limit "
            f"of {RUNTIME_DYNAMIC_GLYPH_LIMIT}"
        )
    first_pointer = 2 + retail.record_count * 2
    pointers: list[int] = []
    cursor = first_pointer
    for record in output_records:
        pointers.append(cursor)
        cursor += len(record)
    split_offset = cursor
    if split_offset > 0xFFFF or any(pointer > 0xFFFF for pointer in pointers):
        raise CompileError(f"{chapter}: MES pointer region exceeds 16-bit offsets")
    output = bytearray(split_offset + len(glyphs) * GLYPH_BYTES)
    output[:2] = split_offset.to_bytes(2, "big")
    for index, pointer in enumerate(pointers):
        output[2 + index * 2 : 4 + index * 2] = pointer.to_bytes(2, "big")
    cursor = first_pointer
    for record in output_records:
        output[cursor : cursor + len(record)] = record
        cursor += len(record)
    output[split_offset:] = b"".join(glyphs)
    parsed = parse_mes(bytes(output), source=f"compiled {chapter}")
    if parsed.record_count != retail.record_count or len(parsed.glyphs) != len(glyphs):
        raise CompileError(f"{chapter}: compiled MES self-check failed")
    if chapter == "PART3C" and len(output) > PART3C_HARD_LIMIT:
        raise CompileError(
            f"PART3C hard boundary exceeded: 0x{len(output):X} > 0x{PART3C_HARD_LIMIT:X}"
        )
    return BuildResult(
        data=bytes(output),
        record_count=retail.record_count,
        translated_records=len(translated),
        preserved_records=len(preserved),
        split_offset=split_offset,
        dynamic_glyphs=len(glyphs),
        rendered_cells=rendered_cells,
        scn_layout_records=len(layouts),
        fixed_spill_count=len(fixed_by_bitmap),
        fixed_spill_occurrences=fixed_spill_occurrences,
        fixed_font_patches=fixed_font_patches,
        glyph_order=glyph_order,
    )


def _dynamic_indexes(record: bytes) -> set[int]:
    """Return dynamic glyph indexes referenced by one validated record."""
    indexes: set[int] = set()
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value < DYNAMIC_PREFIX_START:
            offset += 1
            continue
        if offset + 1 >= len(record) or record[offset + 1] == 0:
            raise MesFormatError("invalid dynamic reference in preserved record")
        indexes.add((value - DYNAMIC_PREFIX_START) * 0xFF + record[offset + 1] - 1)
        offset += 2
    return indexes


def compile_files(
    retail_mes_path: Path,
    retail_scn_path: Path,
    canonical_path: Path,
    output_path: Path,
    *,
    glyph_order: str = "first-use",
) -> BuildResult:
    """Compile guarded file inputs and write one derived MES artifact.

    Retail MES/SCN and canonical JSON are read before calling ``compile_mes``.
    The returned bytes are written only after all compiler checks succeed.

    Side Effects:
        Creates the output parent directory and replaces ``output_path``.
        Retail and canonical inputs remain read-only.
    """
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    result = compile_mes(
        retail_mes_path.read_bytes(),
        retail_scn_path.read_bytes(),
        canonical,
        glyph_order=glyph_order,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result.data)
    return result

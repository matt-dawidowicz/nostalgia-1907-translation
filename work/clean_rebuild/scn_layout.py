#!/usr/bin/env python3
"""Infer text roles and MES rendering contracts from retail SCN commands.

The game does not use one universal text box.  SCN commands select distinct
renderers for lower dialogue, continuation rows, floating thought/aside
windows, choices, and the two labels at the top of the scene UI.  Keeping the
role inference here gives the compiler and the translation editor one shared,
source-derived contract.

SCN operands refer to MES records with one-based IDs; every public result from
this module uses the zero-based canonical record index. Inference accepts only
complete command shapes with in-range IDs so operand bytes elsewhere in SCN are
not mistaken for opcodes. The SCN itself is read-only.

A :class:`Layout` separates visible width from runtime stride. The engine may
advance farther than the visibly usable cells, so the compiler wraps against
the visible width and pads against the runtime width. :class:`RecordContract`
combines that geometry with role and vertical row limit.

See ``docs/TRANSLATION_EDITING.md`` for policy ownership and
``docs/BINARY_FORMATS.md`` for the recognized SCN command shapes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profile_schema import canonical_profile_index


FLOATING_WIDTHS = {
    0x07: 4,
    0x08: 5,
    0x09: 5,
    0x0A: 5,
    0x0B: 6,
    0x0C: 7,
    0x0D: 7,
    0x0E: 8,
    0x0F: 8,
    0x10: 9,
    0x11: 9,
    0x12: 10,
}

ROLE_DIALOGUE = "main_dialogue"
ROLE_CONTINUATION = "dialogue_continuation"
ROLE_SPEAKER = "speaker_name"
ROLE_LOCATION = "location_name"
ROLE_PERSPECTIVE = "perspective_name"
ROLE_THOUGHT = "side_thought"
ROLE_OVERLAY = "overlay_text"
ROLE_NARRATION = "narration"
ROLE_CHOICE = "menu_choice"

# Text-box identity is as important as its measured width.  The compiler must
# never make a floating window, selector, or continuation record inherit the
# lower-dialogue cadence just because both happen to contain English prose.
TEXT_BOX_UNCLASSIFIED = "unclassified"
TEXT_BOX_LOWER_DIALOGUE = "lower_dialogue"
TEXT_BOX_LOWER_CONTINUATION = "lower_continuation"
TEXT_BOX_FLOATING = "floating_window"
TEXT_BOX_FULL_SCREEN_NARRATION = "full_screen_narration"
TEXT_BOX_LOWER_CAPTION = "lower_caption"
TEXT_BOX_SCENE_LABEL = "scene_label"
TEXT_BOX_IDS = frozenset(
    (
        TEXT_BOX_UNCLASSIFIED,
        TEXT_BOX_LOWER_DIALOGUE,
        TEXT_BOX_LOWER_CONTINUATION,
        TEXT_BOX_FLOATING,
        TEXT_BOX_FULL_SCREEN_NARRATION,
        TEXT_BOX_LOWER_CAPTION,
        TEXT_BOX_SCENE_LABEL,
    )
)

# Retail lower dialogue begins with this fixed Japanese opening-quote cell in
# almost every ordinary ``0x21`` dialogue record.  MAIN.BIN renders that first
# cell at X=$4A, then renders every later row at X=$56.  English must retain a
# one-time gutter there, otherwise its first letter becomes the persistent
# left-side glyph on every later page.
DIALOGUE_OPENING_ANCHOR_CODE = 0x10

LABEL_ROLES = frozenset((ROLE_SPEAKER, ROLE_LOCATION, ROLE_PERSPECTIVE))
PROSE_ROLES = frozenset(
    (ROLE_DIALOGUE, ROLE_CONTINUATION, ROLE_THOUGHT, ROLE_OVERLAY, ROLE_NARRATION)
)


class ScnLayoutError(ValueError):
    """Raised when SCN rendering commands assign unsafe layouts."""


@dataclass(frozen=True)
class Layout:
    """Visible cell capacity and engine stride for first/continuation rows.

    ``visible_*`` limits word wrapping. ``runtime_*`` controls padding in the
    flattened MES record and must never be smaller than its visible partner.
    ``page_rows`` describes the renderer's vertical page cadence. It does not
    imply that an X-coordinate/width reset happens at a later page start;
    ``repeat_first_row_on_page`` records that separately when native evidence
    proves it. A normal dialogue record may reserve ``opening_anchor_cells``
    once at the beginning of its stream. That anchor consumes part of row zero
    only.
    """

    visible_first: int
    visible_continuation: int
    runtime_first: int
    runtime_continuation: int
    page_rows: int | None = None
    repeat_first_row_on_page: bool = False
    opening_anchor_cells: int = 0
    text_box: str = TEXT_BOX_UNCLASSIFIED

    def __post_init__(self) -> None:
        """Reject invalid cell geometry before layout inference uses it."""
        widths = (
            self.visible_first,
            self.visible_continuation,
            self.runtime_first,
            self.runtime_continuation,
        )
        if any(width <= 0 for width in widths):
            raise ScnLayoutError("layout cell widths must be positive")
        if self.runtime_first < self.visible_first:
            raise ScnLayoutError("layout first-row stride is narrower than visibility")
        if self.runtime_continuation < self.visible_continuation:
            raise ScnLayoutError(
                "layout continuation stride is narrower than visibility"
            )
        if self.page_rows is not None and self.page_rows <= 0:
            raise ScnLayoutError("layout page_rows must be positive")
        if not isinstance(self.repeat_first_row_on_page, bool):
            raise ScnLayoutError("layout page-repeat flag must be boolean")
        if self.opening_anchor_cells < 0:
            raise ScnLayoutError("layout opening anchor cells must not be negative")
        if self.text_box not in TEXT_BOX_IDS:
            raise ScnLayoutError(f"unknown layout text-box identity {self.text_box!r}")
        if (
            self.opening_anchor_cells >= self.visible_first
            or self.opening_anchor_cells >= self.runtime_first
        ):
            raise ScnLayoutError(
                "layout opening anchor leaves no first-row prose cells"
            )

    def is_first_row(self, row_index: int) -> bool:
        """Return whether ``row_index`` uses the renderer's first-row geometry."""
        if row_index < 0:
            raise ScnLayoutError("layout row index must not be negative")
        return row_index == 0 or (
            self.repeat_first_row_on_page and self.is_page_start(row_index)
        )

    def is_page_start(self, row_index: int) -> bool:
        """Return whether ``row_index`` begins a later renderer page."""
        if row_index < 0:
            raise ScnLayoutError("layout row index must not be negative")
        return (
            self.page_rows is not None
            and row_index > 0
            and row_index % self.page_rows == 0
        )

    def anchor_cells(self, row_index: int) -> int:
        """Return the one-time initial gutter cells before prose begins."""
        if row_index < 0:
            raise ScnLayoutError("layout row index must not be negative")
        return self.opening_anchor_cells if row_index == 0 else 0

    def physical_cells(self, row_index: int) -> int:
        """Return all emitted cells, including a one-time opening gutter."""
        return self.runtime_cells(row_index) + self.anchor_cells(row_index)

    def cadence_rows(self) -> int:
        """Return the number of row shapes in one renderer page cycle."""
        return self.page_rows or 1

    def physical_cadence(self) -> tuple[int, ...]:
        """Return the emitted-cell cadence for one complete renderer cycle."""
        return tuple(self.physical_cells(row) for row in range(self.cadence_rows()))

    def visible_cadence(self) -> tuple[int, ...]:
        """Return prose capacities for one complete renderer cycle."""
        return tuple(self.visible_cells(row) for row in range(self.cadence_rows()))

    def visible_cells(self, row_index: int) -> int:
        """Return the proven visible capacity for one flattened row index."""
        cells = (
            self.visible_first
            if self.is_first_row(row_index)
            else self.visible_continuation
        )
        return cells - self.anchor_cells(row_index)

    def runtime_cells(self, row_index: int) -> int:
        """Return the engine stride for one flattened row index."""
        cells = (
            self.runtime_first
            if self.is_first_row(row_index)
            else self.runtime_continuation
        )
        return cells - self.anchor_cells(row_index)

    def with_opening_anchor(self, cells: int = 1) -> Layout:
        """Return a body-width layout with a one-time native dialogue gutter.

        The caller establishes from retail MES bytes that the original record
        begins with the opening-quote anchor. Its row-zero body therefore loses
        the same number of visible/runtime cells while its physical row length
        and every later row retains its independently declared geometry.
        """
        if cells <= 0:
            raise ScnLayoutError("layout opening anchor cells must be positive")
        if self.visible_first <= cells or self.runtime_first <= cells:
            raise ScnLayoutError(
                "layout opening anchor leaves no first-row prose cells"
            )
        return Layout(
            self.visible_first,
            self.visible_continuation,
            self.runtime_first,
            self.runtime_continuation,
            page_rows=self.page_rows,
            repeat_first_row_on_page=self.repeat_first_row_on_page,
            opening_anchor_cells=cells,
            text_box=self.text_box,
        )


@dataclass(frozen=True)
class RecordContract:
    """Structurally proven role, geometry, and row limit for one MES record.

    A missing layout does not mean the record is safe to wrap. It means no
    general reflow geometry has been proven; canonical data must then declare
    explicit fixed-layout ownership.
    """

    roles: frozenset[str]
    layout: Layout | None
    max_rows: int | None


def _pair(
    profile: dict[str, object], key: str, default: tuple[int, int]
) -> tuple[int, int]:
    """Read a positive first/continuation layout object."""
    raw = profile.get(key)
    if raw is None:
        return default
    if not isinstance(raw, dict):
        raise ScnLayoutError(f"profile {key} is not an object")
    first = raw.get("first")
    continuation = raw.get("continuation")
    if (
        not isinstance(first, int)
        or not isinstance(continuation, int)
        or first <= 0
        or continuation <= 0
    ):
        raise ScnLayoutError(f"profile {key} must contain positive widths")
    return first, continuation


def _indexed_pairs(profile: dict[str, object], key: str) -> dict[int, tuple[int, int]]:
    """Read record-indexed first/continuation width overrides."""
    raw = profile.get(key, {})
    if not isinstance(raw, dict):
        raise ScnLayoutError(f"profile {key} is not an object")
    output: dict[int, tuple[int, int]] = {}
    for raw_index, raw_layout in raw.items():
        try:
            index = canonical_profile_index(
                raw_index, field=key, chapter="SCN profile"
            )
        except ValueError as exc:
            raise ScnLayoutError(
                f"profile {key} has invalid record {raw_index!r}"
            ) from exc
        if index < 0 or not isinstance(raw_layout, dict):
            raise ScnLayoutError(f"profile {key} has invalid record {raw_index!r}")
        first = raw_layout.get("first")
        continuation = raw_layout.get("continuation")
        if (
            not isinstance(first, int)
            or not isinstance(continuation, int)
            or first <= 0
            or continuation <= 0
        ):
            raise ScnLayoutError(
                f"profile {key} record {index} must contain positive widths"
            )
        output[index] = (first, continuation)
    return output


def _indexed_text_boxes(profile: dict[str, object]) -> dict[int, str]:
    """Read reviewed identity overrides for nonstandard but known layouts."""
    raw = profile.get("text_box_overrides", {})
    if not isinstance(raw, dict):
        raise ScnLayoutError("profile text_box_overrides is not an object")
    output: dict[int, str] = {}
    for raw_index, text_box in raw.items():
        try:
            index = canonical_profile_index(
                raw_index, field="text_box_overrides", chapter="SCN profile"
            )
        except ValueError as exc:
            raise ScnLayoutError(
                f"profile text_box_overrides has invalid record {raw_index!r}"
            ) from exc
        if index < 0 or text_box not in TEXT_BOX_IDS - {TEXT_BOX_UNCLASSIFIED}:
            raise ScnLayoutError(
                f"profile text_box_overrides has invalid text box for record {raw_index!r}"
            )
        output[index] = text_box
    return output


def _window_subtypes(profile: dict[str, object]) -> set[int]:
    """Return SCN 0x24 subtypes that carry visible text."""
    # 0x28 is overloaded by selector commands in several chapters.  It is
    # visible text only where the source profile explicitly opts it in.
    raw = profile.get("scn_window_text_subtypes", [0x27])
    if not isinstance(raw, list) or not all(isinstance(item, int) for item in raw):
        raise ScnLayoutError("profile scn_window_text_subtypes is invalid")
    return set(raw)


def _window_text_commands(
    scn: bytes,
    record_count: int,
    window_subtypes: set[int],
) -> list[tuple[int, int, int, int, tuple[int, ...]]]:
    """Return structurally valid floating-window commands and text chains.

    ``0x24`` opens the floating renderer and supplies its first MES record.
    Zero or more immediately following ``0x27 <id>`` commands display later
    records through that same renderer.  Treating the chained records as
    independent opcodes loses their width and row contract, which is how
    stale hand-wrapping survived the first adaptive-formatting pass.
    """
    commands: list[tuple[int, int, int, int, tuple[int, ...]]] = []
    for offset in range(len(scn) - 7):
        if scn[offset] != 0x24 or scn[offset + 5] not in window_subtypes:
            continue
        text_id = int.from_bytes(scn[offset + 6 : offset + 8], "big")
        if not 1 <= text_id <= record_count:
            continue
        indexes = [text_id - 1]
        cursor = offset + 8
        while cursor + 3 <= len(scn) and scn[cursor] == 0x27:
            continuation_id = int.from_bytes(scn[cursor + 1 : cursor + 3], "big")
            if not 1 <= continuation_id <= record_count:
                break
            indexes.append(continuation_id - 1)
            cursor += 3
        commands.append(
            (
                offset,
                scn[offset + 5],
                scn[offset + 3],
                scn[offset + 2],
                tuple(indexes),
            )
        )
    return commands


def _selector_window_commands(
    scn: bytes,
    record_count: int,
) -> list[tuple[int, int, int, int, tuple[int, ...]]]:
    """Return 0x24 windows proven reachable by a 0x42/0x43 selector table."""
    commands: dict[int, tuple[int, int, int, int, tuple[int, ...]]] = {}
    offset = 0
    while offset < len(scn):
        if scn[offset] != 0x42:
            offset += 1
            continue
        cursor = offset + 1
        display_targets: list[int] = []
        while cursor + 6 <= len(scn) and scn[cursor] == 0x43:
            display_targets.append(int.from_bytes(scn[cursor + 4 : cursor + 6], "big"))
            cursor += 6
        if not display_targets or cursor >= len(scn) or scn[cursor] != 0x44:
            offset += 1
            continue
        for target in display_targets:
            if (
                target + 9 > len(scn)
                or scn[target] != 0x24
                or scn[target + 5] not in (0x27, 0x28)
                or scn[target + 8] != 0x13
            ):
                continue
            text_id = int.from_bytes(scn[target + 6 : target + 8], "big")
            if not 1 <= text_id <= record_count:
                continue
            commands[target] = (
                target,
                scn[target + 5],
                scn[target + 3],
                scn[target + 2],
                (text_id - 1,),
            )
        offset = cursor + 1
    return [commands[key] for key in sorted(commands)]


def _role_overrides(profile: dict[str, object]) -> dict[int, frozenset[str]]:
    """Read reviewed role replacements for structurally exceptional records."""
    raw = profile.get("role_overrides", {})
    if not isinstance(raw, dict):
        raise ScnLayoutError("profile role_overrides is not an object")
    output: dict[int, frozenset[str]] = {}
    allowed = LABEL_ROLES | PROSE_ROLES | {ROLE_CHOICE}
    for raw_index, raw_roles in raw.items():
        try:
            index = canonical_profile_index(
                raw_index, field="role_overrides", chapter="SCN profile"
            )
        except ValueError as exc:
            raise ScnLayoutError(f"invalid role override record {raw_index!r}") from exc
        values = [raw_roles] if isinstance(raw_roles, str) else raw_roles
        if (
            index < 0
            or not isinstance(values, list)
            or not values
            or not all(isinstance(role, str) and role in allowed for role in values)
        ):
            raise ScnLayoutError(f"invalid role override for record {raw_index!r}")
        output[index] = frozenset(values)
    return output


def infer_layouts(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
    *,
    retail_records: tuple[bytes, ...] | None = None,
) -> dict[int, Layout]:
    """Infer translated-record geometry from structural SCN commands.

    Dialogue, continuation, floating-window, and selector command operands are
    converted from one-based SCN IDs to zero-based canonical indexes. When the
    matching hash-locked MES records are supplied, a retail opening quote at
    the start of a normal dialogue record becomes a one-time blank English
    gutter. Reviewed profile overrides may refine visible/runtime widths but
    cannot make runtime stride smaller than visible capacity or resolve
    conflicting SCN evidence silently.
    """
    settings = profile or {}
    # This is a native lower-dialogue contract, not a generic English width:
    # physical cells repeat 12/11/11, with an optional quote gutter in the
    # first 12-cell row.  Runtime screenshots of PART1A:003 confirm the
    # 11-cell continuation boundary ("more" must not be packed as 12 cells).
    dialogue_visible = _pair(settings, "scn_dialogue_layout", (12, 11))
    continuation_visible = _pair(settings, "scn_continuation_layout", (12, 10))
    dialogue_runtime = _pair(settings, "scn_dialogue_runtime_layout", dialogue_visible)
    continuation_runtime = _pair(
        settings, "scn_continuation_runtime_layout", continuation_visible
    )
    window_subtypes = _window_subtypes(settings)
    visible_overrides = _indexed_pairs(settings, "layout_overrides")
    runtime_overrides = _indexed_pairs(settings, "runtime_layout_overrides")
    text_box_overrides = _indexed_text_boxes(settings)
    layouts: dict[int, Layout] = {}
    if retail_records is not None and len(retail_records) != record_count:
        raise ScnLayoutError("retail MES record count does not match SCN layout input")
    dialogue_anchor_indexes: set[int] = set()

    def add(index: int, layout: Layout, source: str) -> None:
        """Merge one proven layout while rejecting conflicting SCN evidence."""
        if index not in translated_indexes:
            return
        previous = layouts.get(index)
        if previous is not None and previous != layout:
            raise ScnLayoutError(
                f"record {index} receives conflicting layouts at {source}: "
                f"{previous} versus {layout}"
            )
        if (
            layout.runtime_first < layout.visible_first
            or layout.runtime_continuation < layout.visible_continuation
        ):
            raise ScnLayoutError(
                f"record {index}: runtime stride is smaller than visible width"
            )
        layouts[index] = layout

    for offset, opcode in enumerate(scn):
        if opcode == 0x21 and offset + 5 <= len(scn):
            first_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            second_id = int.from_bytes(scn[offset + 3 : offset + 5], "big")
            if 1 <= second_id <= record_count:
                index = second_id - 1
                add(
                    index,
                    Layout(
                        *dialogue_visible,
                        *dialogue_runtime,
                        page_rows=3,
                        repeat_first_row_on_page=False,
                        text_box=TEXT_BOX_LOWER_DIALOGUE,
                    ),
                    f"0x21 dialogue at 0x{offset:X}",
                )
                if retail_records is not None and retail_records[index][:1] == bytes(
                    (DIALOGUE_OPENING_ANCHOR_CODE,)
                ):
                    dialogue_anchor_indexes.add(index)
            elif second_id == 0 and 1 <= first_id <= record_count:
                add(
                    first_id - 1,
                    Layout(
                        *continuation_visible,
                        *continuation_runtime,
                        page_rows=3,
                        repeat_first_row_on_page=False,
                        text_box=TEXT_BOX_LOWER_CONTINUATION,
                    ),
                    f"0x21 continuation at 0x{offset:X}",
                )
    for offset, _subtype, width_byte, _raw_y, indexes in _window_text_commands(
        scn, record_count, window_subtypes
    ):
        eligible = [index for index in indexes if index in translated_indexes]
        if not eligible:
            # Preserved records retain their retail wrapping byte-for-byte.
            continue
        if width_byte not in FLOATING_WIDTHS:
            if all(index in visible_overrides for index in eligible):
                # Exceptional renderers (for example START's full-screen
                # narration) have reviewed explicit contracts below.
                continue
            raise ScnLayoutError(
                f"unsupported floating width 0x{width_byte:02X} at 0x{offset:X}"
            )
        cells = FLOATING_WIDTHS[width_byte]
        for chain_position, index in enumerate(indexes):
            add(
                index,
                Layout(cells, cells, cells, cells, text_box=TEXT_BOX_FLOATING),
                (
                    f"0x24 window at 0x{offset:X}"
                    if chain_position == 0
                    else f"0x27 window continuation at 0x{offset + 8 + 3 * (chain_position - 1):X}"
                ),
            )

    for offset, _subtype, width_byte, _raw_y, indexes in _selector_window_commands(
        scn, record_count
    ):
        if width_byte not in FLOATING_WIDTHS:
            raise ScnLayoutError(
                f"unsupported selector width 0x{width_byte:02X} at 0x{offset:X}"
            )
        cells = FLOATING_WIDTHS[width_byte]
        for index in indexes:
            add(
                index,
                # Selector tables target the same 0x24 window renderer as
                # ordinary floating text.  The record can also retain the
                # menu_choice role, but its cell contract must not conflict
                # with an identical floating-window use elsewhere in SCN.
                Layout(cells, cells, cells, cells, text_box=TEXT_BOX_FLOATING),
                f"0x42/0x43 selector window at 0x{offset:X}",
            )

    for index in sorted(
        set(visible_overrides) | set(runtime_overrides) | set(text_box_overrides)
    ):
        if index not in translated_indexes:
            continue
        previous = layouts.get(index)
        visible = visible_overrides.get(index)
        runtime = runtime_overrides.get(index)
        if visible is None:
            if previous is None:
                raise ScnLayoutError(
                    f"record {index}: runtime override has no inferred/visible layout"
                )
            visible = (previous.visible_first, previous.visible_continuation)
        if runtime is None:
            runtime = (
                visible
                if index in visible_overrides
                else (
                    (previous.runtime_first, previous.runtime_continuation)
                    if previous is not None
                    else visible
                )
            )
        override = Layout(
            *visible,
            *runtime,
            page_rows=previous.page_rows if previous is not None else None,
            repeat_first_row_on_page=(
                previous.repeat_first_row_on_page if previous is not None else False
            ),
            opening_anchor_cells=(
                previous.opening_anchor_cells if previous is not None else 0
            ),
            text_box=text_box_overrides.get(
                index,
                previous.text_box if previous is not None else TEXT_BOX_UNCLASSIFIED,
            ),
        )
        if (
            override.runtime_first < override.visible_first
            or override.runtime_continuation < override.visible_continuation
        ):
            raise ScnLayoutError(
                f"record {index}: runtime override is smaller than visible width"
            )
        layouts[index] = override
    for index in sorted(dialogue_anchor_indexes):
        layout = layouts.get(index)
        if layout is not None:
            layouts[index] = layout.with_opening_anchor()
    return layouts


def infer_roles(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
) -> dict[int, frozenset[str]]:
    """Infer UI roles without consulting the English translation.

    Top labels are accepted only from the exact adjacent ``0x22``/``0x23``
    pair used by the scene UI.  That avoids treating operand bytes elsewhere
    in the script as label commands.
    """
    settings = profile or {}
    window_subtypes = _window_subtypes(settings)
    roles: dict[int, set[str]] = {}

    def add(index: int, role: str) -> None:
        """Attach one structural role only to a translated record."""
        if index in translated_indexes:
            roles.setdefault(index, set()).add(role)

    for offset in range(len(scn)):
        opcode = scn[offset]
        if opcode == 0x21 and offset + 5 <= len(scn):
            first_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            second_id = int.from_bytes(scn[offset + 3 : offset + 5], "big")
            if 1 <= second_id <= record_count:
                if 1 <= first_id <= record_count:
                    add(first_id - 1, ROLE_SPEAKER)
                add(second_id - 1, ROLE_DIALOGUE)
            elif second_id == 0 and 1 <= first_id <= record_count:
                add(first_id - 1, ROLE_CONTINUATION)
        elif opcode == 0x22 and offset + 6 <= len(scn) and scn[offset + 3] == 0x23:
            location_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            perspective_id = int.from_bytes(scn[offset + 4 : offset + 6], "big")
            if 1 <= location_id <= record_count and 1 <= perspective_id <= record_count:
                add(location_id - 1, ROLE_LOCATION)
                add(perspective_id - 1, ROLE_PERSPECTIVE)
        elif opcode == 0x31 and offset + 6 <= len(scn) and scn[offset + 3] == 0xFF:
            text_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            jump = int.from_bytes(scn[offset + 4 : offset + 6], "big")
            if 1 <= text_id <= record_count and 0 < jump < len(scn):
                add(text_id - 1, ROLE_CHOICE)

    for _offset, subtype, _width_byte, _raw_y, indexes in _window_text_commands(
        scn, record_count, window_subtypes
    ):
        role = ROLE_THOUGHT if subtype == 0x27 else ROLE_OVERLAY
        for index in indexes:
            add(index, role)

    for _offset, _subtype, _width_byte, _raw_y, indexes in _selector_window_commands(
        scn, record_count
    ):
        for index in indexes:
            add(index, ROLE_CHOICE)

    for index, replacement in _role_overrides(settings).items():
        if index in translated_indexes:
            roles[index] = set(replacement)
    return {index: frozenset(values) for index, values in sorted(roles.items())}


def infer_row_limits(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
) -> dict[int, int]:
    """Infer visible row limits from floating-window Y coordinates.

    Only structurally valid configured window subtypes participate. Profile
    overrides are explicit record-indexed evidence for exceptional renderers.
    """
    settings = profile or {}
    window_subtypes = _window_subtypes(settings)
    limits: dict[int, int] = {}
    for offset, _subtype, _width_byte, raw_y, indexes in _window_text_commands(
        scn, record_count, window_subtypes
    ):
        max_rows = (28 - raw_y - 2) // 2
        if max_rows <= 0:
            raise ScnLayoutError(f"floating window at 0x{offset:X} has no visible rows")
        for index in indexes:
            if index not in translated_indexes:
                continue
            previous = limits.get(index)
            # A record may be reused by windows at different Y positions.  It
            # must satisfy the tightest of those real renderers.
            limits[index] = (
                min(previous, max_rows) if previous is not None else max_rows
            )
    for offset, _subtype, _width_byte, raw_y, indexes in _selector_window_commands(
        scn, record_count
    ):
        max_rows = (28 - raw_y - 2) // 2
        if max_rows <= 0:
            raise ScnLayoutError(f"selector window at 0x{offset:X} has no visible rows")
        for index in indexes:
            if index not in translated_indexes:
                continue
            previous = limits.get(index)
            limits[index] = (
                min(previous, max_rows) if previous is not None else max_rows
            )
    raw_overrides = settings.get("row_limit_overrides", {})
    if not isinstance(raw_overrides, dict):
        raise ScnLayoutError("profile row_limit_overrides is not an object")
    for raw_index, raw_limit in raw_overrides.items():
        try:
            index = canonical_profile_index(
                raw_index, field="row_limit_overrides", chapter="SCN profile"
            )
        except ValueError as exc:
            raise ScnLayoutError(f"invalid row-limit record {raw_index!r}") from exc
        if not isinstance(raw_limit, int) or raw_limit <= 0:
            raise ScnLayoutError(f"invalid row limit for record {raw_index!r}")
        if index in translated_indexes:
            limits[index] = raw_limit
    return limits


def infer_contracts(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
    *,
    retail_records: tuple[bytes, ...] | None = None,
) -> dict[int, RecordContract]:
    """Return shared role, layout, and row contracts for translated records.

    The result is keyed only by translated canonical indexes that have at least
    one proven role, layout, or vertical limit. English text is never consulted,
    preventing the translation from determining its own renderer rules.
    """
    roles = infer_roles(scn, record_count, translated_indexes, profile)
    layouts = infer_layouts(
        scn,
        record_count,
        translated_indexes,
        profile,
        retail_records=retail_records,
    )
    row_limits = infer_row_limits(scn, record_count, translated_indexes, profile)
    indexes = set(roles) | set(layouts) | set(row_limits)
    return {
        index: RecordContract(
            roles=roles.get(index, frozenset()),
            layout=layouts.get(index),
            max_rows=row_limits.get(index),
        )
        for index in sorted(indexes)
    }

#!/usr/bin/env python3
"""Parse the game's MES pointer/record/glyph container without interpretation.

MES has three contiguous regions: a big-endian pointer table, encoded records,
and an 18-byte-per-glyph dynamic font tail. The first pointer terminates the
pointer table; the header's split offset terminates the record region. Adjacent
pointers therefore define records without scanning for terminators.

This module validates only structural facts: strictly increasing pointer
boundaries, nonempty terminated records, glyph alignment, and dynamic-reference
bounds. It does not decide which records are English, how text wraps, or which
SCN renderer consumes a record. Those belong to ``mes_compiler.py`` and
``scn_layout.py``.

The parser has no dependency on historical translation tools or generated
builds. See ``docs/BINARY_FORMATS.md`` for an offset diagram and the fixed versus
dynamic code convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GLYPH_BYTES = 18
DYNAMIC_PREFIX_START = 0xF0
DYNAMIC_GLYPHS_PER_PREFIX = 0xFF


class MesFormatError(ValueError):
    """Raised when a MES file violates its structural invariants."""


@dataclass(frozen=True)
class MesFile:
    """A validated MES split point, pointer table, records, and glyph bank.

    ``records[index]`` is the exact encoded byte range selected by pointer
    ``index``. ``glyphs[index]`` is one stored 12x12 bitmap. The object is
    immutable so callers cannot accidentally mutate retail evidence.
    """

    split_offset: int
    pointers: tuple[int, ...]
    records: tuple[bytes, ...]
    glyphs: tuple[bytes, ...]

    @property
    def first_pointer(self) -> int:
        """Return the first record offset and pointer-table boundary."""
        return self.pointers[0]

    @property
    def record_count(self) -> int:
        """Return the number of script records."""
        return len(self.records)

    def referenced_dynamic_indexes(self) -> frozenset[int]:
        """Return every dynamic-glyph index referenced by the record stream."""
        indexes: set[int] = set()
        for record_index, record in enumerate(self.records):
            offset = 0
            while offset < len(record):
                value = record[offset]
                if value < DYNAMIC_PREFIX_START:
                    offset += 1
                    continue
                if offset + 1 >= len(record):
                    raise MesFormatError(
                        f"record {record_index} has a truncated dynamic reference"
                    )
                low = record[offset + 1]
                if low == 0:
                    raise MesFormatError(
                        f"record {record_index} uses forbidden dynamic value 00"
                    )
                indexes.add(
                    (value - DYNAMIC_PREFIX_START) * DYNAMIC_GLYPHS_PER_PREFIX
                    + low
                    - 1
                )
                offset += 2
        return frozenset(indexes)


def _u16be(data: bytes, offset: int) -> int:
    """Read one big-endian unsigned 16-bit integer."""
    return int.from_bytes(data[offset : offset + 2], "big")


def parse_mes(data: bytes, *, source: str = "<bytes>") -> MesFile:
    """Parse a MES file and reject ambiguous or unsafe layouts.

    The first pointer defines both pointer-table length and record count.
    Pointers must be ordered, records must remain before the glyph split, every
    record must terminate, and dynamic references must fit the complete
    18-byte glyph bank.

    Args:
        data: Complete MES member bytes.
        source: Human-readable label used in validation errors.

    Returns:
        An immutable ``MesFile`` retaining exact record and glyph bytes.

    Raises:
        MesFormatError: If any boundary, pointer, terminator, or glyph-reference
            invariant fails.
    """
    if len(data) < 5:
        raise MesFormatError(
            f"{source}: file is too small ({len(data)} bytes)"
        )

    split_offset = _u16be(data, 0)
    first_pointer = _u16be(data, 2)
    if first_pointer < 4 or first_pointer % 2:
        raise MesFormatError(
            f"{source}: invalid first pointer 0x{first_pointer:04X}"
        )
    pointer_count = (first_pointer - 2) // 2
    if pointer_count <= 0 or 2 + pointer_count * 2 != first_pointer:
        raise MesFormatError(f"{source}: inconsistent pointer-table length")
    if not first_pointer <= split_offset <= len(data):
        raise MesFormatError(
            f"{source}: split 0x{split_offset:04X} is outside the data region"
        )

    pointers = tuple(
        _u16be(data, 2 + index * 2) for index in range(pointer_count)
    )
    if pointers[0] != first_pointer:
        raise MesFormatError(f"{source}: first pointer does not end the table")
    if any(
        pointer < first_pointer or pointer >= split_offset
        for pointer in pointers
    ):
        raise MesFormatError(
            f"{source}: record pointer outside the script region"
        )
    if any(left >= right for left, right in zip(pointers, pointers[1:])):
        raise MesFormatError(
            f"{source}: record pointers are not strictly increasing"
        )

    boundaries = (*pointers, split_offset)
    records = tuple(
        data[start:end] for start, end in zip(boundaries, boundaries[1:])
    )
    for record_index, record in enumerate(records):
        if not record:
            raise MesFormatError(f"{source}: record {record_index} is empty")
        if record[-1] != 0:
            raise MesFormatError(
                f"{source}: record {record_index} lacks its 00 terminator"
            )
    glyph_tail = data[split_offset:]
    if len(glyph_tail) % GLYPH_BYTES:
        raise MesFormatError(
            f"{source}: dynamic tail has {len(glyph_tail) % GLYPH_BYTES} extra bytes"
        )
    glyphs = tuple(
        glyph_tail[offset : offset + GLYPH_BYTES]
        for offset in range(0, len(glyph_tail), GLYPH_BYTES)
    )

    parsed = MesFile(
        split_offset=split_offset,
        pointers=pointers,
        records=records,
        glyphs=glyphs,
    )
    references = parsed.referenced_dynamic_indexes()
    if references and max(references) >= len(glyphs):
        raise MesFormatError(
            f"{source}: dynamic reference {max(references)} exceeds "
            f"the {len(glyphs)}-glyph bank"
        )
    return parsed


def read_mes(path: Path) -> MesFile:
    """Read and parse one MES file from disk."""
    return parse_mes(path.read_bytes(), source=str(path))


def record_render_tokens(
    mes: MesFile, record_index: int
) -> tuple[tuple[str, int | bytes], ...]:
    """Return a remap-stable token stream for one encoded MES record.

    Fixed/control bytes are retained verbatim. Dynamic references are resolved
    to their 18-byte glyph bitmap so a legal glyph-bank compaction does not
    create a false difference. Comparing these tokens therefore proves that a
    preserved record has the same fixed/control bytes and the same rendered
    dynamic cells in the same order even when dynamic indexes are renumbered.
    """
    if not 0 <= record_index < mes.record_count:
        raise MesFormatError(f"record index {record_index} is out of range")
    record = mes.records[record_index]
    tokens: list[tuple[str, int | bytes]] = []
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value < DYNAMIC_PREFIX_START:
            tokens.append(("fixed", value))
            offset += 1
            continue
        if offset + 1 >= len(record) or record[offset + 1] == 0:
            raise MesFormatError(
                f"record {record_index} has an invalid dynamic reference"
            )
        dynamic_index = (
            (value - DYNAMIC_PREFIX_START) * DYNAMIC_GLYPHS_PER_PREFIX
            + record[offset + 1]
            - 1
        )
        if dynamic_index >= len(mes.glyphs):
            raise MesFormatError(
                f"record {record_index} dynamic reference {dynamic_index} exceeds "
                f"the {len(mes.glyphs)}-glyph bank"
            )
        tokens.append(("dynamic", mes.glyphs[dynamic_index]))
        offset += 2
    return tuple(tokens)


def changed_record_indexes(
    original: MesFile, rebuilt: MesFile
) -> tuple[int, ...]:
    """Return indexes whose encoded record bytes differ between two MES files."""
    if original.record_count != rebuilt.record_count:
        raise MesFormatError(
            "cannot compare MES files with different record counts: "
            f"{original.record_count} != {rebuilt.record_count}"
        )
    return tuple(
        index
        for index, (before, after) in enumerate(
            zip(original.records, rebuilt.records)
        )
        if before != after
    )

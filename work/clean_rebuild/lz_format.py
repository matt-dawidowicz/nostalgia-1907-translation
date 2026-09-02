#!/usr/bin/env python3
"""Read, encode, and safely rewrite the game's chapter LZ archives.

An archive starts with a member count and fixed-size table. Each table entry
contains a name, payload offset, stored size, unpacked size, and preserved
marker. Member payloads occupy ordered slots after the table. Compressed payload
bits and output bytes are both consumed backward; the footer carries the
unpacked size, XOR checksum, and initial bit buffer.

``replace_members_fixed`` is the preferred writer because it preserves every
member offset and the complete archive size. ``replace_members_reflow`` is a
guarded fallback that preserves member names, order, and untouched payloads
while repacking only inside a caller-supplied outer allocation.

Compression is deterministic: dynamic programming minimizes bit cost, tie
breaking follows stable iteration order, and every result is decompressed as an
immediate self-check. See ``docs/BINARY_FORMATS.md`` for table offsets and
writer invariants.
"""

from __future__ import annotations

import bisect
from collections import deque
from dataclasses import dataclass
from pathlib import Path


ENTRY_SIZE = 0x1E
Op = tuple[str, int, int]


class LzError(ValueError):
    """Raised when an archive or compressed member violates the game format."""


@dataclass(frozen=True)
class Entry:
    """One validated member-table row.

    ``offset`` and ``compressed_size`` locate the stored payload.
    ``unpacked_size`` selects stored versus compressed decoding. ``marker`` is
    retained as opaque retail metadata because its semantics are not needed to
    replace a member safely.
    """

    index: int
    name: str
    offset: int
    compressed_size: int
    unpacked_size: int
    marker: bytes


class BackwardBits:
    """Read the game's compressed footer bitstream from end to start."""

    def __init__(self, data: bytes, position: int, buffer: int, checksum: int):
        """Initialize a backward reader at the first footer-owned bit word.

        Args:
            data: Complete aligned compressed payload.
            position: Exclusive byte offset of the next backing word.
            buffer: Initial 32-bit shift register stored in the footer.
            checksum: XOR accumulator after consuming the initial word.
        """
        self.data = data
        self.position = position
        self.buffer = buffer
        self.checksum = checksum

    def _word(self) -> int:
        """Consume one preceding big-endian word or reject stream underflow."""
        self.position -= 4
        if self.position < 0:
            raise LzError("compressed bitstream underflow")
        return int.from_bytes(self.data[self.position : self.position + 4], "big")

    def bit(self) -> int:
        """Consume one least-significant-first stream bit."""
        value = self.buffer & 1
        self.buffer = (self.buffer >> 1) & 0xFFFFFFFF
        if self.buffer:
            return value
        word = self._word()
        self.checksum ^= word
        self.buffer = (0x80000000 | word >> 1) & 0xFFFFFFFF
        return word & 1

    def bits(self, count: int) -> int:
        """Consume a big-endian numeric field from stream-order bits."""
        value = 0
        for _ in range(count):
            value = (value << 1) | self.bit()
        return value


def decompress(payload: bytes, expected_size: int | None = None) -> bytes:
    """Decompress one backward LZ payload and verify its footer checksum.

    Args:
        payload: Complete 32-bit-aligned stored payload, including footer.
        expected_size: Optional archive-table unpacked size to cross-check.

    Returns:
        Exact unpacked bytes.

    Raises:
        LzError: If alignment, footer size, command bounds, copy distance, or
            XOR checksum is invalid.
    """
    if len(payload) < 12 or len(payload) % 4:
        raise LzError("compressed payload must contain at least three aligned words")
    position = len(payload)

    def previous_word() -> int:
        """Consume one big-endian footer word while moving backward."""
        nonlocal position
        position -= 4
        if position < 0:
            raise LzError("compressed footer underflow")
        return int.from_bytes(payload[position : position + 4], "big")

    unpacked_size = previous_word()
    if expected_size is not None and unpacked_size != expected_size:
        raise LzError(
            f"footer size {unpacked_size} does not match table size {expected_size}"
        )
    output = bytearray(unpacked_size)
    output_position = unpacked_size
    checksum = previous_word()
    initial = previous_word()
    reader = BackwardBits(payload, position, initial, checksum ^ initial)

    def literal(count_minus_one: int) -> None:
        """Decode a literal run into the preceding output positions."""
        nonlocal output_position
        for _ in range(count_minus_one + 1):
            output_position -= 1
            if output_position < 0:
                raise LzError("literal command overran the output")
            output[output_position] = reader.bits(8)

    def copy(distance: int, count_minus_one: int) -> None:
        """Decode a backward overlap-safe copy command."""
        nonlocal output_position
        if distance <= 0:
            raise LzError("copy distance must be positive")
        for _ in range(count_minus_one + 1):
            output_position -= 1
            source = output_position + distance
            if output_position < 0 or source >= len(output):
                raise LzError("copy command overran the output")
            output[output_position] = output[source]

    while output_position:
        if reader.bit() == 0:
            if reader.bit() == 0:
                literal(reader.bits(3))
            else:
                copy(reader.bits(8), 1)
            continue
        mode = reader.bits(2)
        if mode == 3:
            literal(reader.bits(8) + 8)
        elif mode < 2:
            copy(reader.bits(9 + mode), mode + 2)
        else:
            count = reader.bits(8)
            copy(reader.bits(12), count)
    if reader.checksum:
        raise LzError(f"compressed payload checksum is 0x{reader.checksum:08X}")
    return bytes(output)


def _field_bits(value: int, width: int) -> list[int]:
    """Return a numeric field in the order the decoder consumes it."""
    return [(value >> shift) & 1 for shift in range(width - 1, -1, -1)]


def _op_cost(op: Op) -> int:
    """Return the exact encoded bit count for one compressor operation."""
    kind, length, _distance = op
    if kind == "literal":
        return (5 if length <= 8 else 11) + length * 8
    return {"copy2": 10, "copy3": 12, "copy4": 13, "copylong": 23}[kind]


def _match_length(data: bytes, position: int, distance: int, limit: int) -> int:
    """Measure a legal backward match without crossing input boundaries."""
    length = 0
    while length < limit:
        destination = position - length - 1
        if destination < 0:
            break
        source = destination + distance
        if source >= len(data) or data[destination] != data[source]:
            break
        length += 1
    return length


def _copy_candidates(
    data: bytes, positions: dict[int, list[int]], position: int
) -> list[Op]:
    """Enumerate encodable copies ending at ``position``.

    Copy commands require at least two bytes, so candidates are indexed by the
    two-byte sequence ending at each possible source position.  This preserves
    the original ascending source order and therefore deterministic tie
    breaking, while avoiding the much larger set of one-byte false matches.
    """
    max_distance = min(0xFFF, len(data) - position)
    if position < 2 or max_distance <= 0:
        return []
    key = (data[position - 2] << 8) | data[position - 1]
    matching = positions.get(key, [])
    first = bisect.bisect_left(matching, position)
    last = bisect.bisect_right(matching, position - 1 + max_distance)
    operations: list[Op] = []
    for source in matching[first:last]:
        distance = source - (position - 1)
        length = _match_length(data, position, distance, min(256, position))
        if length >= 2 and distance <= 0xFF:
            operations.append(("copy2", 2, distance))
        if length >= 3 and distance <= 0x1FF:
            operations.append(("copy3", 3, distance))
        if length >= 4 and distance <= 0x3FF:
            operations.append(("copy4", 4, distance))
        operations.extend(
            ("copylong", candidate_length, distance)
            for candidate_length in range(5, length + 1)
        )
    return operations


def _choose_operations(data: bytes) -> list[tuple[int, Op]]:
    """Find the minimum-bit backward parse with deterministic tie breaking.

    Literal costs are affine in run length, so the long-literal range can use
    a monotonic sliding minimum instead of rescanning up to 256 predecessors at
    every byte.  Equal-cost minima retain the shortest literal, exactly matching
    the previous ascending-length loop.
    """
    positions: dict[int, list[int]] = {}
    for endpoint in range(1, len(data)):
        key = (data[endpoint - 1] << 8) | data[endpoint]
        positions.setdefault(key, []).append(endpoint)
    infinity = 10**18
    costs = [infinity] * (len(data) + 1)
    choices: list[Op | None] = [None] * (len(data) + 1)
    costs[0] = 0
    long_literals: deque[tuple[int, int]] = deque()
    for position in range(1, len(data) + 1):
        # Lengths 1..8 have a five-bit command overhead.  There are only eight
        # candidates, so evaluating them directly is cheaper and preserves the
        # original shortest-length tie preference.
        for length in range(1, min(8, position) + 1):
            cost = costs[position - length] + 5 + length * 8
            if cost < costs[position]:
                costs[position] = cost
                choices[position] = ("literal", length, 0)

        # Lengths 9..264 cost costs[j] + 11 + 8*(position-j).
        # Maintain the minimum of costs[j] - 8*j over the legal predecessor
        # window.  Newer equal minima replace older ones so ties choose the
        # larger j, i.e. the shorter literal, matching the legacy loop.
        eligible = position - 9
        if eligible >= 0:
            value = costs[eligible] - 8 * eligible
            while long_literals and value <= long_literals[-1][1]:
                long_literals.pop()
            long_literals.append((eligible, value))
        minimum_index = position - 264
        while long_literals and long_literals[0][0] < minimum_index:
            long_literals.popleft()
        if long_literals:
            predecessor = long_literals[0][0]
            length = position - predecessor
            cost = costs[predecessor] + 11 + length * 8
            if cost < costs[position]:
                costs[position] = cost
                choices[position] = ("literal", length, 0)

        for operation in _copy_candidates(data, positions, position):
            cost = costs[position - operation[1]] + _op_cost(operation)
            if cost < costs[position]:
                costs[position] = cost
                choices[position] = operation

    selected: list[tuple[int, Op]] = []
    position = len(data)
    while position:
        operation = choices[position]
        if operation is None:
            raise LzError(f"compressor could not cover byte {position}")
        selected.append((position, operation))
        position -= operation[1]
    return selected


def _pack_stream(bits: list[int], unpacked_size: int) -> bytes:
    """Pack stream-order bits, XOR checksum, and size into the game footer."""
    initial = 0x80000000
    for index, bit in enumerate(bits[:31]):
        initial |= bit << index
    words = [initial]
    for start in range(31, len(bits), 32):
        word = 0
        for index, bit in enumerate(bits[start : start + 32]):
            word |= bit << index
        words.append(word)
    checksum = 0
    for word in words:
        checksum ^= word
    return (
        b"".join(word.to_bytes(4, "big") for word in reversed(words))
        + checksum.to_bytes(4, "big")
        + unpacked_size.to_bytes(4, "big")
    )


def compress(data: bytes) -> bytes:
    """Compress bytes with the game's exact backward command set.

    Dynamic programming selects the minimum encoded bit cost. Stable candidate
    ordering supplies deterministic tie breaking, and the result is immediately
    decompressed to prove a byte-exact round trip.

    Raises:
        LzError: If no command sequence covers the input or the internal
            round-trip check fails.
    """
    bits: list[int] = []
    for position, (kind, length, distance) in _choose_operations(data):
        if kind == "literal":
            if length <= 8:
                bits.extend((0, 0))
                bits.extend(_field_bits(length - 1, 3))
            else:
                bits.extend((1, 1, 1))
                bits.extend(_field_bits(length - 9, 8))
            for offset in range(1, length + 1):
                bits.extend(_field_bits(data[position - offset], 8))
        elif kind == "copy2":
            bits.extend((0, 1))
            bits.extend(_field_bits(distance, 8))
        elif kind == "copy3":
            bits.extend((1, 0, 0))
            bits.extend(_field_bits(distance, 9))
        elif kind == "copy4":
            bits.extend((1, 0, 1))
            bits.extend(_field_bits(distance, 10))
        elif kind == "copylong":
            bits.extend((1, 1, 0))
            bits.extend(_field_bits(length - 1, 8))
            bits.extend(_field_bits(distance, 12))
        else:
            raise LzError(f"unknown compression operation {kind!r}")
    payload = _pack_stream(bits, len(data))
    if decompress(payload, len(data)) != data:
        raise LzError("compressor self-check failed")
    return payload


def parse_archive(data: bytes, *, source: str = "<bytes>") -> tuple[Entry, ...]:
    """Parse and fully bound-check an archive member table.

    Entry order and duplicate names are preserved. Payload offsets must begin
    after the complete table, remain ordered, and fit the archive; stored and
    compressed sizes must form a decodable representation.
    """
    if len(data) < 4:
        raise LzError(f"{source}: archive is too small")
    count = int.from_bytes(data[:2], "big")
    entry_size = int.from_bytes(data[2:4], "big")
    if entry_size != ENTRY_SIZE:
        raise LzError(f"{source}: unexpected table entry size 0x{entry_size:04X}")
    table_end = 4 + count * ENTRY_SIZE
    if table_end > len(data):
        raise LzError(f"{source}: truncated member table")
    entries: list[Entry] = []
    for index in range(count):
        offset = 4 + index * ENTRY_SIZE
        raw = data[offset : offset + ENTRY_SIZE]
        try:
            name = raw[:14].split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError as error:
            raise LzError(f"{source}: member {index} has a non-ASCII name") from error
        entry = Entry(
            index=index,
            name=name,
            offset=int.from_bytes(raw[14:18], "big"),
            compressed_size=int.from_bytes(raw[18:22], "big"),
            unpacked_size=int.from_bytes(raw[22:26], "big"),
            marker=raw[26:30],
        )
        if not name:
            raise LzError(f"{source}: empty member name at index {index}")
        if entry.offset < table_end or entry.offset + entry.compressed_size > len(data):
            raise LzError(f"{source}:{name}: payload lies outside the archive")
        entries.append(entry)
    if any(left.offset >= right.offset for left, right in zip(entries, entries[1:])):
        raise LzError(f"{source}: member slots are not strictly ordered")
    for index, entry in enumerate(entries):
        slot_end = entries[index + 1].offset if index + 1 < len(entries) else len(data)
        if entry.offset + entry.compressed_size > slot_end:
            raise LzError(f"{source}:{entry.name}: payload overlaps the next slot")
    return tuple(entries)


def member_bytes(data: bytes, entry: Entry) -> bytes:
    """Return one member's unpacked bytes with full format validation."""
    payload = data[entry.offset : entry.offset + entry.compressed_size]
    if entry.compressed_size == entry.unpacked_size:
        return payload
    return decompress(payload, entry.unpacked_size)


def read_member(archive_path: Path, member_name: str) -> bytes:
    """Read an archive member by its exact table name."""
    data = archive_path.read_bytes()
    matches = [
        entry
        for entry in parse_archive(data, source=str(archive_path))
        if entry.name == member_name
    ]
    if len(matches) != 1:
        raise LzError(f"{archive_path}: expected one member named {member_name!r}")
    return member_bytes(data, matches[0])


def _replacement_entries(
    entries: tuple[Entry, ...], replacements: dict[str, Path]
) -> dict[str, Entry]:
    """Resolve replacement names while permitting unrelated duplicate names."""
    resolved: dict[str, Entry] = {}
    for name in replacements:
        matches = [entry for entry in entries if entry.name == name]
        if not matches:
            raise LzError(f"archive lacks replacement member {name!r}")
        if len(matches) != 1:
            raise LzError(
                f"replacement member {name!r} is ambiguous ({len(matches)} entries)"
            )
        resolved[name] = matches[0]
    return resolved


def replace_members_fixed(
    source_archive: Path,
    output_archive: Path,
    replacements: dict[str, Path],
) -> list[dict[str, object]]:
    """Compress replacement members inside their retail slots without reflow.

    Member offsets, table rows, untouched stored payloads, and total archive
    size remain byte-identical. Each replacement is re-read through the parser
    and decoder before the output is accepted.

    Raises:
        LzError: If a name is ambiguous, compressed data exceeds its retail
            slot, or any output invariant fails.

    Side Effects:
        Writes ``output_archive`` only; ``source_archive`` and replacement
        source files are read-only.
    """
    if not replacements:
        raise LzError("at least one archive replacement is required")
    data = bytearray(source_archive.read_bytes())
    entries = parse_archive(data, source=str(source_archive))
    by_name = _replacement_entries(entries, replacements)
    report: list[dict[str, object]] = []
    expected: dict[str, bytes] = {}
    for name, replacement_path in sorted(replacements.items()):
        entry = by_name[name]
        unpacked = replacement_path.read_bytes()
        encoded = compress(unpacked)
        payload = encoded if len(encoded) < len(unpacked) else unpacked
        compressed_size = len(payload)
        unpacked_size = len(unpacked) if payload is encoded else len(payload)
        slot_end = (
            entries[entry.index + 1].offset
            if entry.index + 1 < len(entries)
            else len(data)
        )
        slot_size = slot_end - entry.offset
        if len(payload) > slot_size:
            raise LzError(
                f"{name}: encoded payload is {len(payload)} bytes but retail slot is {slot_size}"
            )
        data[entry.offset : slot_end] = payload + b"\0" * (slot_size - len(payload))
        table_offset = 4 + entry.index * ENTRY_SIZE
        data[table_offset + 18 : table_offset + 22] = compressed_size.to_bytes(4, "big")
        data[table_offset + 22 : table_offset + 26] = unpacked_size.to_bytes(4, "big")
        expected[name] = unpacked
        report.append(
            {
                "member": name,
                "unpacked_size": len(unpacked),
                "stored_size": len(payload),
                "slot_size": slot_size,
                "headroom": slot_size - len(payload),
                "mode": "compressed" if payload is encoded else "stored",
            }
        )
    output_archive.parent.mkdir(parents=True, exist_ok=True)
    output_archive.write_bytes(data)
    if output_archive.stat().st_size != source_archive.stat().st_size:
        raise LzError("fixed-slot write changed archive size")
    rebuilt = output_archive.read_bytes()
    rebuilt_entries = parse_archive(rebuilt, source=str(output_archive))
    for name, unpacked in expected.items():
        entry = next(item for item in rebuilt_entries if item.name == name)
        if member_bytes(rebuilt, entry) != unpacked:
            raise LzError(f"{name}: rebuilt member failed round-trip verification")
    return report


def replace_members_reflow(
    source_archive: Path,
    output_archive: Path,
    replacements: dict[str, Path],
    *,
    maximum_archive_size: int | None = None,
) -> dict[str, object]:
    """Reflow members within a guarded outer-file allocation.

    Reflow is the capacity fallback for a replacement that cannot fit its
    original member slot. Names and order remain fixed, untouched stored
    payloads remain exact, and the complete archive cannot exceed
    ``maximum_archive_size``.

    Returns:
        Replacement details and remaining outer-allocation headroom.

    Side Effects:
        Writes and reparses ``output_archive``; no input is modified.
    """
    if not replacements:
        raise LzError("at least one archive replacement is required")
    source = source_archive.read_bytes()
    entries = parse_archive(source, source=str(source_archive))
    by_name = _replacement_entries(entries, replacements)
    replacement_indexes = {entry.index for entry in by_name.values()}

    payloads: list[tuple[bytes, int, int]] = []
    expected: dict[str, bytes] = {}
    replacements_report: list[dict[str, object]] = []
    for entry in entries:
        if entry.index in replacement_indexes:
            unpacked = replacements[entry.name].read_bytes()
            encoded = compress(unpacked)
            payload = encoded if len(encoded) < len(unpacked) else unpacked
            compressed_size = len(payload)
            unpacked_size = len(unpacked) if payload is encoded else len(payload)
            expected[entry.name] = unpacked
            replacements_report.append(
                {
                    "member": entry.name,
                    "unpacked_size": len(unpacked),
                    "stored_size": len(payload),
                    "mode": "compressed" if payload is encoded else "stored",
                }
            )
        else:
            payload = source[entry.offset : entry.offset + entry.compressed_size]
            compressed_size = entry.compressed_size
            unpacked_size = entry.unpacked_size
        payloads.append((payload, compressed_size, unpacked_size))

    first_payload = entries[0].offset
    required_end = first_payload + sum(len(payload) for payload, _, _ in payloads)
    limit = len(source) if maximum_archive_size is None else maximum_archive_size
    if limit < len(source):
        raise LzError("maximum archive size is smaller than the retail archive")
    if required_end > limit:
        raise LzError(
            f"reflow needs {required_end - limit} bytes beyond the guarded allocation"
        )
    output_size = max(len(source), required_end)
    output = bytearray(source + b"\0" * (output_size - len(source)))
    output[first_payload:] = b"\0" * (output_size - first_payload)
    cursor = first_payload
    for entry, (payload, compressed_size, unpacked_size) in zip(entries, payloads):
        table_offset = 4 + entry.index * ENTRY_SIZE
        output[table_offset + 14 : table_offset + 18] = cursor.to_bytes(4, "big")
        output[table_offset + 18 : table_offset + 22] = compressed_size.to_bytes(
            4, "big"
        )
        output[table_offset + 22 : table_offset + 26] = unpacked_size.to_bytes(4, "big")
        output[cursor : cursor + len(payload)] = payload
        cursor += len(payload)

    output_archive.parent.mkdir(parents=True, exist_ok=True)
    output_archive.write_bytes(output)
    if not source_archive.stat().st_size <= output_archive.stat().st_size <= limit:
        raise LzError("reflow output escaped the guarded archive-size range")
    rebuilt = output_archive.read_bytes()
    rebuilt_entries = parse_archive(rebuilt, source=str(output_archive))
    if [entry.name for entry in rebuilt_entries] != [entry.name for entry in entries]:
        raise LzError("reflow changed member order or names")
    for name, unpacked in expected.items():
        matches = [item for item in rebuilt_entries if item.name == name]
        if len(matches) != 1:
            raise LzError(f"{name}: rebuilt replacement member became ambiguous")
        entry = matches[0]
        if member_bytes(rebuilt, entry) != unpacked:
            raise LzError(f"{name}: reflowed member failed round-trip verification")
    return {
        "replacements": replacements_report,
        "payload_start": first_payload,
        "payload_end": cursor,
        "archive_size": len(output),
        "allocation_size": limit,
        "headroom": limit - cursor,
    }

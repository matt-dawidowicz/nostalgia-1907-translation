#!/usr/bin/env python3
"""Read ISO 9660 directory records and patch files inside retail allocations.

The clean rebuild does not master a new filesystem. It walks the retail primary
volume descriptor, records each file's extent and directory-record location,
and installs replacements at those same extents. A replacement may change its
logical size only when it fits the sectors already allocated to that file.

ISO 9660 stores extent and size twice, once in each byte order. The reader
requires both copies to agree; the writer updates both size copies in every
matching directory record, clears the complete old allocation, writes the new
payload, and reparses the result.

This fixed-extent policy is what preserves file placement and total ISO length.
Archive/member concerns remain in ``lz_format.py``. See
``docs/BINARY_FORMATS.md`` for the allocation and mutation model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SECTOR_SIZE = 2048


class IsoError(ValueError):
    """Raised when the retail ISO or a fixed-extent patch is unsafe."""


@dataclass(frozen=True)
class IsoEntry:
    """One ISO 9660 directory entry and its owning record location."""

    path: str
    extent: int
    size: int
    flags: int
    record_offset: int

    @property
    def is_directory(self) -> bool:
        """Return whether this entry is a directory."""
        return bool(self.flags & 0x02)

    @property
    def allocated_size(self) -> int:
        """Return the complete sector allocation occupied by the file."""
        return (self.size + SECTOR_SIZE - 1) // SECTOR_SIZE * SECTOR_SIZE


def normalize_path(path: str) -> str:
    """Normalize a user or directory-record path for exact matching."""
    return "/".join(
        part.split(";", 1)[0].upper()
        for part in path.replace("\\", "/").strip("/").split("/")
        if part
    )


def _parse_record(data: bytes, offset: int) -> tuple[str, int, int, int, int] | None:
    """Parse one ISO directory record from a directory extent."""
    if offset >= len(data) or data[offset] == 0:
        return None
    length = data[offset]
    record = data[offset : offset + length]
    if len(record) != length or length < 34:
        raise IsoError(f"truncated directory record at relative offset {offset}")
    extent_le = int.from_bytes(record[2:6], "little")
    extent_be = int.from_bytes(record[6:10], "big")
    size_le = int.from_bytes(record[10:14], "little")
    size_be = int.from_bytes(record[14:18], "big")
    if extent_le != extent_be or size_le != size_be:
        raise IsoError("ISO directory record endian copies disagree")
    name_size = record[32]
    if name_size == 0:
        raise IsoError("ISO directory record has an empty file identifier")
    identifier_end = 33 + name_size
    padding_size = 1 if name_size % 2 == 0 else 0
    if identifier_end + padding_size > length:
        raise IsoError("ISO directory record truncates its file identifier or padding")
    if padding_size and record[identifier_end] != 0:
        raise IsoError("ISO directory record has nonzero file-identifier padding")
    raw_name = record[33:identifier_end]
    if raw_name == b"\0":
        name = "."
    elif raw_name == b"\1":
        name = ".."
    else:
        name = raw_name.decode("latin1").split(";", 1)[0]
    return name, extent_le, size_le, record[25], length


def _validate_extent(
    extent: int,
    size: int,
    iso_size: int,
    label: str,
) -> None:
    """Require one logical extent and its sector allocation to fit the ISO."""
    start = extent * SECTOR_SIZE
    logical_end = start + size
    allocated_size = (size + SECTOR_SIZE - 1) // SECTOR_SIZE * SECTOR_SIZE
    allocated_end = start + allocated_size
    if start > iso_size or logical_end > iso_size:
        raise IsoError(f"{label} logical extent is outside the ISO")
    if allocated_end > iso_size:
        raise IsoError(f"{label} sector allocation is outside the ISO")


def read_entries(iso_path: Path) -> tuple[IsoEntry, ...]:
    """Walk every ISO directory and return strict record references.

    The parser starts at the primary volume descriptor, requires little- and
    big-endian extent/size copies to agree, bounds every directory and ordinary
    file allocation, and retains each directory-record byte offset for
    fixed-extent patching.
    """
    iso_size = iso_path.stat().st_size
    if iso_size % SECTOR_SIZE:
        raise IsoError("ISO size is not sector aligned")
    with iso_path.open("rb") as iso:
        iso.seek(16 * SECTOR_SIZE)
        pvd = iso.read(SECTOR_SIZE)
        if len(pvd) != SECTOR_SIZE or pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise IsoError("primary volume descriptor is missing")
        root = _parse_record(pvd, 156)
        if root is None:
            raise IsoError("primary volume descriptor has no root record")
        _validate_extent(root[1], root[2], iso_size, "root directory")

        entries: list[IsoEntry] = []
        visited: set[tuple[int, int]] = set()

        def walk(prefix: str, extent: int, size: int) -> None:
            """Append one bounded directory tree to ``entries``.

            ``visited`` prevents recursion through repeated directory records.
            The helper mutates the enclosing result and file position, and
            raises ``IsoError`` when a declared extent leaves the ISO.
            """
            key = (extent, size)
            if key in visited:
                return
            visited.add(key)
            _validate_extent(extent, size, iso_size, f"directory {prefix or '/'}")
            iso.seek(extent * SECTOR_SIZE)
            directory = iso.read(size)
            offset = 0
            while offset < len(directory):
                if directory[offset] == 0:
                    offset = (offset // SECTOR_SIZE + 1) * SECTOR_SIZE
                    continue
                parsed = _parse_record(directory, offset)
                if parsed is None:
                    raise IsoError("unexpected empty directory record")
                name, child_extent, child_size, flags, record_length = parsed
                record_offset = extent * SECTOR_SIZE + offset
                offset += record_length
                if name in {".", ".."}:
                    continue
                path = f"{prefix}/{name}" if prefix else name
                kind = "directory" if flags & 0x02 else "file"
                _validate_extent(
                    child_extent,
                    child_size,
                    iso_size,
                    f"{kind} {path}",
                )
                entry = IsoEntry(path, child_extent, child_size, flags, record_offset)
                entries.append(entry)
                if entry.is_directory:
                    walk(path, child_extent, child_size)

        walk("", root[1], root[2])
    return tuple(entries)


def unique_file(entries: tuple[IsoEntry, ...], target: str) -> IsoEntry:
    """Resolve one unambiguous non-directory path."""
    normalized = normalize_path(target)
    matches = [entry for entry in entries if normalize_path(entry.path) == normalized]
    if not matches:
        raise IsoError(f"ISO does not contain {target!r}")
    layouts = {(entry.extent, entry.size, entry.flags) for entry in matches}
    if len(layouts) != 1:
        raise IsoError(f"conflicting duplicate records for {target!r}")
    entry = matches[0]
    if entry.is_directory:
        raise IsoError(f"{target!r} names a directory")
    return entry


def extract_file(iso_path: Path, target: str) -> bytes:
    """Read one complete file from its declared extent."""
    entry = unique_file(read_entries(iso_path), target)
    with iso_path.open("rb") as iso:
        iso.seek(entry.extent * SECTOR_SIZE)
        data = iso.read(entry.size)
    if len(data) != entry.size:
        raise IsoError(f"short read for {target!r}")
    return data


def _matching_file_records(
    entries: tuple[IsoEntry, ...], target: str
) -> tuple[IsoEntry, ...]:
    """Return every directory record for one unambiguous file layout."""
    normalized = normalize_path(target)
    matches = tuple(
        entry
        for entry in entries
        if normalize_path(entry.path) == normalized and not entry.is_directory
    )
    if not matches:
        raise IsoError(f"ISO does not contain {target!r}")
    layouts = {(entry.extent, entry.size, entry.flags) for entry in matches}
    if len(layouts) != 1:
        raise IsoError(f"conflicting duplicate records for {target!r}")
    return matches


def patch_fixed_extent_files(
    source_iso: Path,
    output_iso: Path,
    replacements: dict[str, Path],
) -> list[dict[str, object]]:
    """Patch files inside their retail allocations without moving extents.

    A replacement may change its logical byte size, but it must fit in the
    complete sector allocation owned by the retail file. Every matching ISO
    directory record receives the new size in both byte orders. The complete
    retail allocation is cleared before writing so stale compressed data can
    never remain addressable through a buggy length calculation.

    Raises:
        IsoError: If source/output alias, replacement geometry, or the rebuilt
            ISO violates the fixed-extent contract.
    """
    if source_iso.resolve() == output_iso.resolve():
        raise IsoError("source and output ISO paths must differ")
    if not replacements:
        raise IsoError("at least one ISO replacement is required")
    entries = read_entries(source_iso)
    plans: list[tuple[IsoEntry, tuple[IsoEntry, ...], str, bytes]] = []
    occupied: list[tuple[int, int, str]] = []
    for target, replacement_path in sorted(replacements.items()):
        records = _matching_file_records(entries, target)
        entry = records[0]
        payload = replacement_path.read_bytes()
        if not payload:
            raise IsoError(f"{target}: refusing to install an empty file")
        if len(payload) > entry.allocated_size:
            raise IsoError(
                f"{target}: replacement is {len(payload)} bytes but its retail "
                f"allocation is only {entry.allocated_size} bytes"
            )
        start = entry.extent * SECTOR_SIZE
        end = start + entry.allocated_size
        for other_start, other_end, other_target in occupied:
            if start < other_end and other_start < end:
                raise IsoError(
                    f"{target} allocation overlaps replacement {other_target}"
                )
        occupied.append((start, end, target))
        plans.append((entry, records, target, payload))

    output_iso.parent.mkdir(parents=True, exist_ok=True)
    with source_iso.open("rb") as source, output_iso.open("wb") as output:
        while block := source.read(1024 * 1024):
            output.write(block)
    with output_iso.open("r+b") as output:
        for entry, records, _target, payload in plans:
            output.seek(entry.extent * SECTOR_SIZE)
            output.write(bytes(entry.allocated_size))
            output.seek(entry.extent * SECTOR_SIZE)
            output.write(payload)
            size_le = len(payload).to_bytes(4, "little")
            size_be = len(payload).to_bytes(4, "big")
            for record in records:
                output.seek(record.record_offset + 10)
                output.write(size_le)
                output.write(size_be)
    if output_iso.stat().st_size != source_iso.stat().st_size:
        raise IsoError("fixed-extent patch changed the ISO byte length")
    output_entries = read_entries(output_iso)
    report = []
    for entry, records, target, payload in plans:
        installed = unique_file(output_entries, target)
        if installed.extent != entry.extent or installed.size != len(payload):
            raise IsoError(f"{target}: installed ISO record did not verify")
        with output_iso.open("rb") as output:
            output.seek(entry.extent * SECTOR_SIZE)
            installed_payload = output.read(len(payload))
            padding = output.read(entry.allocated_size - len(payload))
        if installed_payload != payload or any(padding):
            raise IsoError(f"{target}: installed payload or zero padding differs")
        report.append(
            {
                "target": target,
                "extent": entry.extent,
                "retail_size": entry.size,
                "output_size": len(payload),
                "allocated_size": entry.allocated_size,
                "headroom": entry.allocated_size - len(payload),
                "directory_records_updated": len(records),
            }
        )
    return report

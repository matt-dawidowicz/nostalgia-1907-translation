#!/usr/bin/env python3
"""Strict MODE1/2352 conversion for a fixed-geometry Mega-CD data track."""

from __future__ import annotations

from pathlib import Path


RAW_SECTOR_SIZE = 2352
ISO_SECTOR_SIZE = 2048
USER_DATA_OFFSET = 16
MODE_OFFSET = 15
EDC_OFFSET = 0x810
ZERO_OFFSET = 0x814
ECC_P_OFFSET = 0x81C
ECC_Q_OFFSET = 0x8C8
ECC_END = 0x930
SYNC = b"\x00" + b"\xFF" * 10 + b"\x00"
BOOT_SIGNATURE = b"SEGADISCSYSTEM  "


class RawCdError(ValueError):
    """Raised when a raw track violates MODE1/2352 invariants."""


def _edc_table() -> tuple[int, ...]:
    """Create the CD-ROM EDC lookup table."""
    values: list[int] = []
    for seed in range(256):
        value = seed
        for _ in range(8):
            value = (value >> 1) ^ (0xD8018001 if value & 1 else 0)
        values.append(value & 0xFFFFFFFF)
    return tuple(values)


def _ecc_tables() -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Create the forward and inverse GF(2^8) tables used by CD parity."""
    forward: list[int] = []
    inverse = [0] * 256
    for seed in range(256):
        value = ((seed << 1) ^ (0x11D if seed & 0x80 else 0)) & 0xFF
        forward.append(value)
        inverse[seed ^ value] = seed
    return tuple(forward), tuple(inverse)


EDC_TABLE = _edc_table()
ECC_FORWARD, ECC_INVERSE = _ecc_tables()


def edc(data: bytes | bytearray | memoryview) -> int:
    """Calculate the little-endian CD-ROM error-detection code."""
    value = 0
    for byte in data:
        value = ((value >> 8) ^ EDC_TABLE[(value ^ byte) & 0xFF]) & 0xFFFFFFFF
    return value


def ecc_plane(
    data: bytes | bytearray | memoryview,
    major_count: int,
    minor_count: int,
    major_multiplier: int,
    minor_increment: int,
) -> bytes:
    """Calculate one Reed-Solomon parity plane."""
    data_size = major_count * minor_count
    output = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_multiplier + (major & 1)
        parity_a = 0
        parity_b = 0
        for _ in range(minor_count):
            byte = data[index]
            index = (index + minor_increment) % data_size
            parity_a ^= byte
            parity_b ^= byte
            parity_a = ECC_FORWARD[parity_a]
        parity_a = ECC_INVERSE[ECC_FORWARD[parity_a] ^ parity_b]
        output[major] = parity_a
        output[major + major_count] = parity_a ^ parity_b
    return bytes(output)


def validate_sector_header(sector: bytes | bytearray, sector_index: int) -> None:
    """Reject a sector that is not a correctly addressed MODE1 sector."""
    if len(sector) != RAW_SECTOR_SIZE:
        raise RawCdError(f"sector {sector_index}: short raw sector")
    if sector[:12] != SYNC:
        raise RawCdError(f"sector {sector_index}: invalid sync pattern")
    if sector[MODE_OFFSET] != 1:
        raise RawCdError(f"sector {sector_index}: expected MODE1")
    if sector[12:15] != sector_msf(sector_index):
        raise RawCdError(f"sector {sector_index}: invalid MSF address")


def regenerate_checksums(sector: bytearray) -> None:
    """Regenerate EDC, reserved bytes, and both ECC planes in place."""
    if len(sector) != RAW_SECTOR_SIZE or sector[:12] != SYNC or sector[MODE_OFFSET] != 1:
        raise RawCdError("cannot checksum a non-MODE1/2352 sector")
    sector[EDC_OFFSET:ZERO_OFFSET] = edc(sector[:EDC_OFFSET]).to_bytes(4, "little")
    sector[ZERO_OFFSET:ECC_P_OFFSET] = b"\0" * (ECC_P_OFFSET - ZERO_OFFSET)
    sector[ECC_P_OFFSET:ECC_Q_OFFSET] = ecc_plane(
        sector[0x0C:ECC_P_OFFSET], 86, 24, 2, 86
    )
    sector[ECC_Q_OFFSET:ECC_END] = ecc_plane(
        sector[0x0C:ECC_Q_OFFSET], 52, 43, 86, 88
    )


def _bcd(value: int) -> int:
    """Encode 0 through 99 as packed binary-coded decimal."""
    if not 0 <= value <= 99:
        raise RawCdError(f"BCD value outside 0..99: {value}")
    return (value // 10 << 4) | value % 10


def sector_msf(sector_index: int) -> bytes:
    """Return the absolute minute-second-frame address for a data sector."""
    if sector_index < 0:
        raise RawCdError("sector index cannot be negative")
    absolute = sector_index + 150
    minutes, remainder = divmod(absolute, 60 * 75)
    seconds, frames = divmod(remainder, 75)
    return bytes((_bcd(minutes), _bcd(seconds), _bcd(frames)))


def verify_sector_checksums(sector: bytes | bytearray) -> bool:
    """Return whether a MODE1 sector's stored EDC/ECC bytes are correct."""
    candidate = bytearray(sector)
    stored = bytes(candidate[EDC_OFFSET:ECC_END])
    regenerate_checksums(candidate)
    return bytes(candidate[EDC_OFFSET:ECC_END]) == stored


def raw_to_iso(raw_path: Path, iso_path: Path, *, verify: bool = True) -> int:
    """Extract all 2048-byte user-data sectors from a raw Track 1 image."""
    size = raw_path.stat().st_size
    if size % RAW_SECTOR_SIZE:
        raise RawCdError(f"{raw_path}: size is not divisible by {RAW_SECTOR_SIZE}")
    sector_count = size // RAW_SECTOR_SIZE
    iso_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("rb") as source, iso_path.open("wb") as output:
        for sector_index in range(sector_count):
            sector = source.read(RAW_SECTOR_SIZE)
            validate_sector_header(sector, sector_index)
            if verify and not verify_sector_checksums(sector):
                raise RawCdError(f"sector {sector_index}: invalid EDC/ECC")
            output.write(sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE])
    return sector_count


def iso_to_raw_fixed(
    template_raw_path: Path, iso_path: Path, output_raw_path: Path
) -> int:
    """Rebuild Track 1 using the retail raw sectors as an exact-size template."""
    raw_size = template_raw_path.stat().st_size
    iso_size = iso_path.stat().st_size
    if raw_size % RAW_SECTOR_SIZE:
        raise RawCdError("template Track 1 has a partial raw sector")
    if iso_size % ISO_SECTOR_SIZE:
        raise RawCdError("ISO has a partial user-data sector")
    raw_sectors = raw_size // RAW_SECTOR_SIZE
    iso_sectors = iso_size // ISO_SECTOR_SIZE
    if iso_sectors != raw_sectors:
        raise RawCdError(
            "fixed-geometry rebuild requires identical sector counts: "
            f"retail={raw_sectors}, rebuilt={iso_sectors}"
        )

    output_raw_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        template_raw_path.open("rb") as template,
        iso_path.open("rb") as iso,
        output_raw_path.open("wb") as output,
    ):
        for sector_index in range(raw_sectors):
            sector = bytearray(template.read(RAW_SECTOR_SIZE))
            payload = iso.read(ISO_SECTOR_SIZE)
            validate_sector_header(sector, sector_index)
            if len(payload) != ISO_SECTOR_SIZE:
                raise RawCdError(f"sector {sector_index}: short ISO read")
            sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE] = payload
            regenerate_checksums(sector)
            output.write(sector)
    return raw_sectors


def verify_track(raw_path: Path, *, compare_boot_to: Path | None = None) -> dict[str, object]:
    """Validate every sector plus the Mega-CD signature and optional boot payload."""
    size = raw_path.stat().st_size
    if size % RAW_SECTOR_SIZE:
        raise RawCdError("track has a partial raw sector")
    sector_count = size // RAW_SECTOR_SIZE
    boot_payload = bytearray()
    with raw_path.open("rb") as source:
        for sector_index in range(sector_count):
            sector = source.read(RAW_SECTOR_SIZE)
            validate_sector_header(sector, sector_index)
            if not verify_sector_checksums(sector):
                raise RawCdError(f"sector {sector_index}: invalid EDC/ECC")
            if sector_index < 16:
                boot_payload.extend(
                    sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE]
                )
    if bytes(boot_payload[:16]) != BOOT_SIGNATURE:
        raise RawCdError("Mega-CD boot signature is missing")

    boot_matches = None
    if compare_boot_to is not None:
        reference = bytearray()
        with compare_boot_to.open("rb") as source:
            for sector_index in range(16):
                sector = source.read(RAW_SECTOR_SIZE)
                validate_sector_header(sector, sector_index)
                reference.extend(
                    sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE]
                )
        boot_matches = bytes(reference) == bytes(boot_payload)
        if not boot_matches:
            raise RawCdError("boot-system payload differs from retail Track 1")
    return {
        "sector_count": sector_count,
        "size": size,
        "boot_signature": BOOT_SIGNATURE.decode("ascii"),
        "boot_matches_retail": boot_matches,
        "all_sector_checksums_valid": True,
    }


def write_two_track_cue(cue_path: Path, data_track: Path, audio_track: Path) -> None:
    """Write the retail-compatible two-track CUE with CRLF line endings."""
    if cue_path.parent.resolve() != data_track.parent.resolve() or cue_path.parent.resolve() != audio_track.parent.resolve():
        raise RawCdError("CUE and both track files must share one directory")
    text = (
        f'FILE "{data_track.name}" BINARY\r\n'
        "  TRACK 01 MODE1/2352\r\n"
        "    INDEX 01 00:00:00\r\n"
        f'FILE "{audio_track.name}" BINARY\r\n'
        "  TRACK 02 AUDIO\r\n"
        "    INDEX 00 00:00:00\r\n"
        "    INDEX 01 00:02:00\r\n"
    )
    cue_path.write_bytes(text.encode("ascii"))

#!/usr/bin/env python3
"""Convert the Mega-CD MODE1/2352 data track without changing its geometry.

Each 2,352-byte raw sector contains a 16-byte sync/address/mode header, 2,048
bytes of ISO user data, EDC/reserved bytes, and two ECC parity planes. Extraction
validates the complete retail sector before exposing its user data. Rebuilding
uses the corresponding retail sector as a template, replaces only user data,
and regenerates EDC/ECC.

This module owns raw-sector integrity and the two-track CUE syntax. It does not
interpret ISO files or translation data. ``verify_track`` additionally checks
the Mega-CD boot signature and can prove that the boot payload is unchanged
from retail.

See ``docs/BINARY_FORMATS.md`` for the sector map and checksum boundaries.
"""

from __future__ import annotations

import hashlib
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
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
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


def validate_sector_header(
    sector: bytes | bytearray, sector_index: int
) -> None:
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
    """Regenerate MODE1 EDC, reserved bytes, and both ECC planes in place.

    Args:
        sector: Mutable complete 2,352-byte MODE1 sector.

    Raises:
        RawCdError: If the buffer lacks the raw sync, size, or MODE1 marker.

    Side Effects:
        Replaces only the checksum/reserved ranges of ``sector``. Header and
        2,048-byte user data are not altered.
    """
    if (
        len(sector) != RAW_SECTOR_SIZE
        or sector[:12] != SYNC
        or sector[MODE_OFFSET] != 1
    ):
        raise RawCdError("cannot checksum a non-MODE1/2352 sector")
    sector[EDC_OFFSET:ZERO_OFFSET] = edc(sector[:EDC_OFFSET]).to_bytes(
        4, "little"
    )
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
    """Extract all 2,048-byte user-data sectors from raw Track 1.

    When ``verify`` is true, every address and EDC/ECC checksum is validated
    before its payload is accepted.

    Returns:
        Number of sectors written to ``iso_path``.

    Raises:
        RawCdError: If input and output alias or raw-sector validation fails.

    Side Effects:
        Creates parent directories and replaces ``iso_path``; the raw input is
        read-only.
    """
    if raw_path.resolve() == iso_path.resolve():
        raise RawCdError("raw input and ISO output paths must differ")
    size = raw_path.stat().st_size
    if size % RAW_SECTOR_SIZE:
        raise RawCdError(
            f"{raw_path}: size is not divisible by {RAW_SECTOR_SIZE}"
        )
    sector_count = size // RAW_SECTOR_SIZE
    iso_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("rb") as source, iso_path.open("wb") as output:
        for sector_index in range(sector_count):
            sector = source.read(RAW_SECTOR_SIZE)
            validate_sector_header(sector, sector_index)
            if verify and not verify_sector_checksums(sector):
                raise RawCdError(f"sector {sector_index}: invalid EDC/ECC")
            output.write(
                sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE]
            )
    return sector_count


def iso_to_raw_fixed(
    template_raw_path: Path,
    iso_path: Path,
    output_raw_path: Path,
    *,
    trust_template_checksums: bool = False,
) -> int:
    """Rebuild Track 1 using retail raw sectors as an exact-size template.

    The logical ISO must contain exactly one user-data payload per template
    sector. Headers are preserved from retail. Changed user-data sectors receive
    freshly generated EDC/ECC. When ``trust_template_checksums`` is true, an
    unchanged user-data sector is copied byte-for-byte instead; callers may use
    that fast path only after independently authenticating the complete template
    bytes (the clean rebuild does so with the frozen retail SHA-256).

    Returns:
        Number of raw sectors written.

    Raises:
        RawCdError: If paths alias, sizes, headers, or rebuilt geometry violate
            the fixed-geometry contract.
    """
    output = output_raw_path.resolve()
    if output in {template_raw_path.resolve(), iso_path.resolve()}:
        raise RawCdError(
            "raw output path must differ from both rebuild inputs"
        )
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
        output_raw_path.open("wb") as output_stream,
    ):
        for sector_index in range(raw_sectors):
            sector = bytearray(template.read(RAW_SECTOR_SIZE))
            payload = iso.read(ISO_SECTOR_SIZE)
            validate_sector_header(sector, sector_index)
            if len(payload) != ISO_SECTOR_SIZE:
                raise RawCdError(f"sector {sector_index}: short ISO read")
            original_payload = sector[
                USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE
            ]
            if trust_template_checksums and payload == original_payload:
                output_stream.write(sector)
                continue
            sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE] = (
                payload
            )
            regenerate_checksums(sector)
            output_stream.write(sector)
    return raw_sectors


def _sha256_file(path: Path) -> str:
    """Return an uppercase SHA-256 digest for one streamed file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def verify_track(
    raw_path: Path,
    *,
    compare_boot_to: Path | None = None,
    trusted_reference: Path | None = None,
    trusted_reference_sha256: str | None = None,
) -> dict[str, object]:
    """Validate raw sectors, boot signature, and optional trusted-reference delta.

    By default every sector receives a fresh EDC/ECC calculation.  A caller may
    instead supply both ``trusted_reference`` and its independently established
    SHA-256.  The reference bytes are authenticated before sector processing; an
    output sector that is byte-identical to that authenticated reference inherits
    the reference's checksum evidence, while every changed sector still receives
    full EDC/ECC verification.

    Args:
        raw_path: MODE1/2352 Track 1 to inspect.
        compare_boot_to: Optional template whose first 16 user-data sectors must
            match exactly.
        trusted_reference: Optional already-certified Track 1 used as the source
            of checksum evidence for byte-identical sectors.
        trusted_reference_sha256: Exact expected digest for ``trusted_reference``.
            It must be supplied together with the reference.

    Returns:
        Sector count, boot evidence, verification mode, and the number of sectors
        verified directly versus inherited by exact authenticated byte identity.

    Raises:
        RawCdError: If geometry, address, checksum, reference identity, signature,
            or requested boot equality fails.
    """
    size = raw_path.stat().st_size
    if size % RAW_SECTOR_SIZE:
        raise RawCdError("track has a partial raw sector")
    sector_count = size // RAW_SECTOR_SIZE

    if (trusted_reference is None) != (trusted_reference_sha256 is None):
        raise RawCdError(
            "trusted reference and trusted reference SHA-256 must be supplied together"
        )
    expected_reference_hash = None
    if trusted_reference is not None:
        if trusted_reference.stat().st_size != size:
            raise RawCdError("trusted reference Track 1 geometry differs")
        expected_reference_hash = str(trusted_reference_sha256).upper()
        if len(expected_reference_hash) != 64 or any(
            character not in "0123456789ABCDEF"
            for character in expected_reference_hash
        ):
            raise RawCdError(
                "trusted reference SHA-256 is not 64-digit hexadecimal"
            )
        actual_reference_hash = _sha256_file(trusted_reference)
        if actual_reference_hash != expected_reference_hash:
            raise RawCdError(
                "trusted reference SHA-256 mismatch: "
                f"{actual_reference_hash} != {expected_reference_hash}"
            )

    boot_payload = bytearray()
    directly_verified = 0
    inherited = 0
    reference_stream = (
        trusted_reference.open("rb") if trusted_reference is not None else None
    )
    try:
        with raw_path.open("rb") as source:
            for sector_index in range(sector_count):
                sector = source.read(RAW_SECTOR_SIZE)
                validate_sector_header(sector, sector_index)
                reference_sector = (
                    reference_stream.read(RAW_SECTOR_SIZE)
                    if reference_stream is not None
                    else None
                )
                if reference_sector is not None and sector == reference_sector:
                    inherited += 1
                else:
                    if not verify_sector_checksums(sector):
                        raise RawCdError(
                            f"sector {sector_index}: invalid EDC/ECC"
                        )
                    directly_verified += 1
                if sector_index < 16:
                    boot_payload.extend(
                        sector[
                            USER_DATA_OFFSET : USER_DATA_OFFSET
                            + ISO_SECTOR_SIZE
                        ]
                    )
        if reference_stream is not None and reference_stream.read(1):
            raise RawCdError("trusted reference has trailing raw data")
    finally:
        if reference_stream is not None:
            reference_stream.close()

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
                    sector[
                        USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE
                    ]
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
        "checksum_verification_mode": (
            "trusted-reference-delta"
            if trusted_reference is not None
            else "full-recalculation"
        ),
        "checksum_verified_sector_count": directly_verified,
        "checksum_inherited_sector_count": inherited,
        "trusted_reference_sha256": expected_reference_hash,
    }


def write_two_track_cue(
    cue_path: Path, data_track: Path, audio_track: Path
) -> None:
    """Write the retail-compatible two-track CUE with exact CRLF endings.

    All three files must share one directory so the CUE contains portable base
    names rather than machine-specific paths. Track 2 retains the retail
    two-second pregap represented by INDEX 00 and INDEX 01.
    """
    cue_resolved = cue_path.resolve()
    data_resolved = data_track.resolve()
    audio_resolved = audio_track.resolve()
    if data_resolved == audio_resolved:
        raise RawCdError("data and audio track paths must differ")
    if cue_resolved in {data_resolved, audio_resolved}:
        raise RawCdError("CUE output path must differ from both track files")
    if (
        cue_path.parent.resolve() != data_track.parent.resolve()
        or cue_path.parent.resolve() != audio_track.parent.resolve()
    ):
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

"""Synthetic source-only coverage for the North American region wrapper."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
REGION = ROOT / "work" / "region_variant"

from work.region_variant import build_us_bios_test as region  # noqa: E402
from work.clean_rebuild import raw_cd  # noqa: E402


def synthetic_boot() -> bytes:
    """Return a structurally valid 32 KiB Japanese boot fixture."""
    boot = bytearray(region.BOOT_SIZE)
    for index in range(region.ORIGINAL_USED_END):
        boot[index] = index % 251 + 1
    boot[:16] = b"SEGADISCSYSTEM  "
    for offset, value in region.EXPECTED_HEADER_FIELDS.items():
        boot[offset : offset + 4] = value.to_bytes(4, "big")
    boot[0x1F0:0x200] = b"J" + b" " * 15
    boot[region.ORIGINAL_USED_END - 1] = 0x7F
    return bytes(boot)


def synthetic_security() -> bytes:
    """Return a deterministic security-program-sized byte fixture."""
    size = region.SECURITY_END - region.SECURITY_START
    return bytes((index * 17 + 3) % 256 for index in range(size))


def raw_sector(sector_index: int, user_data: bytes) -> bytes:
    """Encode one valid synthetic MODE1/2352 sector."""
    if len(user_data) != raw_cd.ISO_SECTOR_SIZE:
        raise ValueError("synthetic user data must fill one logical sector")
    sector = bytearray(raw_cd.RAW_SECTOR_SIZE)
    sector[:12] = raw_cd.SYNC
    sector[12:15] = raw_cd.sector_msf(sector_index)
    sector[raw_cd.MODE_OFFSET] = 1
    sector[
        raw_cd.USER_DATA_OFFSET : raw_cd.USER_DATA_OFFSET + raw_cd.ISO_SECTOR_SIZE
    ] = user_data
    raw_cd.regenerate_checksums(sector)
    return bytes(sector)


def raw_track_from_boot(boot: bytes) -> bytes:
    """Encode the 16-sector boot area as a complete synthetic raw track."""
    return b"".join(
        raw_sector(
            sector_index,
            boot[
                sector_index
                * raw_cd.ISO_SECTOR_SIZE : (sector_index + 1)
                * raw_cd.ISO_SECTOR_SIZE
            ],
        )
        for sector_index in range(16)
    )


class RegionWrapperTests(unittest.TestCase):
    """Prove wrapper mutation boundaries without a BIOS or game image."""

    def test_region_basename_rejects_path_syntax(self) -> None:
        """Keep wrapper artifact names inside their selected staging directory."""
        self.assertEqual(region._validate_basename("Nostalgia1907_Test"), "Nostalgia1907_Test")
        for basename in ("", "../escape", "nested/name", "nested\\name", ".hidden"):
            with self.subTest(basename=basename):
                with self.assertRaisesRegex(region.RegionVariantError, "filename stem"):
                    region._validate_basename(basename)

    def test_wrapper_has_no_report_only_publication_entry_point(self) -> None:
        """Prevent staged JSON reports from authorizing an external publication."""
        self.assertFalse(hasattr(region, "publish_existing"))

    def test_wrapped_boot_preserves_metadata_and_relocates_exactly(self) -> None:
        """Keep the Japanese outer header and original payload byte-exact."""
        original = synthetic_boot()
        security = synthetic_security()
        output = region.build_wrapped_boot(original, security)

        self.assertEqual(output[0x1F0:0x200], original[0x1F0:0x200])
        self.assertEqual(
            output[region.SECURITY_START : region.SECURITY_END], security
        )
        self.assertEqual(
            output[region.RELOCATION_START : region.RELOCATION_END],
            original[: region.ORIGINAL_USED_END],
        )
        self.assertEqual(
            output[region.RELOCATION_END :], original[region.RELOCATION_END :]
        )
        for offset, expected in region.OUTPUT_HEADER_FIELDS.items():
            self.assertEqual(int.from_bytes(output[offset : offset + 4], "big"), expected)

    def test_wrapped_boot_rejects_unproven_relocation_capacity(self) -> None:
        """Refuse a baseline whose supposedly unused boot tail is occupied."""
        original = bytearray(synthetic_boot())
        original[region.ORIGINAL_USED_END] = 1
        with self.assertRaisesRegex(region.RegionVariantError, "zero-filled"):
            region.build_wrapped_boot(bytes(original), synthetic_security())

    def test_raw_track_wrapper_changes_only_sectors_zero_through_four(self) -> None:
        """Validate EDC/ECC and reject a later-sector mutation explicitly."""
        original_boot = synthetic_boot()
        security = synthetic_security()
        wrapped_boot = region.build_wrapped_boot(original_boot, security)
        expected_security_hash = hashlib.sha256(security).hexdigest().upper()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            output = root / "output.bin"
            source.write_bytes(raw_track_from_boot(original_boot))
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest().upper()
            with patch.object(
                region, "EXPECTED_US_SECURITY_SHA256", expected_security_hash
            ):
                self.assertEqual(
                    region._write_region_track(source, output, wrapped_boot),
                    [0, 1, 2, 3, 4],
                )
                report = region._validate_track_delta(
                    source, output, wrapped_boot, source_hash
                )
                self.assertEqual(report["changed_raw_sectors"], [0, 1, 2, 3, 4])
                self.assertTrue(report["all_sector_checksums_valid"])
                self.assertEqual(report["checksum_verified_sector_count"], 5)
                self.assertEqual(report["checksum_inherited_sector_count"], 11)

                damaged = bytearray(output.read_bytes())
                start = 5 * raw_cd.RAW_SECTOR_SIZE
                sector = bytearray(damaged[start : start + raw_cd.RAW_SECTOR_SIZE])
                sector[raw_cd.USER_DATA_OFFSET] ^= 0x01
                raw_cd.regenerate_checksums(sector)
                damaged[start : start + raw_cd.RAW_SECTOR_SIZE] = sector
                output.write_bytes(damaged)
                with self.assertRaisesRegex(
                    region.RegionVariantError, "outside the wrapper"
                ):
                    region._validate_track_delta(
                        source, output, wrapped_boot, source_hash
                    )


if __name__ == "__main__":
    unittest.main()

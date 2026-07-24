#!/usr/bin/env python3
"""Build and validate a deterministic U.S.-BIOS test variant of Nostalgia 1907."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
CLEAN_REBUILD = HERE.parent / "clean_rebuild"
sys.path.insert(0, str(CLEAN_REBUILD))

from raw_cd import (  # noqa: E402
    ISO_SECTOR_SIZE,
    RAW_SECTOR_SIZE,
    USER_DATA_OFFSET,
    regenerate_checksums,
    validate_sector_header,
    verify_sector_checksums,
    write_two_track_cue,
)


BOOT_SIZE = 16 * ISO_SECTOR_SIZE
SECURITY_START = 0x200
SECURITY_END = 0x784
WRAPPER_START = SECURITY_END
WRAPPER_END = 0x7B6
TAG_START = WRAPPER_END
TAG_END = 0x7E5
RELOCATION_START = 0x800
ORIGINAL_USED_END = 0x1884
RELOCATION_END = RELOCATION_START + ORIGINAL_USED_END
ORIGINAL_APP_START = 0x356

EXPECTED_HEADER_FIELDS = {
    0x30: 0x200,
    0x34: 0x600,
    0x40: 0x800,
    0x44: 0x7800,
}
OUTPUT_HEADER_FIELDS = {
    0x30: 0x800,
    0x34: 0x800,
    0x40: 0x1000,
    0x44: 0x7800,
}

EXPECTED_V7_TRACK1_SHA256 = (
    "E8B30EA76E02656B5349898AF35FB3CF597C9E766FB8AEDDEAED617DFFD7EDC7"
)
EXPECTED_TRACK2_SHA256 = (
    "F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991"
)
EXPECTED_US_BIOS_SHA256 = (
    "B1C2036B79467514EAAA69C76E5BA83801621E821059CAA53CB921A0B21E3AF4"
)
EXPECTED_US_SECURITY_SHA256 = (
    "6DDF49D3E9EDFFE66B98776507AAE447B3B0A90D96D3DAE4572618D258D1259D"
)
EXPECTED_CANONICAL_ISO_SHA256 = (
    "49AD02E1923B9ACBFD8E68A0D764B8F5A2A5459479C1AB616F5314372D7F516C"
)

US_BIOS_SECURITY_SLICE = slice(0x6DF6, 0x7374)
US_SECURITY_PREFIX = bytes.fromhex("43 FA 00 0A 4E B8")
CONVERSION_TAG = b"MoDJConverted from Japan to US by ConvSCD 1.10\0"

# The wrapper first copies its second stage to high work RAM.  The second stage
# restores the relocated Japanese application to its original execution address
# before jumping to it.  Bytes 0x24:0x26 are filled from the guarded boot header.
WRAPPER_TEMPLATE = bytes.fromhex(
    "41 FA 00 14 43 F8 FF 00 30 3C 00 06 22 D8 51 C8 "
    "FF FC 4E F8 FF 00 20 7C 00 FF 09 56 22 7C 00 FF "
    "01 56 30 3C 12 34 32 D8 51 C8 FF FC 4E F9 00 FF "
    "01 56"
)


class RegionVariantError(ValueError):
    """Raised when the input or output violates the guarded region recipe."""


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _bytes_sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _read_be32(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big")


def _write_be32(data: bytearray, offset: int, value: int) -> None:
    data[offset : offset + 4] = value.to_bytes(4, "big")


def _ensure_empty(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise RegionVariantError(f"refusing to reuse non-empty directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _read_boot(raw_path: Path) -> bytes:
    """Read and validate the first 16 MODE1 user-data sectors."""
    boot = bytearray()
    with raw_path.open("rb") as source:
        for sector_index in range(16):
            sector = source.read(RAW_SECTOR_SIZE)
            validate_sector_header(sector, sector_index)
            if not verify_sector_checksums(sector):
                raise RegionVariantError(
                    f"{raw_path}: sector {sector_index} has invalid EDC/ECC"
                )
            boot.extend(
                sector[
                    USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE
                ]
            )
    if len(boot) != BOOT_SIZE:
        raise RegionVariantError(f"{raw_path}: incomplete 32 KiB boot area")
    return bytes(boot)


def _derive_us_security(us_bios: Path) -> bytes:
    """Derive the licensed U.S. disc security program from the supplied BIOS."""
    if us_bios.stat().st_size != 128 * 1024:
        raise RegionVariantError("U.S. BIOS is not exactly 128 KiB")
    bios_hash = sha256(us_bios)
    if bios_hash != EXPECTED_US_BIOS_SHA256:
        raise RegionVariantError(
            "unexpected U.S. BIOS hash: "
            f"{bios_hash}; expected {EXPECTED_US_BIOS_SHA256}"
        )
    bios = us_bios.read_bytes()
    security = US_SECURITY_PREFIX + bios[US_BIOS_SECURITY_SLICE]
    if len(security) != SECURITY_END - SECURITY_START:
        raise RegionVariantError("derived U.S. security program has the wrong size")
    security_hash = _bytes_sha256(security)
    if security_hash != EXPECTED_US_SECURITY_SHA256:
        raise RegionVariantError(
            "derived U.S. security program hash differs from the licensed reference"
        )
    return security


def _wrapper(input_boot: bytes) -> bytes:
    """Build the guarded 50-byte Japan-to-U.S. restoration wrapper."""
    main_start = _read_be32(input_boot, 0x30)
    main_length = _read_be32(input_boot, 0x34)
    app_offset = ORIGINAL_APP_START - main_start
    copy_count = main_length - app_offset
    if copy_count != 0x04AA:
        raise RegionVariantError(
            f"unexpected Nostalgia main-program copy count: 0x{copy_count:X}"
        )
    wrapper = bytearray(WRAPPER_TEMPLATE)
    wrapper[0x24:0x26] = copy_count.to_bytes(2, "big")
    if len(wrapper) != WRAPPER_END - WRAPPER_START:
        raise RegionVariantError("restoration wrapper has the wrong size")
    return bytes(wrapper)


def build_wrapped_boot(input_boot: bytes, us_security: bytes) -> bytes:
    """Return the canonical U.S.-security wrapper around the intact v7 boot."""
    if len(input_boot) != BOOT_SIZE:
        raise RegionVariantError("input boot area is not exactly 32 KiB")
    if input_boot[:16] != b"SEGADISCSYSTEM  ":
        raise RegionVariantError("Mega-CD boot signature is missing")
    for offset, expected in EXPECTED_HEADER_FIELDS.items():
        actual = _read_be32(input_boot, offset)
        if actual != expected:
            raise RegionVariantError(
                f"unexpected boot header field 0x{offset:X}: "
                f"0x{actual:X} != 0x{expected:X}"
            )
    if input_boot[0x1F0:0x200] != b"J" + b" " * 15:
        raise RegionVariantError("outer Japanese country metadata changed")
    if any(input_boot[ORIGINAL_USED_END:]):
        raise RegionVariantError(
            "validated relocation capacity is no longer zero-filled"
        )

    last_nonzero = max(
        index for index, value in enumerate(input_boot) if value != 0
    )
    if last_nonzero != ORIGINAL_USED_END - 1:
        raise RegionVariantError(
            f"unexpected last used boot byte: 0x{last_nonzero:X}"
        )

    output = bytearray(input_boot)
    for offset, value in OUTPUT_HEADER_FIELDS.items():
        _write_be32(output, offset, value)
    output[SECURITY_START:SECURITY_END] = us_security
    output[WRAPPER_START:WRAPPER_END] = _wrapper(input_boot)
    if len(CONVERSION_TAG) != TAG_END - TAG_START:
        raise RegionVariantError("conversion tag has the wrong size")
    output[TAG_START:TAG_END] = CONVERSION_TAG
    output[TAG_END:RELOCATION_START] = b"\0" * (
        RELOCATION_START - TAG_END
    )
    output[RELOCATION_START:RELOCATION_END] = input_boot[:ORIGINAL_USED_END]

    if output[0x1F0:0x200] != input_boot[0x1F0:0x200]:
        raise RegionVariantError("outer country metadata was altered")
    if output[RELOCATION_START:RELOCATION_END] != input_boot[:ORIGINAL_USED_END]:
        raise RegionVariantError("original boot payload was not relocated exactly")
    if output[RELOCATION_END:] != input_boot[RELOCATION_END:]:
        raise RegionVariantError("boot bytes after the relocation changed")
    return bytes(output)


def _write_region_track(
    input_track: Path, output_track: Path, output_boot: bytes
) -> list[int]:
    """Patch only changed boot sectors and regenerate their MODE1 checksums."""
    size = input_track.stat().st_size
    if size % RAW_SECTOR_SIZE:
        raise RegionVariantError("input Track 1 has a partial raw sector")
    sector_count = size // RAW_SECTOR_SIZE
    changed: list[int] = []
    output_track.parent.mkdir(parents=True, exist_ok=True)
    with (
        input_track.open("rb") as source,
        output_track.open("wb") as output,
    ):
        for sector_index in range(sector_count):
            sector = bytearray(source.read(RAW_SECTOR_SIZE))
            validate_sector_header(sector, sector_index)
            if sector_index < 16:
                start = sector_index * ISO_SECTOR_SIZE
                replacement = output_boot[start : start + ISO_SECTOR_SIZE]
                current = bytes(
                    sector[
                        USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE
                    ]
                )
                if replacement != current:
                    changed.append(sector_index)
                    sector[
                        USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE
                    ] = replacement
                    regenerate_checksums(sector)
            output.write(sector)
    if changed != [0, 1, 2, 3, 4]:
        raise RegionVariantError(f"unexpected changed raw sectors: {changed}")
    return changed


def iso_user_sha256(raw_path: Path) -> str:
    """Hash the logical 2048-byte user data without creating an ISO file."""
    digest = hashlib.sha256()
    with raw_path.open("rb") as source:
        sector_index = 0
        while sector := source.read(RAW_SECTOR_SIZE):
            validate_sector_header(sector, sector_index)
            if not verify_sector_checksums(sector):
                raise RegionVariantError(
                    f"{raw_path}: sector {sector_index} has invalid EDC/ECC"
                )
            digest.update(
                sector[
                    USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE
                ]
            )
            sector_index += 1
    return digest.hexdigest().upper()


def _validate_track_delta(
    input_track: Path,
    output_track: Path,
    expected_boot: bytes,
) -> dict[str, object]:
    """Prove the exact wrapper model and all raw-sector mutation boundaries."""
    if input_track.stat().st_size != output_track.stat().st_size:
        raise RegionVariantError("region variant changed Track 1 geometry")
    changed_sectors: list[int] = []
    raw_digest = hashlib.sha256()
    logical_digest = hashlib.sha256()
    with (
        input_track.open("rb") as source,
        output_track.open("rb") as output,
    ):
        sector_index = 0
        while left := source.read(RAW_SECTOR_SIZE):
            right = output.read(RAW_SECTOR_SIZE)
            if len(right) != RAW_SECTOR_SIZE:
                raise RegionVariantError("short region-variant sector")
            validate_sector_header(right, sector_index)
            if not verify_sector_checksums(right):
                raise RegionVariantError(
                    f"region variant sector {sector_index} has invalid EDC/ECC"
                )
            raw_digest.update(right)
            logical_digest.update(
                right[
                    USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE
                ]
            )
            if left != right:
                changed_sectors.append(sector_index)
                if sector_index >= 5:
                    raise RegionVariantError(
                        f"raw sector {sector_index} changed outside the wrapper"
                    )
                if left[:USER_DATA_OFFSET] != right[:USER_DATA_OFFSET]:
                    raise RegionVariantError(
                        f"raw sector {sector_index} header changed"
                    )
            sector_index += 1
        if output.read(1):
            raise RegionVariantError("region variant has trailing raw data")
    if changed_sectors != [0, 1, 2, 3, 4]:
        raise RegionVariantError(
            f"unexpected changed sector set: {changed_sectors}"
        )

    input_boot = _read_boot(input_track)
    output_boot = _read_boot(output_track)
    if output_boot != expected_boot:
        raise RegionVariantError("installed wrapper differs from the recipe")
    if output_boot[RELOCATION_START:RELOCATION_END] != input_boot[:ORIGINAL_USED_END]:
        raise RegionVariantError("relocated original boot bytes differ")
    if output_boot[RELOCATION_END:] != input_boot[RELOCATION_END:]:
        raise RegionVariantError("post-wrapper boot bytes differ")
    if output_boot[TAG_END:RELOCATION_START] != b"\0" * (
        RELOCATION_START - TAG_END
    ):
        raise RegionVariantError("post-tag padding is not canonical zero")
    if _bytes_sha256(output_boot[SECURITY_START:SECURITY_END]) != (
        EXPECTED_US_SECURITY_SHA256
    ):
        raise RegionVariantError("installed U.S. security hash changed")
    if output_boot[0x1F0:0x200] != input_boot[0x1F0:0x200]:
        raise RegionVariantError("outer Japanese metadata was not preserved")

    logical_hash = logical_digest.hexdigest().upper()
    if logical_hash != EXPECTED_CANONICAL_ISO_SHA256:
        raise RegionVariantError(
            "canonical logical ISO hash mismatch: "
            f"{logical_hash} != {EXPECTED_CANONICAL_ISO_SHA256}"
        )
    return {
        "sector_count": sector_index,
        "size": output_track.stat().st_size,
        "boot_signature": "SEGADISCSYSTEM  ",
        "all_sector_checksums_valid": True,
        "sha256": raw_digest.hexdigest().upper(),
        "logical_iso_sha256": logical_hash,
        "changed_raw_sectors": changed_sectors,
        "security_sha256": EXPECTED_US_SECURITY_SHA256,
        "outer_country_metadata": output_boot[0x1F0:0x200].decode("ascii"),
        "relocated_input_range": ["0x0000", "0x1884"],
        "relocated_output_range": ["0x0800", "0x2084"],
        "canonical_zero_pad": ["0x07E5", "0x0800"],
    }


def _build_once(
    baseline_track1: Path,
    baseline_track2: Path,
    us_bios: Path,
    product_root: Path,
    basename: str,
) -> dict[str, object]:
    _ensure_empty(product_root)
    input_boot = _read_boot(baseline_track1)
    us_security = _derive_us_security(us_bios)
    output_boot = build_wrapped_boot(input_boot, us_security)

    output_track1 = product_root / f"{basename}_Track1.bin"
    output_track2 = product_root / f"{basename}_Track2.bin"
    output_cue = product_root / f"{basename}.cue"
    _write_region_track(baseline_track1, output_track1, output_boot)
    shutil.copyfile(baseline_track2, output_track2)
    write_two_track_cue(output_cue, output_track1, output_track2)

    track1_report = _validate_track_delta(
        baseline_track1, output_track1, output_boot
    )
    if sha256(output_track2) != EXPECTED_TRACK2_SHA256:
        raise RegionVariantError("output Track 2 differs from retail")
    expected_cue = (
        f'FILE "{output_track1.name}" BINARY\r\n'
        "  TRACK 01 MODE1/2352\r\n"
        "    INDEX 01 00:00:00\r\n"
        f'FILE "{output_track2.name}" BINARY\r\n'
        "  TRACK 02 AUDIO\r\n"
        "    INDEX 00 00:00:00\r\n"
        "    INDEX 01 00:02:00\r\n"
    ).encode("ascii")
    if output_cue.read_bytes() != expected_cue:
        raise RegionVariantError("output CUE contents differ from the recipe")

    report = {
        "status": "PASS",
        "baseline_track1_sha256": EXPECTED_V7_TRACK1_SHA256,
        "us_bios_sha256": EXPECTED_US_BIOS_SHA256,
        "track1": track1_report,
        "track2": {
            "size": output_track2.stat().st_size,
            "sha256": sha256(output_track2),
        },
        "cue": {
            "size": output_cue.stat().st_size,
            "sha256": sha256(output_cue),
        },
    }
    (product_root / "verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def publish_existing(
    runs_root: Path,
    delivery_root: Path,
    basename: str,
) -> dict[str, object]:
    """Validate two completed staging products and publish run A."""
    run_a = runs_root / "run_a" / "product"
    run_b = runs_root / "run_b" / "product"
    first = json.loads(
        (run_a / "verification.json").read_text(encoding="utf-8")
    )
    second = json.loads(
        (run_b / "verification.json").read_text(encoding="utf-8")
    )
    if first.get("status") != "PASS" or second.get("status") != "PASS":
        raise RegionVariantError("a staged region build did not pass")
    report_hashes = {
        f"{basename}_Track1.bin": (
            first["track1"]["sha256"],
            second["track1"]["sha256"],
        ),
        f"{basename}_Track2.bin": (
            first["track2"]["sha256"],
            second["track2"]["sha256"],
        ),
        f"{basename}.cue": (
            first["cue"]["sha256"],
            second["cue"]["sha256"],
        ),
    }
    compared: dict[str, str] = {}
    for name, (left, right) in report_hashes.items():
        if left != right:
            raise RegionVariantError(
                f"two region builds differ for {name}: {left} != {right}"
            )
        for staged in (run_a / name, run_b / name):
            actual = sha256(staged)
            if actual != left:
                raise RegionVariantError(
                    f"staged artifact hash changed for {staged}: "
                    f"{actual} != {left}"
                )
        compared[name] = left

    _ensure_empty(delivery_root)
    for name in compared:
        shutil.copyfile(run_a / name, delivery_root / name)
    report = {
        "status": "PASS",
        "purpose": "U.S. Sega CD BIOS startup test; game content remains v7",
        "pipeline": (
            "validated v7 Track 1 -> licensed U.S. security wrapper derived "
            "from supplied BIOS -> fixed-geometry BIN/CUE"
        ),
        "two_clean_region_builds_byte_identical": True,
        "source_v7_track1_sha256": EXPECTED_V7_TRACK1_SHA256,
        "source_track2_sha256": EXPECTED_TRACK2_SHA256,
        "us_bios_sha256": EXPECTED_US_BIOS_SHA256,
        "us_security_sha256": EXPECTED_US_SECURITY_SHA256,
        "canonical_logical_iso_sha256": EXPECTED_CANONICAL_ISO_SHA256,
        "artifact_sha256": compared,
        "verification": first,
        "second_verification": second,
        "preservation": {
            "outer_japanese_metadata_preserved": True,
            "original_boot_payload_relocated_exactly": True,
            "raw_sectors_after_4_byte_identical": True,
            "track2_audio_byte_identical": True,
            "translation_records_changed": 0,
            "scn_data_changed": False,
            "iso_files_or_extents_changed": False,
        },
    }
    (delivery_root / "final_verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    notes = (
        "# Nostalgia 1907 v7 - U.S. BIOS test variant\n\n"
        "This is a separate test derivative of the validated v7 translation. "
        "It installs the licensed U.S. Sega CD security program derived from "
        "the verified v2.00w BIOS and uses a guarded wrapper to restore the "
        "original Nostalgia bootstrap before the game starts.\n\n"
        "The original outer Japanese metadata is intentionally retained. The "
        "BIOS region lock is established by the security program, not by "
        "changing the metadata byte. The original boot payload is relocated "
        "byte-for-byte; raw sectors 5 onward, every ISO file and extent, all "
        "translation/SCN data, Track 2 audio, and disc geometry are unchanged.\n\n"
        "The wrapper was built twice with byte-identical BIN/CUE results. "
        "Automated validation proves the exact relocation model, canonical "
        "zero padding, U.S. security hash, all MODE1 EDC/ECC, mutation "
        "boundaries, logical ISO hash, Track 2 hash, and CUE formatting.\n\n"
        "Manual emulator playtesting remains required. Configure Ares to use "
        "the supplied `Sega CD (U) - Model 2 v2.00w (1993).bin`, then open "
        f"`{basename}.cue`.\n"
    )
    (delivery_root / "TEST_NOTES.md").write_text(notes, encoding="utf-8")
    return report


def build_twice(
    baseline_track1: Path,
    baseline_track2: Path,
    us_bios: Path,
    runs_root: Path,
    delivery_root: Path,
    basename: str,
) -> dict[str, object]:
    """Build twice, compare binary artifacts, and publish one delivery set."""
    if sha256(baseline_track1) != EXPECTED_V7_TRACK1_SHA256:
        raise RegionVariantError("Track 1 is not the validated v7 baseline")
    if sha256(baseline_track2) != EXPECTED_TRACK2_SHA256:
        raise RegionVariantError("Track 2 is not the exact retail audio track")

    run_a = runs_root / "run_a" / "product"
    run_b = runs_root / "run_b" / "product"
    _build_once(
        baseline_track1, baseline_track2, us_bios, run_a, basename
    )
    _build_once(
        baseline_track1, baseline_track2, us_bios, run_b, basename
    )
    return publish_existing(runs_root, delivery_root, basename)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_track1", type=Path)
    parser.add_argument("baseline_track2", type=Path)
    parser.add_argument("us_bios", type=Path)
    parser.add_argument("--runs-root", type=Path, default=HERE / "runs")
    parser.add_argument(
        "--delivery-root",
        type=Path,
        default=WORKSPACE
        / "outputs"
        / "Nostalgia1907_CleanRebuild_v7_US_BIOS_Test",
    )
    parser.add_argument(
        "--basename", default="Nostalgia1907_CleanRebuild_v7_US_BIOS_Test"
    )
    parser.add_argument(
        "--publish-existing",
        action="store_true",
        help="publish two already validated run_a/run_b staging products",
    )
    args = parser.parse_args()
    if args.publish_existing:
        result = publish_existing(
            args.runs_root, args.delivery_root, args.basename
        )
    else:
        result = build_twice(
            args.baseline_track1,
            args.baseline_track2,
            args.us_bios,
            args.runs_root,
            args.delivery_root,
            args.basename,
        )
    print(
        json.dumps(
            {
                "status": result["status"],
                "two_clean_region_builds_byte_identical": result[
                    "two_clean_region_builds_byte_identical"
                ],
                "delivery_root": str(args.delivery_root),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

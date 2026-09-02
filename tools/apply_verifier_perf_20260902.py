#!/usr/bin/env python3
"""Apply trusted-reference verification performance edits on the perf branch."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected exactly one match for {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    begin = text.index(start)
    finish = text.index(end, begin)
    path.write_text(text[:begin] + replacement + text[finish:], encoding="utf-8")


raw = ROOT / "work" / "clean_rebuild" / "raw_cd.py"
replace_once(raw, "from pathlib import Path\n", "import hashlib\nfrom pathlib import Path\n")
replace_between(
    raw,
    "def verify_track(\n",
    "def write_two_track_cue(",
    '''def _sha256_file(path: Path) -> str:\n    """Return an uppercase SHA-256 digest for one streamed file."""\n    digest = hashlib.sha256()\n    with path.open("rb") as source:\n        while block := source.read(1024 * 1024):\n            digest.update(block)\n    return digest.hexdigest().upper()\n\n\ndef verify_track(\n    raw_path: Path,\n    *,\n    compare_boot_to: Path | None = None,\n    trusted_reference: Path | None = None,\n    trusted_reference_sha256: str | None = None,\n) -> dict[str, object]:\n    """Validate raw sectors, boot signature, and optional trusted-reference delta.\n\n    By default every sector receives a fresh EDC/ECC calculation.  A caller may\n    instead supply both ``trusted_reference`` and its independently established\n    SHA-256.  The reference bytes are authenticated before sector processing; an\n    output sector that is byte-identical to that authenticated reference inherits\n    the reference's checksum evidence, while every changed sector still receives\n    full EDC/ECC verification.\n\n    Args:\n        raw_path: MODE1/2352 Track 1 to inspect.\n        compare_boot_to: Optional template whose first 16 user-data sectors must\n            match exactly.\n        trusted_reference: Optional already-certified Track 1 used as the source\n            of checksum evidence for byte-identical sectors.\n        trusted_reference_sha256: Exact expected digest for ``trusted_reference``.\n            It must be supplied together with the reference.\n\n    Returns:\n        Sector count, boot evidence, verification mode, and the number of sectors\n        verified directly versus inherited by exact authenticated byte identity.\n\n    Raises:\n        RawCdError: If geometry, address, checksum, reference identity, signature,\n            or requested boot equality fails.\n    """\n    size = raw_path.stat().st_size\n    if size % RAW_SECTOR_SIZE:\n        raise RawCdError("track has a partial raw sector")\n    sector_count = size // RAW_SECTOR_SIZE\n\n    if (trusted_reference is None) != (trusted_reference_sha256 is None):\n        raise RawCdError(\n            "trusted reference and trusted reference SHA-256 must be supplied together"\n        )\n    expected_reference_hash = None\n    if trusted_reference is not None:\n        if trusted_reference.stat().st_size != size:\n            raise RawCdError("trusted reference Track 1 geometry differs")\n        expected_reference_hash = str(trusted_reference_sha256).upper()\n        if len(expected_reference_hash) != 64 or any(\n            character not in "0123456789ABCDEF"\n            for character in expected_reference_hash\n        ):\n            raise RawCdError("trusted reference SHA-256 is not 64-digit hexadecimal")\n        actual_reference_hash = _sha256_file(trusted_reference)\n        if actual_reference_hash != expected_reference_hash:\n            raise RawCdError(\n                "trusted reference SHA-256 mismatch: "\n                f"{actual_reference_hash} != {expected_reference_hash}"\n            )\n\n    boot_payload = bytearray()\n    directly_verified = 0\n    inherited = 0\n    reference_stream = (\n        trusted_reference.open("rb") if trusted_reference is not None else None\n    )\n    try:\n        with raw_path.open("rb") as source:\n            for sector_index in range(sector_count):\n                sector = source.read(RAW_SECTOR_SIZE)\n                validate_sector_header(sector, sector_index)\n                reference_sector = (\n                    reference_stream.read(RAW_SECTOR_SIZE)\n                    if reference_stream is not None\n                    else None\n                )\n                if reference_sector is not None and sector == reference_sector:\n                    inherited += 1\n                else:\n                    if not verify_sector_checksums(sector):\n                        raise RawCdError(f"sector {sector_index}: invalid EDC/ECC")\n                    directly_verified += 1\n                if sector_index < 16:\n                    boot_payload.extend(\n                        sector[\n                            USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE\n                        ]\n                    )\n        if reference_stream is not None and reference_stream.read(1):\n            raise RawCdError("trusted reference has trailing raw data")\n    finally:\n        if reference_stream is not None:\n            reference_stream.close()\n\n    if bytes(boot_payload[:16]) != BOOT_SIGNATURE:\n        raise RawCdError("Mega-CD boot signature is missing")\n\n    boot_matches = None\n    if compare_boot_to is not None:\n        reference = bytearray()\n        with compare_boot_to.open("rb") as source:\n            for sector_index in range(16):\n                sector = source.read(RAW_SECTOR_SIZE)\n                validate_sector_header(sector, sector_index)\n                reference.extend(\n                    sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE]\n                )\n        boot_matches = bytes(reference) == bytes(boot_payload)\n        if not boot_matches:\n            raise RawCdError("boot-system payload differs from retail Track 1")\n    return {\n        "sector_count": sector_count,\n        "size": size,\n        "boot_signature": BOOT_SIGNATURE.decode("ascii"),\n        "boot_matches_retail": boot_matches,\n        "all_sector_checksums_valid": True,\n        "checksum_verification_mode": (\n            "trusted-reference-delta"\n            if trusted_reference is not None\n            else "full-recalculation"\n        ),\n        "checksum_verified_sector_count": directly_verified,\n        "checksum_inherited_sector_count": inherited,\n        "trusted_reference_sha256": expected_reference_hash,\n    }\n\n\n''',
)

regression = ROOT / "work" / "clean_rebuild" / "regression.py"
replace_once(
    regression,
    "from .mes_format import read_mes\nfrom .source_json import load_json_array, load_json_object\nfrom .raw_cd import verify_track\n",
    "from .mes_format import read_mes\nfrom .prepare_retail import RETAIL_TRACK1_SHA256\nfrom .source_json import load_json_array, load_json_object\nfrom .raw_cd import verify_track\n",
)
replace_once(
    regression,
    "    track_report = verify_track(track1, compare_boot_to=retail_track1)\n",
    "    track_report = verify_track(\n        track1,\n        compare_boot_to=retail_track1,\n        trusted_reference=retail_track1,\n        trusted_reference_sha256=RETAIL_TRACK1_SHA256,\n    )\n",
)

region = ROOT / "work" / "region_variant" / "build_us_bios_test.py"
replace_once(
    region,
    '''def _validate_track_delta(\n    input_track: Path,\n    output_track: Path,\n    expected_boot: bytes,\n) -> dict[str, object]:\n''',
    '''def _validate_track_delta(\n    input_track: Path,\n    output_track: Path,\n    expected_boot: bytes,\n    expected_input_sha256: str,\n) -> dict[str, object]:\n''',
)
replace_once(
    region,
    '''    if input_track.stat().st_size != output_track.stat().st_size:\n        raise RegionVariantError("region variant changed Track 1 geometry")\n    changed_sectors: list[int] = []\n''',
    '''    if input_track.stat().st_size != output_track.stat().st_size:\n        raise RegionVariantError("region variant changed Track 1 geometry")\n    expected_input_sha256 = expected_input_sha256.upper()\n    if sha256(input_track) != expected_input_sha256:\n        raise RegionVariantError(\n            "region validation input does not match the authenticated baseline"\n        )\n    changed_sectors: list[int] = []\n''',
)
replace_once(
    region,
    '''            validate_sector_header(right, sector_index)\n            if not verify_sector_checksums(right):\n                raise RegionVariantError(\n                    f"region variant sector {sector_index} has invalid EDC/ECC"\n                )\n            raw_digest.update(right)\n            logical_digest.update(\n                right[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE]\n            )\n            if left != right:\n                changed_sectors.append(sector_index)\n''',
    '''            validate_sector_header(right, sector_index)\n            raw_digest.update(right)\n            logical_digest.update(\n                right[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE]\n            )\n            if left != right:\n                if not verify_sector_checksums(right):\n                    raise RegionVariantError(\n                        f"region variant sector {sector_index} has invalid EDC/ECC"\n                    )\n                changed_sectors.append(sector_index)\n''',
)
replace_once(
    region,
    '''        "all_sector_checksums_valid": True,\n        "sha256": raw_digest.hexdigest().upper(),\n''',
    '''        "all_sector_checksums_valid": True,\n        "checksum_verification_mode": "trusted-reference-delta",\n        "checksum_verified_sector_count": len(changed_sectors),\n        "checksum_inherited_sector_count": sector_index - len(changed_sectors),\n        "sha256": raw_digest.hexdigest().upper(),\n''',
)
replace_once(
    region,
    "    track1_report = _validate_track_delta(baseline_track1, output_track1, output_boot)\n",
    "    track1_report = _validate_track_delta(\n        baseline_track1, output_track1, output_boot, expected_track1_sha256\n    )\n",
)
replace_once(
    region,
    "        track1_report = _validate_track_delta(baseline_track1, track1, expected_boot)\n",
    "        track1_report = _validate_track_delta(\n            baseline_track1, track1, expected_boot, expected_track1_sha256\n        )\n",
)

region_test = ROOT / "tests" / "test_region_wrapper.py"
replace_once(
    region_test,
    '''            source.write_bytes(raw_track_from_boot(original_boot))\n            with patch.object(\n''',
    '''            source.write_bytes(raw_track_from_boot(original_boot))\n            source_hash = hashlib.sha256(source.read_bytes()).hexdigest().upper()\n            with patch.object(\n''',
)
replace_once(
    region_test,
    '''                report = region._validate_track_delta(source, output, wrapped_boot)\n                self.assertEqual(report["changed_raw_sectors"], [0, 1, 2, 3, 4])\n                self.assertTrue(report["all_sector_checksums_valid"])\n''',
    '''                report = region._validate_track_delta(\n                    source, output, wrapped_boot, source_hash\n                )\n                self.assertEqual(report["changed_raw_sectors"], [0, 1, 2, 3, 4])\n                self.assertTrue(report["all_sector_checksums_valid"])\n                self.assertEqual(report["checksum_verified_sector_count"], 5)\n                self.assertEqual(report["checksum_inherited_sector_count"], 11)\n''',
)
replace_once(
    region_test,
    '''                    region._validate_track_delta(source, output, wrapped_boot)\n''',
    '''                    region._validate_track_delta(\n                        source, output, wrapped_boot, source_hash\n                    )\n''',
)

perf_test = ROOT / "tests" / "test_performance_equivalence.py"
replace_once(perf_test, "import bisect\n", "import bisect\nimport hashlib\n")
replace_once(
    perf_test,
    '''        changed = list(payloads)\n''',
    '''        first_payload = bytearray(payloads[0])\n        first_payload[: len(raw_cd.BOOT_SIGNATURE)] = raw_cd.BOOT_SIGNATURE\n        payloads[0] = bytes(first_payload)\n        changed = list(payloads)\n''',
)
replace_once(
    perf_test,
    '''            self.assertEqual(\n                optimized.stat().st_size,\n                sector_count * raw_cd.RAW_SECTOR_SIZE,\n            )\n''',
    '''            self.assertEqual(\n                optimized.stat().st_size,\n                sector_count * raw_cd.RAW_SECTOR_SIZE,\n            )\n\n            full_report = raw_cd.verify_track(optimized)\n            reference_hash = hashlib.sha256(template.read_bytes()).hexdigest().upper()\n            delta_report = raw_cd.verify_track(\n                optimized,\n                trusted_reference=template,\n                trusted_reference_sha256=reference_hash,\n            )\n            self.assertEqual(full_report["checksum_verified_sector_count"], sector_count)\n            self.assertEqual(delta_report["checksum_verified_sector_count"], 4)\n            self.assertEqual(delta_report["checksum_inherited_sector_count"], 60)\n            self.assertEqual(\n                delta_report["checksum_verification_mode"],\n                "trusted-reference-delta",\n            )\n            with self.assertRaisesRegex(raw_cd.RawCdError, "SHA-256 mismatch"):\n                raw_cd.verify_track(\n                    optimized,\n                    trusted_reference=template,\n                    trusted_reference_sha256="0" * 64,\n                )\n\n            damaged = bytearray(optimized.read_bytes())\n            damage_offset = 7 * raw_cd.RAW_SECTOR_SIZE + raw_cd.USER_DATA_OFFSET + 20\n            damaged[damage_offset] ^= 0x01\n            optimized.write_bytes(damaged)\n            with self.assertRaisesRegex(raw_cd.RawCdError, "invalid EDC/ECC"):\n                raw_cd.verify_track(\n                    optimized,\n                    trusted_reference=template,\n                    trusted_reference_sha256=reference_hash,\n                )\n''',
)

performance = ROOT / "docs" / "PERFORMANCE.md"
replace_once(
    performance,
    '''The release regression still performs a complete final Track 1 EDC/ECC\nverification. The optimization removes redundant work during preparation and\nreconstruction; it does not remove the final output-integrity proof.\n''',
    '''Release regression now authenticates the complete retail reference by its\nfrozen SHA-256, proves unchanged output sectors by exact byte identity to that\nreference, and recalculates EDC/ECC only for sectors that differ. This retains\ncomplete output-integrity evidence while avoiding another redundant full-disc\nparity pass.\n\n### Trusted-reference regression verification\n\nA paired 4,096-sector verification benchmark measures the full legacy\nrecalculation against authenticated-reference delta verification:\n\n| Case | Baseline wall | Optimized wall | Speedup | Direct EDC/ECC checks |\n| --- | ---: | ---: | ---: | ---: |\n| No changed sectors | 2.436 s | 0.013 s | 181.1x | 0 / 4,096 |\n| 128 changed sectors (3.125%) | 2.499 s | 0.092 s | 27.2x | 128 / 4,096 |\n\nOn the complete 81,909-sector retail Track 1, authenticated-reference\nverification took 0.216 seconds when all sectors were identical and 0.242\nseconds when five sectors were changed and freshly checksummed. The latter\nmirrors the region-wrapper mutation count. These full-track optimized timings\ninclude streaming SHA-256 authentication of the reference.\n''',
)

print("trusted-reference verification edits applied")

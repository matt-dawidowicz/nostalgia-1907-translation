#!/usr/bin/env python3
"""Apply the runtime-verified PART1A poker-status SCN coordinate correction.

The English build moves the persistent Game Hall poker status panel one native
X unit to the right in ``MAIN.BIN``. Retail ``PART1A.SCN`` also contains two
selector-window commands for the Call/Fold choice that still use the panel's
old X coordinate. When either selector runs, its clear/redraw rectangle clips
the relocated panel's top border.

This module is intentionally a closed binary patch, not a general SCN editor.
It accepts only the exact retail ``PART1A.SCN`` hash, checks both reviewed
selector bytes, changes only those two offsets from ``0x17`` to ``0x18``, and
requires the exact reviewed output hash and mutation set. The resulting scene
was confirmed in Ares on 2026-09-02.
"""

from __future__ import annotations

import hashlib

RETAIL_PART1A_SCN_SHA256 = (
    "2F345D957366BB3CDA14FA5764EFBC294F7B2C06531C6ED8E50745354DB3F00E"
)
PATCHED_PART1A_SCN_SHA256 = (
    "9B290B664E921651CE7712CDFDEF60F96933FFED74FA3A3AC271A2E932FD65F0"
)
SELECTOR_X_OFFSETS = (0x065D, 0x0666)
RETAIL_SELECTOR_X = 0x17
PATCHED_SELECTOR_X = 0x18


def sha256(data: bytes) -> str:
    """Return an uppercase SHA-256 digest for one in-memory SCN payload."""
    return hashlib.sha256(data).hexdigest().upper()


def patch_part1a_scn(retail: bytes) -> bytes:
    """Align the two Call/Fold selector windows with the relocated status panel.

    Args:
        retail: Exact unmodified retail ``PART1A.SCN`` bytes.

    Returns:
        A same-length SCN payload with only offsets ``0x065D`` and ``0x0666``
        changed from X=23 (``0x17``) to X=24 (``0x18``).

    Raises:
        ValueError: If the input hash or either expected retail coordinate differs.
        AssertionError: If output hash, length, or changed-byte scope drifts.
    """
    digest = sha256(retail)
    if digest != RETAIL_PART1A_SCN_SHA256:
        raise ValueError(
            "PART1A.SCN retail hash mismatch: expected "
            f"{RETAIL_PART1A_SCN_SHA256}, got {digest}"
        )
    if any(
        retail[offset] != RETAIL_SELECTOR_X for offset in SELECTOR_X_OFFSETS
    ):
        values = tuple(retail[offset] for offset in SELECTOR_X_OFFSETS)
        raise ValueError(
            "PART1A.SCN Call/Fold selector coordinates are not the retail values: "
            f"{values!r}"
        )

    patched = bytearray(retail)
    for offset in SELECTOR_X_OFFSETS:
        patched[offset] = PATCHED_SELECTOR_X
    result = bytes(patched)

    if (
        len(result) != len(retail)
        or sha256(result) != PATCHED_PART1A_SCN_SHA256
    ):
        raise AssertionError(
            "PART1A.SCN patch output does not match its frozen result"
        )
    changed = {
        index
        for index, (before, after) in enumerate(
            zip(retail, result, strict=True)
        )
        if before != after
    }
    if changed != set(SELECTOR_X_OFFSETS):
        raise AssertionError(
            "PART1A.SCN patch touched unexpected byte offsets"
        )
    return result

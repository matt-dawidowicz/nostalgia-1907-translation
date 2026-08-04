#!/usr/bin/env python3
"""Apply the translation's single frozen MAIN.BIN UI-coordinate adjustment.

This is intentionally not a general patch framework. The function accepts only
the exact retail executable hash, verifies every original descriptor/coordinate,
changes the status panel and thirteen marker X positions by the reviewed amount,
then requires the complete output hash and exact changed-byte set.

New text or screenshot fixes do not belong here. They must be expressed as
canonical wording or a shared renderer/layout rule unless separate executable
analysis establishes a new, independently reviewed contract.
"""

from __future__ import annotations

import hashlib


RETAIL_SHA256 = "AEF74096DF5416A947D15A1DAF32995A4373F629DE9C5AC301EFE9CE67D4F05E"
PATCHED_SHA256 = "F425B9D080E5DE46373DF90D23E136F13D895198C3A2764644B1337FEABBF50A"
STATUS_PANEL_OFFSET = 0x2772
STATUS_PANEL_RETAIL = bytes((23, 19, 8, 8))
STATUS_PANEL_PATCHED = bytes((24, 19, 8, 8))
MARKER_X_OFFSETS = tuple(range(0x2D2A, 0x2D8B, 8))
MARKER_X_RETAIL = (
    0x0144,
    0x014C,
    0x014C,
    0x014C,
    0x0154,
    0x0154,
    0x015C,
    0x015C,
    0x0154,
    0x0154,
    0x0154,
    0x015C,
    0x0164,
)


def sha256(data: bytes) -> str:
    """Return an uppercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest().upper()


def patch_main(retail: bytes) -> bytes:
    """Move the status panel and all thirteen markers right by eight pixels.

    Args:
        retail: Exact unmodified retail ``MAIN.BIN`` bytes.

    Returns:
        A same-length executable matching the single frozen patched hash.

    Raises:
        ValueError: If the input hash or expected original coordinates differ.
        AssertionError: If implementation drift changes the output hash,
            length, or exact byte-offset mutation set.

    Notes:
        This is a closed, reviewed UI-coordinate recipe. It is not an extension
        point for translation or chapter-specific layout fixes.
    """
    digest = sha256(retail)
    if digest != RETAIL_SHA256:
        raise ValueError(
            f"MAIN.BIN retail hash mismatch: expected {RETAIL_SHA256}, got {digest}"
        )
    panel_end = STATUS_PANEL_OFFSET + len(STATUS_PANEL_RETAIL)
    if retail[STATUS_PANEL_OFFSET:panel_end] != STATUS_PANEL_RETAIL:
        raise ValueError("MAIN.BIN status-panel descriptor is not the retail value")
    marker_values = tuple(
        int.from_bytes(retail[offset : offset + 2], "big")
        for offset in MARKER_X_OFFSETS
    )
    if marker_values != MARKER_X_RETAIL:
        raise ValueError("MAIN.BIN status-marker coordinates are not the retail values")

    patched = bytearray(retail)
    patched[STATUS_PANEL_OFFSET:panel_end] = STATUS_PANEL_PATCHED
    for offset, value in zip(MARKER_X_OFFSETS, MARKER_X_RETAIL, strict=True):
        patched[offset : offset + 2] = (value + 8).to_bytes(2, "big")
    result = bytes(patched)
    if len(result) != len(retail) or sha256(result) != PATCHED_SHA256:
        raise AssertionError("MAIN.BIN patch output does not match its frozen result")

    changed = {
        index for index, pair in enumerate(zip(retail, result)) if pair[0] != pair[1]
    }
    expected = {STATUS_PANEL_OFFSET} | {offset + 1 for offset in MARKER_X_OFFSETS}
    if changed != expected:
        raise AssertionError("MAIN.BIN patch touched unexpected byte offsets")
    return result

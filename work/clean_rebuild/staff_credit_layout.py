#!/usr/bin/env python3
"""Validate STAFF credits against the native centered 18-cell canvas.

The STAFF renderer exposes 18 12-pixel cells. English cells contain two
six-pixel character slots, so one complete credit row owns exactly 36 source
characters. Canonical STAFF text is fixed-layout and therefore preserves its
leading and trailing spaces verbatim; those spaces are presentation data, not
semantic whitespace.

This module provides one deterministic centering rule for every translated
credit row. A line is valid only when its visible text is centered across the
36-character canvas using Python's normal odd-padding convention: when one
extra slot remains, it is placed on the right. This prevents short entries such
as ``Ruthie`` from silently reverting to left alignment while still fitting the
box width.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .source_json import load_json_object
from .translation_audit import SOURCES

STAFF_CANVAS_CELLS = 18
STAFF_CANVAS_CHARACTERS = STAFF_CANVAS_CELLS * 2
DEFAULT_STAFF_SOURCE = SOURCES / "STAFF.json"


def centered_credit_line(text: str) -> str:
    """Return one credit line centered on the complete STAFF canvas.

    Args:
        text: Visible credit wording, optionally already padded with ASCII
            spaces at either edge.

    Returns:
        The same visible wording centered in exactly 36 character slots.

    Raises:
        ValueError: If the input is multiline, contains no visible text, or is
            too wide for the native STAFF canvas.
    """
    if "\n" in text or "\r" in text:
        raise ValueError("STAFF credit lines must be single-line text")
    visible = text.strip(" ")
    if not visible:
        raise ValueError("STAFF credit lines must contain visible text")
    if len(visible) > STAFF_CANVAS_CHARACTERS:
        raise ValueError(
            f"STAFF credit is {len(visible)} characters; "
            f"canvas permits {STAFF_CANVAS_CHARACTERS}"
        )
    return visible.center(STAFF_CANVAS_CHARACTERS)


def _edge_spaces(text: str) -> tuple[int, int]:
    """Return literal left and right ASCII-space counts for one credit row."""
    leading = len(text) - len(text.lstrip(" "))
    trailing = len(text) - len(text.rstrip(" "))
    return leading, trailing


def audit_staff_credits(
    source: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Audit every translated STAFF record for exact width and centering.

    Args:
        source: Parsed STAFF source object. When omitted, the canonical tracked
            ``STAFF.json`` is loaded.

    Returns:
        A JSON-serializable report with all translated record IDs and failures.

    Raises:
        ValueError: If the supplied source has an incompatible shape.
        OSError: If the canonical source cannot be read when ``source`` is
            omitted.
    """
    document = (
        load_json_object(DEFAULT_STAFF_SOURCE) if source is None else source
    )
    chapter = document.get("chapter")
    records = document.get("records")
    if chapter != "STAFF" or not isinstance(records, list):
        raise ValueError(
            "STAFF credit audit requires a STAFF source record list"
        )

    failures: list[str] = []
    audited_ids: list[str] = []
    for record in records:
        if not isinstance(record, dict) or record.get("policy") != "translate":
            continue
        index = record.get("index")
        text = record.get("text")
        if not isinstance(index, int) or not isinstance(text, str):
            raise ValueError(
                "translated STAFF record requires integer index and text"
            )
        record_id = f"STAFF:{index:03d}"
        audited_ids.append(record_id)
        if len(text) != STAFF_CANVAS_CHARACTERS:
            failures.append(
                f"{record_id}: row is {len(text)} characters; "
                f"expected {STAFF_CANVAS_CHARACTERS}"
            )
            continue
        try:
            expected = centered_credit_line(text)
        except ValueError as error:
            failures.append(f"{record_id}: {error}")
            continue
        if text != expected:
            actual_left, actual_right = _edge_spaces(text)
            expected_left, expected_right = _edge_spaces(expected)
            failures.append(
                f"{record_id}: credit is not centered; padding "
                f"{actual_left}/{actual_right}, expected "
                f"{expected_left}/{expected_right}"
            )

    return {
        "status": "PASS" if not failures else "FAIL",
        "canvas_cells": STAFF_CANVAS_CELLS,
        "canvas_characters": STAFF_CANVAS_CHARACTERS,
        "audited_record_count": len(audited_ids),
        "audited_record_ids": audited_ids,
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> int:
    """Run the canonical STAFF centering audit and return a shell status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_STAFF_SOURCE)
    args = parser.parse_args()
    report = audit_staff_credits(load_json_object(args.source))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

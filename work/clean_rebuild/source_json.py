#!/usr/bin/env python3
"""Load tracked JSON without silently discarding duplicate object keys.

Canonical chapters, renderer policy, project manifests, and generated evidence
must never use normal ``json.loads`` last-key-wins behavior. This module is the
shared clean-rebuild loader. It reports the owning path, rejects duplicate keys
at every object depth, and can require an object or array top level.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DuplicateJsonKeyError(ValueError):
    """Raised when one JSON object repeats a key in source text."""


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Build one JSON object while rejecting every repeated source key."""
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def loads_json(text: str, *, source: str = "<json>") -> Any:
    """Parse JSON text with duplicate-key rejection and contextual errors.

    Args:
        text: UTF-8-decoded JSON source text.
        source: Human-readable path or label for diagnostics.

    Returns:
        The parsed JSON value.

    Raises:
        ValueError: If JSON syntax is invalid or an object repeats a key.

    Side Effects:
        None.
    """
    try:
        return json.loads(text, object_pairs_hook=_object_without_duplicate_keys)
    except (json.JSONDecodeError, DuplicateJsonKeyError) as error:
        raise ValueError(f"{source}: {error}") from error


def load_json(path: Path) -> Any:
    """Read and strictly parse one UTF-8 JSON file.

    Args:
        path: File to read without modifying it.

    Returns:
        The parsed JSON value.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If syntax or duplicate-key validation fails.

    Side Effects:
        Reads ``path`` only.
    """
    return loads_json(path.read_text(encoding="utf-8"), source=str(path))


def load_json_object(path: Path) -> dict[str, Any]:
    """Load one strict JSON file and require an object top level."""
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def load_json_array(path: Path) -> list[Any]:
    """Load one strict JSON file and require an array top level."""
    value = load_json(path)
    if not isinstance(value, list):
        raise ValueError(f"{path}: expected a JSON array")
    return value

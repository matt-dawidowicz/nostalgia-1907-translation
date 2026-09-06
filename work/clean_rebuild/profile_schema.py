#!/usr/bin/env python3
"""Validate canonical renderer-profile fields and active text rules.

Renderer profiles contain only live production settings consumed by current
validation or layout inference. Retired migration flags and unknown fields are
rejected instead of being retained as compatibility state. The module also
enforces profile-owned exact text, prefix, and forbidden-pattern rules against
canonical records without requiring retail data.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

ACTIVE_PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "name",
        "translation_status",
        "required_text_exact",
        "required_text_prefixes",
        "forbidden_text_patterns",
        "scn_dialogue_layout",
        "scn_continuation_layout",
        "scn_dialogue_runtime_layout",
        "scn_continuation_runtime_layout",
        "scn_window_text_subtypes",
        "layout_overrides",
        "runtime_layout_overrides",
        "row_limit_overrides",
        "text_box_overrides",
        "role_overrides",
    }
)
INDEXED_LAYOUT_FIELDS = frozenset(
    {"layout_overrides", "runtime_layout_overrides"}
)
TEXT_BOX_IDS = frozenset(
    {
        "lower_dialogue",
        "lower_continuation",
        "floating_window",
        "full_screen_narration",
        "lower_caption",
        "scene_label",
    }
)
PROFILE_ROLES = frozenset(
    {
        "main_dialogue",
        "dialogue_continuation",
        "speaker_name",
        "location_name",
        "perspective_name",
        "side_thought",
        "overlay_text",
        "narration",
        "menu_choice",
    }
)


def canonical_profile_index(
    raw_index: object, *, field: str, chapter: str
) -> int:
    """Return one canonical non-negative profile record index.

    JSON object keys are strings. Requiring their exact decimal form prevents
    aliases such as ``"01"`` and ``"1"`` from silently collapsing when the
    SCN consumers convert keys to integers.
    """
    if not isinstance(raw_index, str) or not re.fullmatch(
        r"0|[1-9][0-9]*", raw_index
    ):
        raise ValueError(
            f"{chapter}: profile {field} index {raw_index!r} is not canonical"
        )
    return int(raw_index)


def _translated_index(
    index: int,
    records: Sequence[object] | None,
    *,
    field: str,
    chapter: str,
) -> None:
    """Require an indexed production rule to address a translated record."""
    if records is None:
        return
    if index >= len(records):
        raise ValueError(
            f"{chapter}: profile {field} index {index} is out of range"
        )
    record = records[index]
    if not isinstance(record, dict) or record.get("policy") != "translate":
        raise ValueError(
            f"{chapter}: profile {field} index {index} does not target a translated record"
        )


def _indexed_string_rules(
    profile: dict[str, object],
    field: str,
    *,
    chapter: str,
    records: Sequence[object] | None = None,
) -> dict[int, str]:
    """Return one validated record-index-to-string rule mapping."""
    raw = profile.get(field, {})
    if not isinstance(raw, dict):
        raise ValueError(f"{chapter}: profile {field} is not an object")
    rules: dict[int, str] = {}
    for raw_index, expected in raw.items():
        index = canonical_profile_index(
            raw_index, field=field, chapter=chapter
        )
        _translated_index(index, records, field=field, chapter=chapter)
        if not isinstance(expected, str):
            raise ValueError(
                f"{chapter}: profile {field}[{raw_index!r}] is not a string"
            )
        rules[index] = expected
    return rules


def _indexed_rules(
    profile: dict[str, object],
    field: str,
    *,
    chapter: str,
    records: Sequence[object] | None,
) -> dict[int, object]:
    """Validate one active indexed field and return its canonical mapping."""
    raw = profile.get(field, {})
    if not isinstance(raw, dict):
        raise ValueError(f"{chapter}: profile {field} is not an object")
    rules: dict[int, object] = {}
    for raw_index, value in raw.items():
        index = canonical_profile_index(
            raw_index, field=field, chapter=chapter
        )
        if index in rules:
            raise ValueError(
                f"{chapter}: profile {field} has duplicate normalized index {index}"
            )
        _translated_index(index, records, field=field, chapter=chapter)
        rules[index] = value
    return rules


def _validate_indexed_renderer_rules(
    profile: dict[str, object],
    *,
    chapter: str,
    records: Sequence[object] | None,
) -> None:
    """Validate every renderer field keyed by a canonical record index."""
    for field in INDEXED_LAYOUT_FIELDS:
        for index, value in _indexed_rules(
            profile, field, chapter=chapter, records=records
        ).items():
            if not isinstance(value, dict) or set(value) - {
                "first",
                "continuation",
                "reason",
            }:
                raise ValueError(
                    f"{chapter}: profile {field}[{index}] has unsupported layout fields"
                )
            first = value.get("first")
            continuation = value.get("continuation")
            if (
                not isinstance(first, int)
                or not isinstance(continuation, int)
                or first <= 0
                or continuation <= 0
            ):
                raise ValueError(
                    f"{chapter}: profile {field}[{index}] must contain positive widths"
                )
            reason = value.get("reason")
            if reason is not None and (
                not isinstance(reason, str) or not reason
            ):
                raise ValueError(
                    f"{chapter}: profile {field}[{index}] reason is not a non-empty string"
                )

    for field, validator in (
        (
            "row_limit_overrides",
            lambda value: isinstance(value, int) and value > 0,
        ),
        ("text_box_overrides", lambda value: value in TEXT_BOX_IDS),
    ):
        for index, value in _indexed_rules(
            profile, field, chapter=chapter, records=records
        ).items():
            if not validator(value):
                raise ValueError(
                    f"{chapter}: profile {field}[{index}] is invalid"
                )

    for index, value in _indexed_rules(
        profile, "role_overrides", chapter=chapter, records=records
    ).items():
        roles = [value] if isinstance(value, str) else value
        if (
            not isinstance(roles, list)
            or not roles
            or not all(
                isinstance(role, str) and role in PROFILE_ROLES
                for role in roles
            )
        ):
            raise ValueError(
                f"{chapter}: profile role_overrides[{index}] is invalid"
            )


def validate_profile(
    profile: dict[str, object] | None,
    *,
    chapter: str,
    records: Sequence[object] | None = None,
) -> None:
    """Validate profile identity and reject retired or unknown fields.

    Args:
        profile: Embedded canonical profile, or ``None`` when absent.
        chapter: Canonical chapter identifier that the profile must describe.
        records: Optional canonical records used to validate indexed targets.

    Raises:
        ValueError: If the profile is not an object, contains an unknown field,
            uses an unsupported schema, names a different chapter, or contains
            a malformed active rule.
    """
    if profile is None:
        return
    if not isinstance(profile, dict):
        raise ValueError(f"{chapter}: embedded profile is not an object")
    unknown = set(profile) - ACTIVE_PROFILE_FIELDS
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(
            f"{chapter}: profile contains unknown fields: {joined}"
        )
    if profile.get("schema_version") not in {None, 1}:
        raise ValueError(f"{chapter}: unsupported profile schema version")
    profile_name = profile.get("name")
    if profile_name is not None and profile_name != chapter:
        raise ValueError(
            f"{chapter}: profile name {profile_name!r} does not match chapter"
        )
    translation_status = profile.get("translation_status")
    if translation_status is not None and not isinstance(
        translation_status, str
    ):
        raise ValueError(
            f"{chapter}: profile translation_status is not a string"
        )

    _indexed_string_rules(
        profile, "required_text_exact", chapter=chapter, records=records
    )
    _indexed_string_rules(
        profile, "required_text_prefixes", chapter=chapter, records=records
    )
    _validate_indexed_renderer_rules(profile, chapter=chapter, records=records)
    forbidden = profile.get("forbidden_text_patterns", [])
    if not isinstance(forbidden, list) or any(
        not isinstance(pattern, str) for pattern in forbidden
    ):
        raise ValueError(
            f"{chapter}: profile forbidden_text_patterns is not a string list"
        )
    for pattern in forbidden:
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(
                f"{chapter}: invalid forbidden text pattern {pattern!r}: {error}"
            ) from error


def profile_text_failures(
    profile: dict[str, object] | None,
    records: Sequence[object],
    *,
    chapter: str,
) -> list[str]:
    """Return canonical text violations owned by one validated profile.

    Exact and prefix rules address stable zero-based record indexes. Forbidden
    regular expressions are checked record by record so diagnostics identify
    the exact canonical ID instead of only the chapter.
    """
    validate_profile(profile, chapter=chapter, records=records)
    if profile is None:
        return []
    exact = _indexed_string_rules(
        profile, "required_text_exact", chapter=chapter, records=records
    )
    prefixes = _indexed_string_rules(
        profile, "required_text_prefixes", chapter=chapter, records=records
    )
    failures: list[str] = []
    for field, rules in (("exact text", exact), ("prefix", prefixes)):
        for index, expected in sorted(rules.items()):
            if index >= len(records):
                failures.append(
                    f"{chapter}:{index:03d}: profile {field} rule is out of range"
                )
                continue
            record = records[index]
            if not isinstance(record, dict):
                failures.append(
                    f"{chapter}:{index:03d}: canonical record is not an object"
                )
                continue
            text = record.get("text")
            if not isinstance(text, str):
                failures.append(
                    f"{chapter}:{index:03d}: profile {field} requires translated text"
                )
                continue
            valid = (
                text == expected
                if field == "exact text"
                else text.startswith(expected)
            )
            if not valid:
                relation = "equal" if field == "exact text" else "start with"
                failures.append(
                    f"{chapter}:{index:03d}: profile requires text to {relation} "
                    f"{expected!r}, got {text!r}"
                )

    patterns = [
        re.compile(pattern)
        for pattern in profile.get("forbidden_text_patterns", [])
        if isinstance(pattern, str)
    ]
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(
            record.get("text"), str
        ):
            continue
        text = record["text"]
        for pattern in patterns:
            if pattern.search(text):
                failures.append(
                    f"{chapter}:{index:03d}: text matches forbidden profile pattern "
                    f"{pattern.pattern!r}"
                )
    return failures

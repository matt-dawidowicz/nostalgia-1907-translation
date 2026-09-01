"""Source-only tests for canonical renderer-profile ownership."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
SOURCES = CLEAN / "sources"

from work.clean_rebuild.profile_schema import profile_text_failures, validate_profile  # noqa: E402
from work.clean_rebuild.source_json import load_json_object  # noqa: E402


class ProfileSchemaTests(unittest.TestCase):
    """Keep live profile settings distinct from accepted legacy metadata."""

    def test_all_canonical_profiles_and_text_rules_pass(self) -> None:
        """Validate every tracked profile without requiring retail fixtures."""
        index = load_json_object(SOURCES / "index.json")
        legacy_fields: set[str] = set()
        for item in index["chapters"]:
            source = load_json_object(SOURCES / item["source"])
            chapter = source["chapter"]
            with self.subTest(chapter=chapter):
                legacy_fields.update(
                    validate_profile(source.get("profile"), chapter=chapter)
                )
                self.assertEqual(
                    profile_text_failures(
                        source.get("profile"),
                        source["records"],
                        chapter=chapter,
                    ),
                    [],
                )
        self.assertIn("validate_wrapped_text_integrity", legacy_fields)
        self.assertIn("choice_render_cell_limit", legacy_fields)

    def test_unknown_profile_field_is_rejected(self) -> None:
        """Fail closed when an active-looking setting has no implementation."""
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_profile(
                {"schema_version": 1, "mystery_renderer_patch": True},
                chapter="TEST",
            )

    def test_exact_prefix_and_forbidden_rules_are_enforced(self) -> None:
        """Make profile text locks executable rather than documentary labels."""
        profile = {
            "schema_version": 1,
            "name": "TEST",
            "required_text_exact": {"0": "Exact"},
            "required_text_prefixes": {"1": "ACT 1:"},
            "forbidden_text_patterns": [r"(?i)direcktor"],
        }
        records = [
            {"index": 0, "policy": "translate", "text": "Wrong"},
            {"index": 1, "policy": "translate", "text": "Action 1: Opening"},
            {"index": 2, "policy": "translate", "text": "Direcktor"},
        ]
        failures = profile_text_failures(profile, records, chapter="TEST")
        self.assertEqual(len(failures), 3)
        self.assertTrue(any("equal 'Exact'" in failure for failure in failures))
        self.assertTrue(any("start with 'ACT 1:'" in failure for failure in failures))
        self.assertTrue(any("forbidden profile pattern" in failure for failure in failures))

    def test_profile_name_must_match_its_canonical_chapter(self) -> None:
        """Prevent copied profiles from silently governing another chapter."""
        with self.assertRaisesRegex(ValueError, "does not match chapter"):
            validate_profile(
                {"schema_version": 1, "name": "OTHER"},
                chapter="TEST",
            )

    def test_indexed_renderer_rules_require_canonical_translated_targets(self) -> None:
        """Reject aliases, stale indexes, and preserve-record renderer edits."""
        records = [
            {"index": 0, "policy": "translate", "text": "Visible"},
            {"index": 1, "policy": "preserve", "text": None},
        ]
        for profile, expression in (
            (
                {"layout_overrides": {"01": {"first": 8, "continuation": 8}}},
                "not canonical",
            ),
            (
                {"row_limit_overrides": {"2": 2}},
                "out of range",
            ),
            (
                {"text_box_overrides": {"1": "lower_dialogue"}},
                "does not target a translated record",
            ),
        ):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, expression):
                    validate_profile(profile, chapter="TEST", records=records)

    def test_indexed_renderer_rule_shapes_are_checked(self) -> None:
        """Reject malformed renderer overrides before SCN inference consumes them."""
        records = [{"index": 0, "policy": "translate", "text": "Visible"}]
        invalid_profiles = (
            {"layout_overrides": {"0": {"first": 8}}},
            {"runtime_layout_overrides": {"0": {"first": 0, "continuation": 8}}},
            {"row_limit_overrides": {"0": 0}},
            {"text_box_overrides": {"0": "unknown_box"}},
            {"role_overrides": {"0": ["made_up_role"]}},
        )
        for profile in invalid_profiles:
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(
                    ValueError, "unsupported layout fields|is invalid|positive widths"
                ):
                    validate_profile(profile, chapter="TEST", records=records)


if __name__ == "__main__":
    unittest.main()

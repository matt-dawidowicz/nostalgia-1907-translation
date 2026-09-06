"""Source-only tests for strict JSON loading in production paths."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"

from work.clean_rebuild.source_json import (  # noqa: E402
    load_json_array,
    load_json_object,
    loads_json,
)


class StrictJsonTests(unittest.TestCase):
    """Reject duplicate keys before they can alter canonical policy silently."""

    def test_duplicate_key_is_rejected_at_nested_depth(self) -> None:
        """Reject last-key-wins behavior in nested profile objects."""
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            loads_json('{"profile": {"name": "A", "name": "B"}}')

    def test_object_loader_rejects_non_object_top_level(self) -> None:
        """Keep object-shaped manifests from accepting arrays accidentally."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "array.json"
            path.write_text("[]\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(ValueError, "expected a JSON object"):
                load_json_object(path)

    def test_array_loader_accepts_object_entries(self) -> None:
        """Allow list-shaped generated reports while retaining strict keys."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "patches.json"
            path.write_text(
                '[{"target": "MAIN.BIN", "extent": 64}]\n',
                encoding="utf-8",
                newline="\n",
            )
            self.assertEqual(
                load_json_array(path),
                [{"target": "MAIN.BIN", "extent": 64}],
            )

    def test_array_loader_rejects_duplicate_entry_keys(self) -> None:
        """Keep strict duplicate-key rejection inside report arrays."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "patches.json"
            path.write_text(
                '[{"target": "A", "target": "B"}]\n',
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(
                ValueError, "duplicate JSON object key"
            ):
                load_json_array(path)


if __name__ == "__main__":
    unittest.main()

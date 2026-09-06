"""Regression tests for the closed PART1A poker-status SCN correction."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from work.clean_rebuild import scn_patch


class Part1aScnPatchTests(unittest.TestCase):
    """Keep the Ares-confirmed selector alignment change exactly two bytes wide."""

    @staticmethod
    def _fixture(*, selector_x: int = scn_patch.RETAIL_SELECTOR_X) -> bytes:
        data = bytearray(0x700)
        for offset in scn_patch.SELECTOR_X_OFFSETS:
            data[offset] = selector_x
        return bytes(data)

    def test_exact_two_selector_coordinates_move_from_x23_to_x24(self) -> None:
        """Change only the two reviewed selector X bytes."""
        retail = self._fixture()
        expected = bytearray(retail)
        for offset in scn_patch.SELECTOR_X_OFFSETS:
            expected[offset] = scn_patch.PATCHED_SELECTOR_X
        expected_bytes = bytes(expected)
        with (
            patch.object(
                scn_patch, "RETAIL_PART1A_SCN_SHA256", scn_patch.sha256(retail)
            ),
            patch.object(
                scn_patch,
                "PATCHED_PART1A_SCN_SHA256",
                scn_patch.sha256(expected_bytes),
            ),
        ):
            result = scn_patch.patch_part1a_scn(retail)
        self.assertEqual(result, expected_bytes)
        self.assertEqual(len(result), len(retail))
        self.assertEqual(
            {
                i
                for i, pair in enumerate(zip(retail, result, strict=True))
                if pair[0] != pair[1]
            },
            set(scn_patch.SELECTOR_X_OFFSETS),
        )

    def test_wrong_retail_hash_is_rejected(self) -> None:
        """Reject every SCN payload outside the frozen retail identity."""
        with self.assertRaisesRegex(ValueError, "retail hash mismatch"):
            scn_patch.patch_part1a_scn(b"not retail PART1A.SCN")

    def test_wrong_coordinate_is_rejected_even_when_hash_is_authenticated(
        self,
    ) -> None:
        """Require the expected old X values independently of the file hash."""
        retail = self._fixture(selector_x=0x16)
        with patch.object(
            scn_patch, "RETAIL_PART1A_SCN_SHA256", scn_patch.sha256(retail)
        ):
            with self.assertRaisesRegex(ValueError, "selector coordinates"):
                scn_patch.patch_part1a_scn(retail)


if __name__ == "__main__":
    unittest.main()

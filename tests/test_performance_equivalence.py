#!/usr/bin/env python3
"""Prove performance shortcuts preserve the legacy binary results."""

from __future__ import annotations

import bisect
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from work.clean_rebuild import lz_format
from work.clean_rebuild import mes_compiler
from work.clean_rebuild import raw_cd


class LzOptimizerEquivalenceTests(unittest.TestCase):
    """Compare the optimized DP against the exact previous search order."""

    @staticmethod
    def _legacy_copy_candidates(
        data: bytes,
        positions: list[list[int]],
        position: int,
    ) -> list[lz_format.Op]:
        max_distance = min(0xFFF, len(data) - position)
        if position <= 0 or max_distance <= 0:
            return []
        matching = positions[data[position - 1]]
        first = bisect.bisect_left(matching, position)
        last = bisect.bisect_right(matching, position - 1 + max_distance)
        operations: list[lz_format.Op] = []
        for source in matching[first:last]:
            distance = source - (position - 1)
            length = lz_format._match_length(
                data,
                position,
                distance,
                min(256, position),
            )
            if length >= 2 and distance <= 0xFF:
                operations.append(("copy2", 2, distance))
            if length >= 3 and distance <= 0x1FF:
                operations.append(("copy3", 3, distance))
            if length >= 4 and distance <= 0x3FF:
                operations.append(("copy4", 4, distance))
            operations.extend(
                ("copylong", candidate_length, distance)
                for candidate_length in range(5, length + 1)
            )
        return operations

    @classmethod
    def _legacy_choose_operations(cls, data: bytes) -> list[tuple[int, lz_format.Op]]:
        positions: list[list[int]] = [[] for _ in range(256)]
        for index, byte in enumerate(data):
            positions[byte].append(index)
        infinity = 10**18
        costs = [infinity] * (len(data) + 1)
        choices: list[lz_format.Op | None] = [None] * (len(data) + 1)
        costs[0] = 0
        for position in range(1, len(data) + 1):
            for length in range(1, min(264, position) + 1):
                operation: lz_format.Op = ("literal", length, 0)
                cost = costs[position - length] + lz_format._op_cost(operation)
                if cost < costs[position]:
                    costs[position] = cost
                    choices[position] = operation
            for operation in cls._legacy_copy_candidates(data, positions, position):
                cost = costs[position - operation[1]] + lz_format._op_cost(operation)
                if cost < costs[position]:
                    costs[position] = cost
                    choices[position] = operation

        selected: list[tuple[int, lz_format.Op]] = []
        position = len(data)
        while position:
            operation = choices[position]
            if operation is None:
                raise AssertionError(f"legacy compressor could not cover byte {position}")
            selected.append((position, operation))
            position -= operation[1]
        return selected

    def test_optimized_compressor_matches_legacy_bytes(self) -> None:
        rng = random.Random(1907)
        corpora = (
            b"A" * 600,
            (b"ABRACADABRA-1907-" * 40)[:700],
            bytes(range(256)) * 3,
            bytes(rng.randrange(256) for _ in range(768)),
            (b"The ship is still moving. What happened in the engine room? " * 16)[
                :900
            ],
        )
        for data in corpora:
            with self.subTest(length=len(data), prefix=data[:12]):
                with patch.object(
                    lz_format,
                    "_choose_operations",
                    self._legacy_choose_operations,
                ):
                    legacy = lz_format.compress(data)
                optimized = lz_format.compress(data)
                self.assertEqual(optimized, legacy)
                self.assertEqual(lz_format.decompress(optimized, len(data)), data)


class RawCdFastPathEquivalenceTests(unittest.TestCase):
    """Prove trusted unchanged-sector copying matches full regeneration."""

    @staticmethod
    def _sector(index: int, payload: bytes) -> bytes:
        sector = bytearray(raw_cd.RAW_SECTOR_SIZE)
        sector[:12] = raw_cd.SYNC
        sector[12:15] = raw_cd.sector_msf(index)
        sector[raw_cd.MODE_OFFSET] = 1
        sector[
            raw_cd.USER_DATA_OFFSET : raw_cd.USER_DATA_OFFSET + raw_cd.ISO_SECTOR_SIZE
        ] = payload
        raw_cd.regenerate_checksums(sector)
        return bytes(sector)

    def test_trusted_fast_path_matches_full_regeneration(self) -> None:
        sector_count = 64
        payloads = [
            bytes(((index + offset * 17) & 0xFF) for offset in range(raw_cd.ISO_SECTOR_SIZE))
            for index in range(sector_count)
        ]
        changed = list(payloads)
        for index in (0, 7, 31, 63):
            payload = bytearray(changed[index])
            payload[100 + index] ^= 0x5A
            changed[index] = bytes(payload)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template.bin"
            logical = root / "translated.iso"
            baseline = root / "baseline.bin"
            optimized = root / "optimized.bin"
            template.write_bytes(
                b"".join(self._sector(index, payload) for index, payload in enumerate(payloads))
            )
            logical.write_bytes(b"".join(changed))

            raw_cd.iso_to_raw_fixed(template, logical, baseline)
            raw_cd.iso_to_raw_fixed(
                template,
                logical,
                optimized,
                trust_template_checksums=True,
            )
            self.assertEqual(optimized.read_bytes(), baseline.read_bytes())
            self.assertEqual(
                optimized.stat().st_size,
                sector_count * raw_cd.RAW_SECTOR_SIZE,
            )


class CompilerFastPathTests(unittest.TestCase):
    """Check the cache and dormant-phase shortcuts directly."""

    def test_stored_cell_cache_reuses_identical_render(self) -> None:
        mes_compiler.stored_cell.cache_clear()
        first = mes_compiler.stored_cell("literal", "th")
        second = mes_compiler.stored_cell("literal", "th")
        self.assertEqual(first, second)
        info = mes_compiler.stored_cell.cache_info()
        self.assertEqual(info.misses, 1)
        self.assertEqual(info.hits, 1)

    def test_phase_optimizer_returns_immediately_without_alternates(self) -> None:
        row = mes_compiler.RowPlan(
            record=0,
            prefix=(),
            primary=(("literal", "th"),),
            alternate=None,
        )
        with patch.object(
            mes_compiler,
            "stored_cell",
            side_effect=AssertionError("renderer should not run"),
        ):
            mes_compiler._optimize_phases([row], [], {})
        self.assertFalse(row.selected_alternate)


if __name__ == "__main__":
    unittest.main()

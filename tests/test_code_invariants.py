"""Focused regressions for parser, transaction, ISO, and release safeguards."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from work.clean_rebuild import iso9660
from work.clean_rebuild import mes_compiler
from work.clean_rebuild import mes_format
from work.clean_rebuild import renderer_format
from work.clean_rebuild import rebuild as clean_rebuild
from work.clean_rebuild import scn_layout
from work.clean_rebuild import translation_formatter

import test_script_layout_integration as layout_tests


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"


def mes_bytes(pointers: tuple[int, ...], script: bytes) -> bytes:
    """Build one synthetic MES header and record region without glyphs."""
    first_pointer = 2 + len(pointers) * 2
    if not pointers or pointers[0] != first_pointer:
        raise ValueError("synthetic pointers must begin at the table boundary")
    split_offset = first_pointer + len(script)
    return (
        split_offset.to_bytes(2, "big")
        + b"".join(pointer.to_bytes(2, "big") for pointer in pointers)
        + script
    )


def directory_record(
    name: bytes,
    extent: int,
    size: int,
    *,
    flags: int = 0,
    padding: bytes | None = None,
    system_use: bytes = b"",
) -> bytes:
    """Build one structurally valid ISO directory record for tests."""
    record = bytearray(33)
    record[1] = 0
    record[2:6] = extent.to_bytes(4, "little")
    record[6:10] = extent.to_bytes(4, "big")
    record[10:14] = size.to_bytes(4, "little")
    record[14:18] = size.to_bytes(4, "big")
    record[25] = flags
    record[28:30] = (1).to_bytes(2, "little")
    record[30:32] = (1).to_bytes(2, "big")
    record[32] = len(name)
    record.extend(name)
    if len(name) % 2 == 0:
        record.extend(b"\0" if padding is None else padding)
    record.extend(system_use)
    record[0] = len(record)
    return bytes(record)


def write_test_iso(
    path: Path,
    *,
    file_extent: int,
    file_size: int,
    total_sectors: int = 22,
    duplicate_extent: int | None = None,
) -> None:
    """Write a minimal primary-volume/root-directory ISO test fixture."""
    image = bytearray(total_sectors * iso9660.SECTOR_SIZE)
    pvd_offset = 16 * iso9660.SECTOR_SIZE
    pvd = bytearray(iso9660.SECTOR_SIZE)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    root = directory_record(b"\0", 20, iso9660.SECTOR_SIZE, flags=0x02)
    pvd[156 : 156 + len(root)] = root
    image[pvd_offset : pvd_offset + len(pvd)] = pvd

    records = [
        directory_record(b"\0", 20, iso9660.SECTOR_SIZE, flags=0x02),
        directory_record(b"\1", 20, iso9660.SECTOR_SIZE, flags=0x02),
        directory_record(b"FILE.BIN;1", file_extent, file_size),
    ]
    if duplicate_extent is not None:
        records.append(directory_record(b"FILE.BIN;1", duplicate_extent, file_size))
    directory = b"".join(records)
    start = 20 * iso9660.SECTOR_SIZE
    image[start : start + len(directory)] = directory
    path.write_bytes(image)


def canonical_source(text: str, *, layout_policy: str = "fixed") -> dict[str, object]:
    """Return a one-record canonical chapter object for transaction tests."""
    return {
        "record_count": 1,
        "records": [
            {
                "index": 0,
                "policy": "translate",
                "text": text,
                "layout_policy": layout_policy,
            }
        ],
    }


def write_dependency_fixture(
    root: Path,
    modules: dict[str, str],
    *,
    chapters: list[dict[str, object]] | None = None,
) -> None:
    """Create a minimal production-dependency audit fixture tree."""
    root.mkdir(parents=True, exist_ok=True)
    for name, text in modules.items():
        (root / name).write_text(text, encoding="utf-8")
    (root / "font_patterns.json").write_text("{}\n", encoding="utf-8")
    sources = root / "sources"
    sources.mkdir()
    (sources / "index.json").write_text(
        json.dumps({"chapter_count": len(chapters or []), "chapters": chapters or []})
        + "\n",
        encoding="utf-8",
    )


class MesFormatTests(unittest.TestCase):
    """Reject ambiguous MES record boundaries and missing terminators."""

    def test_minimum_terminated_record_is_valid(self) -> None:
        """Accept a one-byte terminator-only record as the structural minimum."""
        parsed = mes_format.parse_mes(mes_bytes((4,), b"\0"))
        self.assertEqual(parsed.records, (b"\0",))

    def test_duplicate_and_zero_length_records_are_rejected(self) -> None:
        """Reject first, middle, last, and all-equal zero-length boundaries."""
        malformed = {
            "empty first": mes_bytes((6, 6), b"A\0"),
            "empty middle": mes_bytes((8, 10, 10), b"A\0B\0"),
            "empty last": mes_bytes((6, 8), b"A\0"),
            "all equal": mes_bytes((8, 8, 8), b"A\0"),
        }
        for label, data in malformed.items():
            with self.subTest(label=label):
                with self.assertRaises(mes_format.MesFormatError):
                    mes_format.parse_mes(data, source=label)

    def test_missing_record_terminator_is_rejected(self) -> None:
        """Reject a bounded record whose final byte is not the 00 terminator."""
        with self.assertRaisesRegex(
            mes_format.MesFormatError, "lacks its 00 terminator"
        ):
            mes_format.parse_mes(mes_bytes((4,), b"AB"))

    def test_multiple_terminated_records_remain_valid(self) -> None:
        """Accept strictly increasing records that each end in a terminator."""
        parsed = mes_format.parse_mes(mes_bytes((6, 8), b"A\0B\0"))
        self.assertEqual(parsed.records, (b"A\0", b"B\0"))


class RowPackingTests(unittest.TestCase):
    """Keep storage optimization from changing visible text placement."""

    def test_row_packing_keeps_the_first_source_character_left_aligned(self) -> None:
        """Reject the former phase shift and its obsolete alternate-row state."""
        for text in (
            "It was not here, in this",
            "games and play one",
            "Do not insult me!",
        ):
            with self.subTest(text=text):
                row = mes_compiler._row_plan(0, text)
                self.assertFalse(hasattr(row, "alternate"))
                self.assertFalse(hasattr(row, "selected_alternate"))
                self.assertEqual(row.cells()[0], ("literal", text[:2]))

    def test_prose_rows_without_an_anchor_never_reserve_a_leading_blank_cell(
        self,
    ) -> None:
        """Keep non-dialogue adaptive rows aligned to their renderer's first cell."""
        layout = mes_compiler.Layout(4, 4, 4, 4)
        rows = mes_compiler._prose_rows("left aligned", layout)
        self.assertEqual(rows[0][0], ())
        self.assertTrue(rows[0][1].startswith("left"))

    def test_opening_anchor_is_emitted_once_for_the_full_dialogue_stream(self) -> None:
        """Keep one gutter while every later row uses the continuation stride."""
        layout = mes_compiler.Layout(
            3,
            2,
            3,
            2,
            page_rows=3,
            opening_anchor_cells=1,
        )
        rows = mes_compiler._prose_rows("one two four five six ten nine", layout)
        self.assertEqual(
            [len(prefix) for prefix, _line in rows[:7]],
            [1, 0, 0, 0, 0, 0, 0],
        )
        self.assertEqual(
            [layout.visible_cells(index) for index in range(7)],
            [2, 2, 2, 2, 2, 2, 2],
        )
        self.assertEqual(
            [layout.physical_cells(index) for index in range(7)],
            [3, 2, 2, 2, 2, 2, 2],
        )
        self.assertEqual(rows[0][0], (mes_compiler.BLANK_CELL,))
        self.assertEqual(
            [
                len(prefix) + renderer_format.measure_literal(line)
                for prefix, line in rows[:7]
            ],
            [3, 2, 2, 2, 2, 2, 2],
        )

    def test_layout_rejects_invalid_cell_geometry_and_row_indexes(self) -> None:
        """Fail closed instead of silently compiling an impossible layout."""
        with self.assertRaisesRegex(scn_layout.ScnLayoutError, "must be positive"):
            mes_compiler.Layout(0, 2, 2, 2)
        with self.assertRaisesRegex(scn_layout.ScnLayoutError, "narrower"):
            mes_compiler.Layout(3, 2, 2, 2)
        layout = mes_compiler.Layout(3, 2, 3, 2)
        with self.assertRaisesRegex(scn_layout.ScnLayoutError, "must not be negative"):
            layout.physical_cells(-1)
        with self.assertRaisesRegex(scn_layout.ScnLayoutError, "page_rows"):
            mes_compiler.Layout(3, 2, 3, 2, page_rows=0)
        with self.assertRaisesRegex(scn_layout.ScnLayoutError, "leaves no"):
            mes_compiler.Layout(1, 2, 1, 2, opening_anchor_cells=1)

    def test_retail_opening_anchor_applies_only_to_main_dialogue(self) -> None:
        """Never assign the quote gutter to a continuation stream fragment."""
        retail_records = (b"\x01\x00", b"\x10\x00")
        main = scn_layout.infer_layouts(
            b"\x21\x00\x01\x00\x02",
            2,
            {1},
            None,
            retail_records=retail_records,
        )
        self.assertEqual(main[1].opening_anchor_cells, 1)
        self.assertEqual(
            (main[1].visible_first, main[1].runtime_first),
            (12, 12),
        )
        self.assertEqual(main[1].page_rows, 3)
        self.assertEqual(main[1].visible_cells(0), 11)
        self.assertFalse(main[1].repeat_first_row_on_page)
        self.assertEqual(main[1].visible_cells(3), 11)
        continuation = scn_layout.infer_layouts(
            b"\x21\x00\x02\x00\x00",
            2,
            {1},
            None,
            retail_records=retail_records,
        )
        self.assertEqual(continuation[1].opening_anchor_cells, 0)


class IsoFormatTests(unittest.TestCase):
    """Enforce complete identifiers and in-image ISO extents."""

    def test_truncated_identifier_is_rejected(self) -> None:
        """Reject a name length that extends beyond the directory record."""
        record = bytearray(directory_record(b"A", 1, 1))
        record[32] = 10
        with self.assertRaisesRegex(iso9660.IsoError, "truncates its file identifier"):
            iso9660._parse_record(bytes(record), 0)

    def test_identifier_padding_rules_are_enforced(self) -> None:
        """Accept legal odd/even names and reject missing or nonzero padding."""
        odd = directory_record(b"A", 1, 1)
        even = directory_record(b"AB", 1, 1)
        self.assertEqual(iso9660._parse_record(odd, 0)[0], "A")
        self.assertEqual(iso9660._parse_record(even, 0)[0], "AB")
        self.assertEqual(
            iso9660._parse_record(directory_record(b"\0", 1, 1), 0)[0], "."
        )

        missing_padding = bytearray(even[:-1])
        missing_padding[0] = len(missing_padding)
        with self.assertRaisesRegex(iso9660.IsoError, "identifier or padding"):
            iso9660._parse_record(bytes(missing_padding), 0)
        with self.assertRaisesRegex(iso9660.IsoError, "nonzero"):
            iso9660._parse_record(
                directory_record(b"AB", 1, 1, padding=b"X"),
                0,
            )

    def test_file_extent_outside_iso_is_rejected_before_use(self) -> None:
        """Reject an ordinary file whose declared bytes leave the image."""
        with tempfile.TemporaryDirectory() as temporary:
            iso_path = Path(temporary) / "bad.iso"
            write_test_iso(iso_path, file_extent=22, file_size=1)
            with self.assertRaisesRegex(
                iso9660.IsoError, "file FILE.BIN logical extent"
            ):
                iso9660.read_entries(iso_path)

    def test_last_sector_exact_fit_is_valid(self) -> None:
        """Accept a file allocation ending exactly at the ISO boundary."""
        with tempfile.TemporaryDirectory() as temporary:
            iso_path = Path(temporary) / "exact.iso"
            write_test_iso(
                iso_path,
                file_extent=21,
                file_size=iso9660.SECTOR_SIZE,
            )
            entry = iso9660.unique_file(iso9660.read_entries(iso_path), "FILE.BIN")
            self.assertEqual(entry.allocated_size, iso9660.SECTOR_SIZE)

    def test_conflicting_duplicate_file_records_are_rejected(self) -> None:
        """Reject duplicate normalized paths that claim different layouts."""
        with tempfile.TemporaryDirectory() as temporary:
            iso_path = Path(temporary) / "duplicate.iso"
            write_test_iso(
                iso_path,
                file_extent=21,
                file_size=1,
                duplicate_extent=20,
            )
            entries = iso9660.read_entries(iso_path)
            with self.assertRaisesRegex(iso9660.IsoError, "conflicting duplicate"):
                iso9660.unique_file(entries, "FILE.BIN")


class TranslationFormatterTests(unittest.TestCase):
    """Protect duplicate-key handling and transactional canonical writes."""

    def test_duplicate_json_keys_are_rejected_at_every_object_level(self) -> None:
        """Reject duplicate IDs, wrapper keys, and unrelated metadata keys."""
        payloads = (
            '{"PART1A:003":"first","PART1A:003":"second"}',
            '{"changes":{"PART1A:003":"first","PART1A:003":"second"}}',
            '{"metadata":1,"metadata":2,"changes":{"PART1A:003":"only"}}',
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changes.json"
            for payload in payloads:
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaisesRegex(
                        ValueError, "duplicate JSON object key"
                    ):
                        translation_formatter._changes(path)

    def test_unique_object_and_list_change_forms_remain_supported(self) -> None:
        """Keep both documented unique change-set representations working."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changes.json"
            path.write_text(
                json.dumps({"changes": {"PART1A:003": "one"}}),
                encoding="utf-8",
            )
            self.assertEqual(
                translation_formatter._changes(path),
                {"PART1A:003": "one"},
            )

    def test_duplicate_list_change_ids_are_rejected(self) -> None:
        """Keep explicit duplicate detection for the entry-list representation."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changes.json"
            path.write_text(
                json.dumps(
                    {
                        "changes": [
                            {"id": "PART1A:003", "text": "first"},
                            {"id": "PART1A:003", "text": "second"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "repeats stable ID"):
                translation_formatter._changes(path)
            path.write_text(
                json.dumps({"changes": [{"id": "PART1A:003", "text": "one"}]}),
                encoding="utf-8",
            )
            self.assertEqual(
                translation_formatter._changes(path),
                {"PART1A:003": "one"},
            )

    def test_apply_rejects_malformed_profile_before_retail_lookup(self) -> None:
        """Fail before source mutation when an embedded profile is invalid."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "TEST.json"
            source = {
                "chapter": "TEST",
                "record_count": 1,
                "records": [
                    {
                        "index": 0,
                        "policy": "translate",
                        "text": "Before",
                        "layout_policy": "fixed",
                    }
                ],
                "profile": {
                    "schema_version": 1,
                    "mystery_renderer_patch": True,
                },
            }
            source_path.write_text(
                json.dumps(source) + "\n", encoding="utf-8", newline="\n"
            )
            before = source_path.read_bytes()
            changes = root / "changes.json"
            changes.write_text(
                json.dumps({"TEST:000": "After"}) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            chapters = {"TEST": (source_path, source)}
            with patch.object(
                translation_formatter,
                "_chapter_sources",
                return_value=({}, chapters),
            ):
                with self.assertRaisesRegex(ValueError, "unknown fields"):
                    translation_formatter.apply_changes(changes, root)
            self.assertEqual(source_path.read_bytes(), before)

    def test_row_limit_inference_rejects_noncanonical_indexes(self) -> None:
        """Keep direct SCN inference from accepting aliases such as ``01``."""
        with self.assertRaisesRegex(
            scn_layout.ScnLayoutError, "invalid row-limit record"
        ):
            scn_layout.infer_row_limits(
                b"",
                2,
                {1},
                {"row_limit_overrides": {"01": 2}},
            )

    def test_serialization_failure_leaves_every_target_untouched(self) -> None:
        """Pre-serialize the complete transaction before creating replacements."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            first.write_bytes(b"before A")
            second.write_bytes(b"before B")
            with self.assertRaises(TypeError):
                translation_formatter._transactional_write_json_sources(
                    {
                        first: {"value": "after A"},
                        second: {"value": object()},
                    }
                )
            self.assertEqual(first.read_bytes(), b"before A")
            self.assertEqual(second.read_bytes(), b"before B")
            self.assertEqual(list(root.glob(".*.new")), [])

    def test_staging_failure_leaves_every_target_untouched(self) -> None:
        """Remove staged temps and preserve sources when a later temp write fails."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            first.write_bytes(b"before A")
            second.write_bytes(b"before B")
            real_write = translation_formatter._write_transaction_temp
            staged_new = 0

            def failing_write(
                target: Path,
                payload: bytes,
                mode: int,
                kind: str,
            ) -> Path:
                """Fail the second new-data staging write."""
                nonlocal staged_new
                if kind == "new":
                    staged_new += 1
                    if staged_new == 2:
                        raise OSError("simulated staging failure")
                return real_write(target, payload, mode, kind)

            with patch.object(
                translation_formatter,
                "_write_transaction_temp",
                side_effect=failing_write,
            ):
                with self.assertRaisesRegex(OSError, "simulated staging failure"):
                    translation_formatter._transactional_write_json_sources(
                        {
                            first: {"value": "after A"},
                            second: {"value": "after B"},
                        }
                    )
            self.assertEqual(first.read_bytes(), b"before A")
            self.assertEqual(second.read_bytes(), b"before B")
            self.assertEqual(list(root.glob(".*.new")), [])
            self.assertEqual(list(root.glob(".*.backup")), [])

    def test_second_replacement_failure_rolls_back_first(self) -> None:
        """Restore an earlier chapter when a later atomic replace fails."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            first.write_bytes(b"before A")
            second.write_bytes(b"before B")
            real_replace = os.replace
            new_replacements = 0

            def failing_replace(
                source: str | bytes | Path, target: str | bytes | Path
            ) -> None:
                """Fail only the second staged-new replacement."""
                nonlocal new_replacements
                if str(source).endswith(".new"):
                    new_replacements += 1
                    if new_replacements == 2:
                        raise OSError("simulated second replacement failure")
                real_replace(source, target)

            with patch.object(
                translation_formatter.os,
                "replace",
                side_effect=failing_replace,
            ):
                with self.assertRaisesRegex(OSError, "second replacement failure"):
                    translation_formatter._transactional_write_json_sources(
                        {
                            first: {"value": "after A"},
                            second: {"value": "after B"},
                        }
                    )
            self.assertEqual(first.read_bytes(), b"before A")
            self.assertEqual(second.read_bytes(), b"before B")
            self.assertEqual(list(root.glob(".*.new")), [])
            self.assertEqual(list(root.glob(".*.backup")), [])

    def test_first_replacement_failure_leaves_all_sources_untouched(self) -> None:
        """Preserve every chapter when the first canonical replace cannot start."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            first.write_bytes(b"before A")
            second.write_bytes(b"before B")
            real_replace = os.replace

            def failing_replace(
                source: str | bytes | Path, target: str | bytes | Path
            ) -> None:
                """Fail the first staged-new replacement and allow cleanup."""
                if str(source).endswith(".new"):
                    raise OSError("simulated first replacement failure")
                real_replace(source, target)

            with patch.object(
                translation_formatter.os,
                "replace",
                side_effect=failing_replace,
            ):
                with self.assertRaisesRegex(OSError, "first replacement failure"):
                    translation_formatter._transactional_write_json_sources(
                        {
                            first: {"value": "after A"},
                            second: {"value": "after B"},
                        }
                    )
            self.assertEqual(first.read_bytes(), b"before A")
            self.assertEqual(second.read_bytes(), b"before B")
            self.assertEqual(list(root.glob(".*.new")), [])
            self.assertEqual(list(root.glob(".*.backup")), [])

    def test_rollback_failure_is_reported_explicitly(self) -> None:
        """Never hide a replacement failure when restoring a prior file also fails."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            first.write_bytes(b"before A")
            second.write_bytes(b"before B")
            real_replace = os.replace
            new_replacements = 0

            def failing_replace(
                source: str | bytes | Path, target: str | bytes | Path
            ) -> None:
                """Fail the second commit and the subsequent first-file rollback."""
                nonlocal new_replacements
                source_text = str(source)
                if source_text.endswith(".new"):
                    new_replacements += 1
                    if new_replacements == 2:
                        raise OSError("simulated commit failure")
                if source_text.endswith(".backup") and Path(target) == first:
                    raise OSError("simulated rollback failure")
                real_replace(source, target)

            with patch.object(
                translation_formatter.os,
                "replace",
                side_effect=failing_replace,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "rollback was incomplete.*recovery backups retained",
                ):
                    translation_formatter._transactional_write_json_sources(
                        {
                            first: {"value": "after A"},
                            second: {"value": "after B"},
                        }
                    )
            self.assertNotEqual(first.read_bytes(), b"before A")
            self.assertEqual(second.read_bytes(), b"before B")
            backups = list(root.glob(".*.backup"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"before A")
            self.assertEqual(list(root.glob(".*.new")), [])

    def test_successful_transaction_writes_deterministic_json(self) -> None:
        """Commit all targets with stable UTF-8 formatting and no temp residue."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            first.write_bytes(b"before A")
            second.write_bytes(b"before B")
            pending = {
                second: {"value": "B", "number": 2},
                first: {"value": "A", "number": 1},
            }
            translation_formatter._transactional_write_json_sources(pending)
            for path, value in pending.items():
                expected = (
                    json.dumps(value, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
                self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(list(root.glob(".*.new")), [])
            self.assertEqual(list(root.glob(".*.backup")), [])

    def test_apply_changes_rolls_back_a_multi_chapter_batch(self) -> None:
        """Exercise transactional rollback through the public batch-edit function."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            first.write_text(json.dumps(canonical_source("before A")), encoding="utf-8")
            second.write_text(
                json.dumps(canonical_source("before B")), encoding="utf-8"
            )
            before_first = first.read_bytes()
            before_second = second.read_bytes()
            changes = root / "changes.json"
            changes.write_text(
                json.dumps({"A:000": "after A", "B:000": "after B"}),
                encoding="utf-8",
            )
            chapters = {
                "A": (first, canonical_source("before A")),
                "B": (second, canonical_source("before B")),
            }
            real_replace = os.replace
            new_replacements = 0

            def failing_replace(
                source: str | bytes | Path, target: str | bytes | Path
            ) -> None:
                """Fail the second canonical replacement and permit rollback."""
                nonlocal new_replacements
                if str(source).endswith(".new"):
                    new_replacements += 1
                    if new_replacements == 2:
                        raise OSError("simulated apply failure")
                real_replace(source, target)

            with (
                patch.object(
                    translation_formatter,
                    "_chapter_sources",
                    return_value=({}, chapters),
                ),
                patch.object(translation_formatter, "_contracts", return_value={}),
                patch.object(translation_formatter, "_rules_by_role", return_value={}),
                patch.object(
                    translation_formatter.os,
                    "replace",
                    side_effect=failing_replace,
                ),
            ):
                with self.assertRaisesRegex(OSError, "simulated apply failure"):
                    translation_formatter.apply_changes(changes, root)
            self.assertEqual(first.read_bytes(), before_first)
            self.assertEqual(second.read_bytes(), before_second)

    def test_migration_rolls_back_a_multi_chapter_batch(self) -> None:
        """Exercise the same transaction through adaptive-layout migration."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A.json"
            second = root / "B.json"
            source_a = canonical_source("before A", layout_policy="adaptive")
            source_b = canonical_source("before B", layout_policy="adaptive")
            del source_a["records"][0]["layout_policy"]
            del source_b["records"][0]["layout_policy"]
            first.write_text(json.dumps(source_a), encoding="utf-8")
            second.write_text(json.dumps(source_b), encoding="utf-8")
            before_first = first.read_bytes()
            before_second = second.read_bytes()
            chapters = {"A": (first, source_a), "B": (second, source_b)}
            real_replace = os.replace
            new_replacements = 0

            def failing_replace(
                source: str | bytes | Path, target: str | bytes | Path
            ) -> None:
                """Fail the second migration replacement and permit rollback."""
                nonlocal new_replacements
                if str(source).endswith(".new"):
                    new_replacements += 1
                    if new_replacements == 2:
                        raise OSError("simulated migration failure")
                real_replace(source, target)

            with (
                patch.object(
                    translation_formatter,
                    "_chapter_sources",
                    return_value=({}, chapters),
                ),
                patch.object(translation_formatter, "_contracts", return_value={}),
                patch.object(translation_formatter, "_rules_by_role", return_value={}),
                patch.object(
                    translation_formatter.os,
                    "replace",
                    side_effect=failing_replace,
                ),
            ):
                with self.assertRaisesRegex(OSError, "simulated migration failure"):
                    translation_formatter.migrate(root)
            self.assertEqual(first.read_bytes(), before_first)
            self.assertEqual(second.read_bytes(), before_second)


class RebuildSafetyTests(unittest.TestCase):
    """Keep direct rebuild paths safe and release evidence source-derived."""

    def test_direct_basename_validation_rejects_path_syntax(self) -> None:
        """Reject traversal, absolute forms, separators, dot segments, and empties."""
        self.assertEqual(
            clean_rebuild._validate_basename("Nostalgia1907_CleanRebuild_Example"),
            "Nostalgia1907_CleanRebuild_Example",
        )
        invalid = (
            "../escape",
            "/absolute",
            "C:\\absolute",
            "nested/name",
            "nested\\name",
            ".",
            "..",
            "",
            "bad name",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    clean_rebuild._validate_basename(value)

    def test_rebuild_validates_basename_before_any_build_work(self) -> None:
        """Make the independently executable rebuild API self-defending."""
        with patch.object(
            clean_rebuild,
            "_verify_production_independence",
            side_effect=AssertionError("audit should not run"),
        ):
            with self.assertRaises(ValueError):
                clean_rebuild.rebuild(
                    Path("track1"),
                    Path("track2"),
                    Path("runs"),
                    Path("delivery"),
                    "../escape",
                )

    def test_clean_production_dependency_graph_passes(self) -> None:
        """Report the exact bounded scope of the real static dependency audit."""
        report = clean_rebuild._verify_production_independence()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            report["modules_scanned"], len(clean_rebuild.PRODUCTION_MODULES)
        )
        self.assertEqual(report["unapproved_local_import_count"], 0)
        self.assertEqual(report["known_historical_marker_hit_count"], 0)

    def test_unallowlisted_local_import_is_rejected(self) -> None:
        """Reject a dependency hidden in a local non-production module."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_dependency_fixture(
                root,
                {
                    "entry.py": "import hidden\n",
                    "hidden.py": "VALUE = 1\n",
                },
            )
            with self.assertRaisesRegex(ValueError, "unapproved local imports"):
                clean_rebuild._verify_production_independence(
                    root,
                    ("entry.py",),
                )

    def test_production_data_path_escape_is_rejected(self) -> None:
        """Reject source-index paths even when the legacy directory has a new name."""
        for source_name in (
            "../renamed_history/A.json",
            "..\\renamed_history\\A.json",
            "C:renamed_history.json",
        ):
            with self.subTest(source_name=source_name):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    write_dependency_fixture(
                        root,
                        {"entry.py": "VALUE = 1\n"},
                        chapters=[
                            {
                                "chapter": "A",
                                "source": source_name,
                            }
                        ],
                    )
                    with self.assertRaisesRegex(ValueError, "one JSON filename"):
                        clean_rebuild._verify_production_independence(
                            root,
                            ("entry.py",),
                        )

    def test_clean_allowlisted_fixture_graph_passes(self) -> None:
        """Accept local imports when every dependency is explicitly allowlisted."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_dependency_fixture(
                root,
                {
                    "entry.py": "import helper\n",
                    "helper.py": "VALUE = 1\n",
                },
            )
            report = clean_rebuild._verify_production_independence(
                root,
                ("entry.py", "helper.py"),
            )
            self.assertEqual(report["local_import_edges"], ["entry.py -> helper.py"])

    def test_canonical_coverage_matches_current_sources(self) -> None:
        """Derive every published coverage count from the tracked source set."""
        coverage = clean_rebuild._canonical_coverage()
        self.assertEqual(coverage["chapter_count"], 19)
        self.assertEqual(coverage["record_count"], 2905)
        self.assertEqual(coverage["adaptive_record_count"], 2759)
        self.assertEqual(coverage["fixed_record_count"], 123)
        self.assertEqual(coverage["anchor_record_count"], 1)
        self.assertEqual(coverage["part3b_translated_record_count"], 209)
        self.assertEqual(coverage["part3b_preserved_record_indexes"], [4, 15])

    def test_release_notes_follow_changed_coverage_fixture(self) -> None:
        """Prove notes interpolate fixture counts instead of frozen prose literals."""
        with tempfile.TemporaryDirectory() as temporary:
            sources = Path(temporary)
            chapter = {
                "record_count": 2,
                "records": [
                    {
                        "index": 0,
                        "policy": "translate",
                        "text": "A",
                        "layout_policy": "adaptive",
                    },
                    {"index": 1, "policy": "preserve"},
                ],
            }
            (sources / "PART3B_.json").write_text(
                json.dumps(chapter),
                encoding="utf-8",
            )
            (sources / "index.json").write_text(
                json.dumps(
                    {
                        "chapter_count": 1,
                        "chapters": [
                            {
                                "chapter": "PART3B_",
                                "source": "PART3B_.json",
                                "record_count": 2,
                                "translated_records": 1,
                                "preserved_records": 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            coverage = clean_rebuild._canonical_coverage(sources)
            notes = clean_rebuild._render_test_notes(coverage)
            self.assertIn("all 1 chapters and 2 records", notes)
            self.assertIn("declares 1 translated records", notes)
            self.assertIn("0 translated records with explicit fixed-layout", notes)
            self.assertIn("PART3B_ contains 1 translated records", notes)
            self.assertIn("Retail records 1 remain retail-preserved", notes)


class RetailFixturePrerequisiteTests(unittest.TestCase):
    """Distinguish unavailable retail fixtures from layout invariant failures."""

    def test_missing_retail_layout_fixtures_raise_explicit_skip(self) -> None:
        """Return a SkipTest with a precise preparation instruction."""
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(unittest.SkipTest, "prepared retail"):
                layout_tests.require_retail_layout_fixtures(Path(temporary))

    def test_complete_fixture_inventory_satisfies_prerequisite(self) -> None:
        """Proceed when every required fixture path is present."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in layout_tests.required_retail_layout_files(root):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            layout_tests.require_retail_layout_fixtures(root)


if __name__ == "__main__":
    unittest.main()

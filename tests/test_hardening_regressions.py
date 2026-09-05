"""Focused regressions for repository-wide hardening findings."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from work.clean_rebuild import (
    build_archives,
    raw_cd,
    rebuild,
    translation_formatter,
)
from work.clean_rebuild.build_archives import _minimum_fixed_headroom
from work.clean_rebuild.iso9660 import IsoError, patch_fixed_extent_files
from work.clean_rebuild.lz_format import (
    LzError,
    LzSlotOverflowError,
    replace_members_fixed,
    replace_members_reflow,
)


class HardeningRegressionTests(unittest.TestCase):
    """Keep defensive fixes from regressing during later maintenance."""

    def test_archive_headroom_uses_tightest_replacement_slot(self) -> None:
        """Multi-member archives must report the least remaining capacity."""
        replacements = [
            {"member": "PART1A.MES", "headroom": 512},
            {"member": "PART1A.SCN", "headroom": 7},
        ]
        self.assertEqual(_minimum_fixed_headroom(replacements), 7)

    def test_archive_headroom_rejects_malformed_report(self) -> None:
        """Do not publish capacity evidence from missing or nonnumeric data."""
        with self.assertRaisesRegex(ValueError, "report is empty"):
            _minimum_fixed_headroom([])
        with self.assertRaisesRegex(ValueError, "invalid headroom"):
            _minimum_fixed_headroom([{"member": "TEST.MES", "headroom": None}])

    def test_archive_reflow_is_used_only_for_typed_slot_overflow(self) -> None:
        """Do not select a destructive layout fallback by parsing error text."""
        paths = (Path("retail.lz"), Path("output.lz"), {"TEST.MES": Path("test.mes")})
        reflow_report = {
            "replacements": [{"member": "TEST.MES", "headroom": 0}],
            "headroom": 23,
        }
        with (
            patch.object(
                build_archives,
                "replace_members_fixed",
                side_effect=LzSlotOverflowError("slot capacity exhausted"),
            ),
            patch.object(
                build_archives,
                "replace_members_reflow",
                return_value=reflow_report,
            ) as reflow,
        ):
            replacement, mode, headroom = build_archives._replace_archive(
                *paths, 4096
            )
        self.assertEqual(replacement, reflow_report["replacements"])
        self.assertEqual(mode, "guarded-reflow")
        self.assertEqual(headroom, 23)
        reflow.assert_called_once()

        with (
            patch.object(
                build_archives,
                "replace_members_fixed",
                side_effect=LzError("but retail slot is mentioned incidentally"),
            ),
            patch.object(build_archives, "replace_members_reflow") as reflow,
        ):
            with self.assertRaisesRegex(LzError, "mentioned incidentally"):
                build_archives._replace_archive(*paths, 4096)
        reflow.assert_not_called()

    def test_lz_writers_reject_source_output_aliases(self) -> None:
        """The retail archive must stay read-only for both rewrite strategies."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "retail.lz"
            original = b"not-a-valid-archive"
            archive.write_bytes(original)
            replacement = root / "replacement.bin"
            replacement.write_bytes(b"replacement")
            replacements = {"FILE.BIN": replacement}

            for writer in (replace_members_fixed, replace_members_reflow):
                with self.subTest(writer=writer.__name__):
                    with self.assertRaisesRegex(
                        LzError, "source and output archive paths must differ"
                    ):
                        writer(archive, archive, replacements)
                    self.assertEqual(archive.read_bytes(), original)

    def test_iso_patcher_rejects_same_source_and_output_before_truncation(self) -> None:
        """An in-place call must fail before opening the ISO for destructive write."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso = root / "retail.iso"
            original = b"not-even-a-valid-iso"
            iso.write_bytes(original)
            replacement = root / "replacement.bin"
            replacement.write_bytes(b"replacement")

            with self.assertRaisesRegex(IsoError, "source and output ISO paths must differ"):
                patch_fixed_extent_files(iso, iso, {"FILE.BIN": replacement})

            self.assertEqual(iso.read_bytes(), original)

    def test_raw_to_iso_rejects_in_place_conversion(self) -> None:
        """Reject input/output aliasing before an invalid raw track can be truncated."""
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "track.bin"
            original = b"not-a-raw-track"
            raw.write_bytes(original)
            with self.assertRaisesRegex(
                raw_cd.RawCdError, "input and ISO output paths must differ"
            ):
                raw_cd.raw_to_iso(raw, raw)
            self.assertEqual(raw.read_bytes(), original)

    def test_iso_to_raw_rejects_output_aliases_before_writing(self) -> None:
        """Protect both fixed-rebuild inputs from destructive output aliasing."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "retail.bin"
            iso = root / "translated.iso"
            template_bytes = b"template"
            iso_bytes = b"iso"
            template.write_bytes(template_bytes)
            iso.write_bytes(iso_bytes)

            for output in (template, iso):
                with self.subTest(output=output.name):
                    with self.assertRaisesRegex(
                        raw_cd.RawCdError,
                        "raw output path must differ from both rebuild inputs",
                    ):
                        raw_cd.iso_to_raw_fixed(template, iso, output)
                    self.assertEqual(template.read_bytes(), template_bytes)
                    self.assertEqual(iso.read_bytes(), iso_bytes)

    def test_cue_writer_rejects_track_aliases_before_overwrite(self) -> None:
        """Never let a CUE path or second track overwrite an existing track."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "Track1.bin"
            audio = root / "Track2.bin"
            data_bytes = b"data-track"
            audio_bytes = b"audio-track"
            data.write_bytes(data_bytes)
            audio.write_bytes(audio_bytes)

            with self.assertRaisesRegex(
                raw_cd.RawCdError,
                "CUE output path must differ from both track files",
            ):
                raw_cd.write_two_track_cue(data, data, audio)
            self.assertEqual(data.read_bytes(), data_bytes)
            self.assertEqual(audio.read_bytes(), audio_bytes)

            with self.assertRaisesRegex(
                raw_cd.RawCdError,
                "data and audio track paths must differ",
            ):
                raw_cd.write_two_track_cue(root / "game.cue", data, data)
            self.assertEqual(data.read_bytes(), data_bytes)

    def test_clean_build_root_rejects_existing_file_without_touching_it(self) -> None:
        """Report a domain error instead of leaking ``NotADirectoryError``."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "build"
            original = b"occupied"
            path.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "exists and is not a directory"):
                rebuild._ensure_empty(path)
            self.assertEqual(path.read_bytes(), original)

    def test_batch_edits_cache_contracts_per_chapter_and_rules_once(self) -> None:
        """Avoid repeated retail parsing and rule loading inside one edit batch."""
        chapter_a = {
            "chapter": "A",
            "record_count": 2,
            "records": [
                {"index": 0, "policy": "translate", "text": "old zero"},
                {"index": 1, "policy": "translate", "text": "old one"},
            ],
        }
        chapter_b = {
            "chapter": "B",
            "record_count": 1,
            "records": [
                {"index": 0, "policy": "translate", "text": "old two"},
            ],
        }
        chapters = {
            "A": (Path("A.json"), chapter_a),
            "B": (Path("B.json"), chapter_b),
        }
        changes = {
            "A:000": "new zero",
            "A:001": "new one",
            "B:000": "new two",
        }
        inferred: list[str] = []

        def fake_contracts(
            source: dict[str, object], _retail_root: Path
        ) -> dict[int, object]:
            """Record one inference per chapter while returning no SCN contract."""
            inferred.append(str(source["chapter"]))
            return {}

        audit_result = {"failures": [], "roles": [], "preview_rows": []}
        with (
            patch.object(translation_formatter, "_changes", return_value=changes),
            patch.object(
                translation_formatter,
                "_chapter_sources",
                return_value=({}, chapters),
            ),
            patch.object(
                translation_formatter,
                "_contracts",
                side_effect=fake_contracts,
            ) as contracts,
            patch.object(
                translation_formatter,
                "_rules_by_role",
                return_value={},
            ) as rules,
            patch.object(
                translation_formatter,
                "_record_audit",
                return_value=audit_result,
            ),
            patch.object(
                translation_formatter,
                "_transactional_write_json_sources",
            ) as write_sources,
        ):
            report = translation_formatter.apply_changes(
                Path("changes.json"), Path("retail")
            )

        self.assertEqual(report["changed_record_count"], 3)
        self.assertEqual(contracts.call_count, 2)
        self.assertEqual(inferred, ["A", "B"])
        rules.assert_called_once_with()
        write_sources.assert_called_once()


if __name__ == "__main__":
    unittest.main()

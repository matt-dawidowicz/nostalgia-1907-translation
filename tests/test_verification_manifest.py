"""Regression tests for cryptographic input and output report binding."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "work" / "clean_rebuild"
if str(CLEAN) not in sys.path:
    sys.path.insert(0, str(CLEAN))

import verification_manifest as provenance  # noqa: E402


class VerificationManifestTests(unittest.TestCase):
    """Prove fingerprint sensitivity, exclusions, and stale-output rejection."""

    def _inputs(self, root: Path) -> tuple[list[provenance.FileBinding], Path, Path]:
        """Create a minimal declared source set plus original track fixtures."""
        canonical = root / "canonical.json"
        production = root / "production.py"
        canonical.write_text('{"text":"current"}\n', encoding="utf-8")
        production.write_text("VALUE = 1\n", encoding="utf-8")
        track1 = root / "track1.bin"
        track2 = root / "track2.bin"
        track1.write_bytes(b"track one")
        track2.write_bytes(b"track two")
        bindings = [
            provenance.FileBinding(
                "canonical_translation_sources",
                "sources/chapter.json",
                canonical,
            ),
            provenance.FileBinding(
                "production_python",
                "work/clean_rebuild/production.py",
                production,
            ),
        ]
        return bindings, track1, track2

    def _manifest(
        self,
        bindings: list[provenance.FileBinding],
        track1: Path,
        track2: Path,
    ) -> dict[str, object]:
        """Create one fingerprint with a fixed synthetic runtime identity."""
        return provenance.create_input_manifest(
            bindings,
            track1=track1,
            track2=track2,
            build_profile={"name": "unit-test", "baseline": "reference"},
            command=["python", "work/clean_rebuild/rebuild.py", "<TRACKS>"],
            runtime={
                "python": {"implementation": "CPython", "version": "test"},
                "platform": {"system": "test", "release": "test", "machine": "test"},
                "output_affecting_dependencies": [],
            },
        )

    def test_canonical_change_changes_input_fingerprint(self) -> None:
        """Changing canonical translation bytes must alter the aggregate digest."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings, track1, track2 = self._inputs(root)
            before = self._manifest(bindings, track1, track2)
            bindings[0].path.write_text('{"text":"revised"}\n', encoding="utf-8")
            after = self._manifest(bindings, track1, track2)
            self.assertNotEqual(
                before["aggregate_input_fingerprint"],
                after["aggregate_input_fingerprint"],
            )

    def test_production_code_change_changes_input_fingerprint(self) -> None:
        """Changing declared production code must alter the aggregate digest."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings, track1, track2 = self._inputs(root)
            before = self._manifest(bindings, track1, track2)
            bindings[1].path.write_text("VALUE = 2\n", encoding="utf-8")
            after = self._manifest(bindings, track1, track2)
            self.assertNotEqual(
                before["aggregate_input_fingerprint"],
                after["aggregate_input_fingerprint"],
            )

    def test_ignored_file_change_does_not_change_input_fingerprint(self) -> None:
        """An undeclared unrelated file must remain outside the fingerprint."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings, track1, track2 = self._inputs(root)
            ignored = root / "scratch.log"
            ignored.write_text("first\n", encoding="utf-8")
            before = self._manifest(bindings, track1, track2)
            ignored.write_text("second\n", encoding="utf-8")
            after = self._manifest(bindings, track1, track2)
            self.assertEqual(
                before["aggregate_input_fingerprint"],
                after["aggregate_input_fingerprint"],
            )

    def test_output_affecting_runtime_change_changes_input_fingerprint(self) -> None:
        """Runtime identity is part of the exact execution input contract."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings, track1, track2 = self._inputs(root)
            before = self._manifest(bindings, track1, track2)
            after = provenance.create_input_manifest(
                bindings,
                track1=track1,
                track2=track2,
                build_profile={"name": "unit-test", "baseline": "reference"},
                command=["python", "work/clean_rebuild/rebuild.py", "<TRACKS>"],
                runtime={
                    "python": {"implementation": "CPython", "version": "changed"},
                    "platform": {
                        "system": "test",
                        "release": "test",
                        "machine": "test",
                    },
                    "output_affecting_dependencies": [],
                },
            )
            self.assertNotEqual(
                before["aggregate_input_fingerprint"],
                after["aggregate_input_fingerprint"],
            )

    def test_report_binds_exact_generated_artifacts(self) -> None:
        """The human and machine reports must name current direct output hashes."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings, track1, track2 = self._inputs(root)
            input_manifest = self._manifest(bindings, track1, track2)
            artifact = root / "product.bin"
            artifact.write_bytes(b"generated artifact")
            paths = {"product/product.bin": artifact}
            snapshot = provenance.snapshot_artifacts(paths)
            report = provenance.write_bound_verification(
                root,
                input_manifest=input_manifest,
                artifact_paths=paths,
                generated_snapshot=snapshot,
                verification={"status": "PASS", "checks": 3},
                manifest_name="verification_manifest.json",
                report_name="verification.json",
                report_kind="unit-test-run",
                explanation="Exact unit-test artifact binding.",
            )
            machine = json.loads(
                (root / "verification_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(machine["outputs"], snapshot)
            self.assertEqual(report["provenance"]["outputs"], snapshot)
            self.assertEqual(
                report["provenance"]["aggregate_input_fingerprint"],
                input_manifest["aggregate_input_fingerprint"],
            )
            validation = provenance.validate_bound_verification(
                root / "verification_manifest.json",
                paths,
            )
            self.assertEqual(validation["status"], "PASS")
            artifact.write_bytes(b"post-report replacement")
            validation = provenance.validate_bound_verification(
                root / "verification_manifest.json",
                paths,
            )
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(
                any("outputs differ" in item for item in validation["failures"])
            )

    def test_stale_artifact_cannot_be_reported_as_current(self) -> None:
        """Mutation after generation must abort before either report is written."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings, track1, track2 = self._inputs(root)
            input_manifest = self._manifest(bindings, track1, track2)
            artifact = root / "product.bin"
            artifact.write_bytes(b"generated artifact")
            paths = {"product/product.bin": artifact}
            snapshot = provenance.snapshot_artifacts(paths)
            artifact.write_bytes(b"stale replacement")
            with self.assertRaisesRegex(ValueError, "snapshot is stale"):
                provenance.write_bound_verification(
                    root,
                    input_manifest=input_manifest,
                    artifact_paths=paths,
                    generated_snapshot=snapshot,
                    verification={"status": "PASS"},
                    manifest_name="verification_manifest.json",
                    report_name="verification.json",
                    report_kind="unit-test-run",
                    explanation="Must never be written.",
                )
            self.assertFalse((root / "verification_manifest.json").exists())
            self.assertFalse((root / "verification.json").exists())

    def test_managed_inventory_rejects_stale_product_file(self) -> None:
        """An unrecognized product artifact must fail the pre-report inventory."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            product = root / "product"
            (build / "mes").mkdir(parents=True)
            (build / "archives").mkdir(parents=True)
            product.mkdir()
            (build / "mes" / "TEST.MES").write_bytes(b"mes")
            (build / "archives" / "TEST.LZ").write_bytes(b"lz")
            (product / "Game_Track1.bin").write_bytes(b"one")
            (product / "Game_Track2.bin").write_bytes(b"two")
            (product / "Game.cue").write_text("cue\n", encoding="utf-8")
            (product / "STALE.bin").write_bytes(b"stale")
            with self.assertRaisesRegex(ValueError, "unexpected.*STALE.bin"):
                provenance.assert_exact_managed_inventory(
                    build,
                    product,
                    "Game",
                    ["TEST"],
                )


if __name__ == "__main__":
    unittest.main()

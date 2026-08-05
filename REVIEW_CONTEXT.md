# Final source-release review context

This is a source-only final review package for the Nostalgia 1907 English
fan-translation project. It contains the current corrected working tree,
including source-integration corrections, contributor documentation, retirement of the
failed audio-localization experiment, and hardening after independent review.

## Read first

1. `README.md`
2. `docs/GETTING_STARTED.md`
3. `docs/ARCHITECTURE.md`
4. `docs/TEXT_BOX_CONTRACTS.md`
5. `docs/DEVELOPMENT.md`
6. `docs/RELEASE.md`
7. `CHATGPT_REVIEW_PROMPT.md`

## Scope and exclusions

Included: canonical source JSON, renderer/compiler/validation code, tests,
documentation, project policy, and GitHub source-check workflow.

Excluded: retail or rebuilt images, CUE files, BIOS files, extracted retail
members, comparison images, generated reports, local configuration, and the
retired audio-localization experiment.

`MANIFEST.sha256` lists every other archive member and its SHA-256. Verify it
before reviewing source conclusions.

## Current source evidence

This source-review package passed the following source-only checks after the
release-hardening corrections in this package:

- `python -m unittest discover -s tests -v`: 132 tests passed, with 1
  retail-fixture integration test skipped as designed.
- `python tools/source_health.py --root . --strict-release`: PASS, zero
  failures across the complete unpacked-package inventory.
- `python tools/style_audit.py --root .`: PASS, zero violations.
- `python -m compileall -q nostalgia1907.py tools tests work`: PASS.

The immediately preceding candidate source line was also validated on Windows
with Python 3.12.13 and privately prepared retail fixtures. That run completed
the full renderer, layout, comparison, compilation, semantic, deterministic
clean-build, and North American region-wrapper gates for all 19 chapters and
2,905 records. The resulting Track 1, Track 2, CUE, final verification report,
and test notes were byte-identical to the preceding tested candidate. Track 1
SHA-256:
`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`.

The current corrections tighten source-release inventory and invalid-input
failures without changing canonical translation records. The private
retail-backed build was not rerun in this source-only review environment, so
the historical deterministic-build evidence is not represented as a new
runtime certification.

The earlier build-comparison evidence showed that the preceding hardening
changed failure and verification behavior without changing playable bytes. The
project maintainer subsequently completed a full Ares playtest of that exact
Track 1, including targeted dialogue-renderer checks, page advances, and
dialogue transitions, with no reported defects. The source package cannot
independently replay that session; independent and future regression playtests
remain welcome, and changed playable bytes require fresh candidate-bound
evidence.

## Recent review corrections

- Public CI now audits the exact Git-tracked inventory, while unpacked source
  packages audit every member. Ignored retail/output directory names no longer
  conceal release contamination.
- The strict release audit rejects local configuration, generated images,
  emulator states, Python caches, and private/generated directory contents.
- The translation editor validates the complete embedded profile before retail
  lookup or canonical mutation, and direct row-limit inference rejects
  noncanonical aliases such as `"01"`.
- Retained forensic utilities require explicit historical input paths and no
  longer contain a contributor-machine default.
- Adaptive records without SCN geometry or a recognized non-prose renderer
  contract fail compilation before bytes are emitted.
- Indexed renderer profile fields reject aliases, stale/out-of-range indexes,
  preserve-record targets, and invalid values.
- The North American wrapper has no report-only publication path. Publication
  re-derives the expected boot from locked inputs and revalidates both staged
  products directly.
- Wrapper basenames reject path-like values.
- Retired generated recovery reports and their utility were removed; source
  health prevents their reintroduction.

No Japanese records, record IDs/order, policies, reviewed English text, SCN
content, archive boundaries, ISO extents, or Track 2 bytes changed in these
corrections. A stale PART2F metadata pointer to a deleted generated report was
removed.

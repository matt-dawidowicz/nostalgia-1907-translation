# Source-release review context

This document gives reviewers the current source-only context for the Nostalgia
1907 English fan-translation project. It separates three things that must not be
conflated:

1. the runtime-certified 1.0.2 reference;
2. the later 2026-08-27 translation revision, which changes playable bytes; and
3. source-only repository maintenance and validation hardening that do not
   change canonical English or byte-generating behavior.

## Read first

1. `README.md`
2. `docs/GETTING_STARTED.md`
3. `docs/ARCHITECTURE.md`
4. `docs/TEXT_BOX_CONTRACTS.md`
5. `docs/DEVELOPMENT.md`
6. `docs/TRANSLATION_REVISION_20260827.md`
7. `docs/RELEASE.md`
8. `CHATGPT_REVIEW_PROMPT.md`

Verify `MANIFEST.sha256` before source review:

```text
python tools/source_manifest.py --root .
```

## Scope and exclusions

Included: canonical source JSON, active renderer/compiler/validation code,
source tests, documentation, project policy, GitHub source checks, and historical
review provenance under `provenance/`.

Excluded: retail or rebuilt images, CUE files, BIOS files, extracted retail
members, comparison images, generated reports, local configuration, and the
retired audio-localization experiment.

The source manifest lists every other tracked review-bundle member and excludes
only itself.

## 2026-09-01 maintenance modernization and validation hardening

This maintenance pass does **not** change canonical translation records,
binary-format behavior, renderer behavior, frozen retail hashes, playable-byte
algorithms, or historical runtime/release claims. It does make narrowly scoped
mechanical changes inside maintained modules where those changes remove obsolete
Python syntax or stale verification bookkeeping, and it makes future runtime
certification fail closed against incomplete or hand-edited evidence.

- the supported Python floor moves from 3.10 to 3.12;
- the Python 3.10-only `tomli` compatibility dependency and fallback code are
  removed, leaving the runtime dependency list empty;
- the package metadata now uses a current setuptools baseline and explicit MIT
  license/repository metadata;
- Ruff is pinned as a development-only dependency, targets Python 3.12, and
  enables pyupgrade checks for obsolete syntax/APIs;
- CI now exercises Python 3.12 on Ubuntu and Python 3.14 on Windows;
- the completed translation-proposal compatibility shim is removed rather than
  retained as an inert no-pending exporter;
- the obsolete retired-workspace registry is removed after its durable history
  was already captured in maintenance documentation;
- obsolete standalone report-writing CLIs are removed from validation libraries;
- generic hand-written lint rules are replaced by Ruff while the project-specific
  docstring contract remains enforced by `tools/style_audit.py`;
- `scn_layout.py` receives only a Python-3.12-safe annotation modernization;
- `verification_manifest.py` drops references to the retired files so a real
  build cannot attempt to fingerprint maintenance artifacts that no longer exist;
- `whole_game_test.py` now requires the supported schema, successful static
  summaries, exact candidate filename/hash binding, intact generated runtime
  inventories, evidence notes for completed scopes, and an empty runtime issue
  list before certification can pass; and
- regression tests explicitly reject unbound candidates, missing evidence,
  failed static coverage, and deleted certification scopes.

Because canonical English and byte-generating behavior are unchanged, this pass
requires source-only CI evidence and does not itself require a new Ares
playthrough. The stricter verifier applies to future candidate certification; it
does not retroactively invent or change historical 1.0.2 evidence.

## 2026-08-30 repository-maintenance pass

The maintenance pass intentionally does **not** change canonical records,
production-module code, binary formats, renderer behavior, project hashes, or
release/runtime claims. Its scope is repository hygiene:

- one-off translation applicators, forensic decoders, capacity planners,
  intermediate snapshots, and obsolete report/export scripts were removed from
  `work/clean_rebuild/`;
- the completed translation-proposal exporter was reduced to its explicit
  no-pending status contract instead of retaining the old active-analysis
  machinery;
- reviewed 2026-08-27 change ledgers were moved out of the active `work/`
  namespace into `provenance/2026-08-27/`;
- the README, architecture, development guide, and ignore rules were tightened
  around the supported surfaces;
- documentation coverage now derives the maintained Python surface rather than
  hard-coding a long file list; and
- `tools/source_manifest.py` plus CI coverage now make `MANIFEST.sha256` a
  generated-and-verified contract instead of a manual inventory.

This pass therefore requires source-only regression evidence but does not, by
itself, trigger a new Ares playthrough. Any later change to canonical English or
byte-producing code remains subject to the normal candidate-bound runtime rule.

## 2026-08-27 post-1.0.2 translation revision

The current canonical source contains the complete Japanese-semantic and
character-voice revision that was not part of 1.0.2. The semantic application
changed 345 canonical records, followed by reviewed voice, ending, capacity,
and validator passes.

The final revision was reported green on Windows/Python 3.12 and Ubuntu/Python
3.10 source CI. Retail-backed validation passed the 17-test layout suite, all 19
MES chapters, and all 19 LZ archive rebuilds; PART3C was 16,073 bytes (`0x3EC9`)
and minimum archive headroom was 168 bytes. Those results are recorded in
`docs/TRANSLATION_REVISION_20260827.md`.

That is source/build evidence, not runtime certification. The playable bytes
changed, so the historical 1.0.2 Ares evidence cannot be inherited.

## Historical 1.0.2 runtime reference

The latest runtime-certified North American Track 1 remains:

`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`

Its unchanged Track 2 SHA-256 is:

`F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991`

That exact 1.0.2 Track 1 completed a full maintainer Ares playthrough, including
targeted lower-dialogue checks, page advances, and dialogue transitions, with no
reported defect. The current post-1.0.2 source revision still needs its own
fresh deterministic two-track build and candidate-bound Ares evidence before it
can become a runtime-certified successor.

## Preservation boundary

Reviewers should confirm that current source work preserves:

- all 19 chapter names and 2,905 record positions;
- Japanese records, stable IDs/order, and preserve/translate policy;
- SCN/control bytes and non-MES archive members;
- fixed ISO extents and raw Track 1 geometry;
- Track 2 byte-for-byte;
- North America as the default supported build region; and
- the distinction between static/deterministic proof and runtime evidence.

Historical ledgers under `provenance/` are evidence only. They must never be
imported by production code or treated as alternate canonical source.

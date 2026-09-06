# Source-release review context

This document gives reviewers the current source-only context for the Nostalgia
1907 English fan-translation project. Read
[`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) first; dated revision and
maintenance files are historical evidence, not current-state summaries.

The current review must keep three evidence classes separate:

1. the runtime-certified **1.0.2** reference;
2. the cumulative **post-1.0.2 successor source line**, which now includes
   translation, renderer/runtime, fixed-layout, STAFF, hardening, and performance
   changes; and
3. candidate-specific retail/runtime evidence, which is valid only for the exact
   source and output hashes that produced it.

## Read first

1. `docs/CURRENT_STATUS.md`
2. `README.md`
3. `docs/GETTING_STARTED.md`
4. `docs/ARCHITECTURE.md`
5. `docs/TEXT_BOX_CONTRACTS.md`
6. `docs/DEVELOPMENT.md`
7. `docs/RELEASE.md`
8. `docs/WHOLE_GAME_TESTING.md`
9. `CHATGPT_REVIEW_PROMPT.md`

Dated records such as `docs/TRANSLATION_REVISION_20260827.md`,
`docs/PROLOGUE_PACING_REVISION_20260901.md`, and
`docs/HISTORICAL_MAINTENANCE_REPORT.md` should be consulted when reviewing the
history of a particular change.

Verify the maintained source contract with:

```text
python -m tools.source_checks --root . --strict-release
```

## Scope and exclusions

Included: canonical source JSON, active renderer/compiler/validation code,
source tests, documentation, project policy, GitHub source checks, and historical
review provenance under `provenance/`.

Excluded: retail or rebuilt images, CUE files, BIOS files, extracted retail
members, comparison images, generated reports, local configuration, and retired
experiments.

`MANIFEST.sha256` describes the exact tracked source-review tree except for the
manifest itself. It is generated, not hand-maintained.

## Current maintained source line

The present source is no longer just the 2026-08-27 revision. The following
major work is integrated:

- full-corpus Japanese source-fidelity and character-voice revision;
- complete English-script audit and first-play pacing/clarity pass;
- late-game source/terminology corrections;
- shared lower-dialogue continuation and apostrophe-spacing corrections;
- the closed hash-locked PART1A Game Hall selector-coordinate fix;
- exhaustive retail-backed layout/script-integrity gates, including fixed
  layouts, SCN-to-MES references, choice branches, and preserved-render identity;
- STAFF credit correction/centering;
- defensive build, path, archive, verification, and source-health hardening;
- removal of obsolete maintenance/proposal/profile compatibility state;
- deterministic rebuild performance optimizations; and
- repository-wide Ruff format/lint, PEP 257, and maintained mypy checks.

The canonical project contract is 19 chapters / 2,905 records, with 2,883
translated and 22 deliberately preserved.

## Public source gate and CI

The source-only contract is implemented by `tools/source_checks.py`. It checks:

- source-tree health and publication policy;
- exact `MANIFEST.sha256` identity;
- production-module/data dependency containment;
- maintained-Python compilation;
- source-only unit tests;
- Ruff formatting;
- Ruff linting;
- the maintained mypy target set; and
- the public-API documentation policy.

CI runs the complete gate on Ubuntu/Python 3.12 and Windows/Python 3.14, plus
compile/unit compatibility on Ubuntu/Python 3.13 and 3.14. Do not use older
documents that describe only Ubuntu 3.10/3.12, a two-command lint setup, Black,
or an optional package-install workflow as the current CI contract.

## Release evidence boundary

The 1.0.2 North American Track 1 remains:

`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`

Track 2 remains:

`F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991`

That exact 1.0.2 Track 1 completed the recorded full maintainer Ares playthrough.
The successor source line does not inherit it.

Intermediate successor commits have completed substantial retail-backed
compilation/determinism work and targeted Ares checks. Those results are useful
regression evidence, but later source/playable/production changes mean the
current successor must still freeze an exact final commit, generate a fresh
North American candidate, record its deterministic hashes, and complete the
candidate-bound whole-game Ares log before a new release claim.

## Preservation boundary

Reviewers should confirm that current source work preserves:

- all 19 chapter names and 2,905 record positions;
- Japanese records, stable IDs/order, and preserve/translate policy;
- retail SCN/control structure except the single closed PART1A correction;
- non-MES archive data outside declared changes;
- fixed ISO extents and raw Track 1 geometry;
- Track 2 byte-for-byte;
- North America as the default supported build region; and
- the distinction between static/deterministic proof and runtime evidence.

Historical ledgers under `provenance/` are evidence only. They must never be
imported by production code or treated as alternate canonical source.

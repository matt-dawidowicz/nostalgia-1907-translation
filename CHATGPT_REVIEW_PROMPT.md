# Nostalgia 1907 source-release review prompt

I am attaching a source-only review package for the Nostalgia 1907 English
fan-translation project. Treat `docs/CURRENT_STATUS.md` as the authoritative
current-state summary. Dated revision/maintenance documents are historical
snapshots and may contain then-current hashes, test counts, or pending-work
statements that were superseded later.

The runtime-certified published reference is still version 1.0.2. Its exact
North American Track 1 completed the recorded full maintainer Ares playthrough.
The maintained source is now a cumulative post-1.0.2 successor line containing
translation, renderer/runtime, fixed-layout, STAFF, hardening, and performance
changes. Do **not** transfer the 1.0.2 runtime evidence to that successor.

First, extract the archive and read these files in order:

1. `docs/CURRENT_STATUS.md`
2. `REVIEW_CONTEXT.md`
3. `README.md`
4. `docs/GETTING_STARTED.md`
5. `docs/ARCHITECTURE.md`
6. `docs/TEXT_BOX_CONTRACTS.md`
7. `docs/DEVELOPMENT.md`
8. `docs/RELEASE.md`
9. `docs/WHOLE_GAME_TESTING.md`

Then verify the archive's `MANIFEST.sha256`. Confirm that the package contains
only source, tests, documentation, and tracked provenance—no BIOS, retail game
data, extracted assets, generated images, screenshots, BIN/CUE, or local
configuration.

If code execution is available, run the maintained source contract:

```text
python -m tools.source_checks --root . --strict-release
```

Do not replace it with an older hand-copied list of checks. The unified gate
owns source health, manifest verification, production-dependency policy,
compilation, source-only tests, Ruff format, Ruff lint, mypy, and public-API
documentation checks.

## Project constraints

- The canonical corpus is 19 chapters and 2,905 records.
- Preserve all Japanese records, stable IDs/order, policies, reviewed English,
  binary boundaries, and Track 2 except where a reviewed task explicitly changes
  canonical English.
- Retail SCN is the structural authority. The only maintained generated SCN
  mutation is the closed, hash-locked two-byte PART1A Game Hall selector
  correction.
- North America must remain the default build region. Japan is diagnostic only;
  Europe is not supported.
- Rebuild only from verified Japanese retail inputs. Never use a prior translated
  image, generated MES, or previous candidate as a build input.
- The native renderer is retained. Do not propose a speculative new text engine
  or chapter-specific binary workaround from screenshots alone.
- Retired one-off forensic, proposal, migration, and audio-localization work must
  not reappear as active production dependencies.

## Review assignment

Perform a rigorous static source/release review. Audit:

1. **Shared text pipeline** — SCN-derived layout, formatter, active fail-closed
   profile schema, compiler, and direct compiler enforcement of token/layout
   boundaries.
2. **Preservation boundaries** — canonical JSON, MES/SCN, archive/ISO/raw-CD
   checks, authenticated unchanged-sector reuse, Track 2, and the guarded North
   American wrapper.
3. **Script integrity** — SCN-to-MES references, choice branches, preserved-record
   render identity, fixed-layout ownership, and chapter/record coverage.
4. **Validation** — duplicate JSON keys, malformed-profile handling,
   deterministic report/build contracts, unified source checks, Ruff/mypy,
   source manifest, and regression coverage.
5. **Release safety** — fresh staging, deterministic two-run clean and region
   stages, exact candidate binding, default North American selection, and
   source-tree hygiene.
6. **Documentation** — whether a contributor can distinguish current status from
   historical snapshots and source proof from Ares runtime evidence.

## Evidence rules

- Report only evidence-based findings. Every finding needs severity (`P0`–`P3`),
  exact file and line(s), explanation, and the smallest safe fix or regression
  test.
- Do not invent runtime bugs from static code. Static checks and deterministic
  hashes prove reproducibility and preservation boundaries, not on-screen redraw,
  page advances, transitions, save/reload behavior, or route coverage.
- Do not rewrite translation text or recommend changing canonical text without
  identifying the exact record and a source-supported reason.
- Do not recommend adding copyrighted game assets, a BIOS, or generated builds
  to the repository.
- Treat intermediate successor hashes as historical development evidence unless
  the current release docs explicitly bind them to the frozen candidate under
  review.
- If no problem exists in an area, say so plainly. Do not invent redesign work
  merely because the project is complex.

## Required response format

1. **Archive integrity** — manifest result, source-only content result, and any
   missing/extra files.
2. **Source assessment** — choose exactly one:
   - `SOURCE RELEASE: APPROVE`
   - `SOURCE RELEASE: HOLD`

   State the decisive evidence.
3. **Findings** — ordered P0 through P3. Include only actionable findings with
   exact code/doc references.
4. **Preservation audit** — confirm or challenge corpus/binary boundaries,
   default region, and retired-work removal.
5. **Runtime/release boundary** — distinguish the exact 1.0.2 runtime reference
   from the current successor candidate. Identify only candidate-specific work
   still required by `docs/CURRENT_STATUS.md`, `docs/RELEASE.md`, and the
   generated whole-game plan.
6. **Minimal next action** — one concrete action only. If no source blocker is
   found, say `No source change is required.` If the successor is not yet
   runtime-certified, the next action should normally be the exact frozen-
   candidate build or runtime-certification step rather than another broad
   modernization pass.

Do not provide a broad redesign proposal. The goal is a trustworthy decision
with clear separation between source evidence, deterministic build evidence,
and emulator evidence.

# Nostalgia 1907 final release review prompt

I am attaching `Nostalgia1907_Source_Review.zip`, a source-only review package
for the Nostalgia 1907 English fan-translation project. This is the final
independent review before source publication. The hash-identified runtime
reference completed a full maintainer Ares playtest; assess that evidence while
welcoming independent regression testing and preserving the requirement for
fresh runtime evidence whenever playable bytes change.

First, extract the archive and read these files in order:

1. `REVIEW_CONTEXT.md`
2. `README.md`
3. `docs/GETTING_STARTED.md`
4. `docs/ARCHITECTURE.md`
5. `docs/TEXT_BOX_CONTRACTS.md`
6. `docs/DEVELOPMENT.md`
7. `docs/RELEASE.md`

Then verify the archive's `MANIFEST.sha256`. Confirm that the package contains
only source, tests, and documentation—no BIOS, retail game data, extracted
assets, generated images, screenshots, BIN/CUE, or local configuration.

## Project constraints

- The canonical corpus is 19 chapters and 2,905 records.
- Preserve all Japanese records, record IDs and order, policies, reviewed
  English, SCN/control bytes, archive member order, fixed ISO extents, and
  Track 2 exactly.
- North America must remain the default build region. Japan is diagnostic only;
  Europe is not supported.
- The source is designed to rebuild from verified Japanese retail inputs. Never
  use a prior translated image, generated MES, or a disc image as an input.
- The native renderer is retained. Do not propose a speculative new text engine
  or chapter-specific binary workaround from screenshots alone.
- The optional audio-localization experiment was intentionally retired. It
  must not reappear as active code, tests, dependencies, runtime data, or
  documentation that implies it remains supported. Historical notes may state
  only that it was removed.

## Review assignment

Perform a rigorous static release review. If you can run code, run the
documented source-only checks. If you cannot, say so and review the checked-in
tests and contracts instead.

Audit these areas:

1. **Shared text pipeline** — SCN-derived layout, formatter, profile schema,
   compiler, and direct compiler enforcement of token boundaries.
2. **Preservation boundaries** — canonical JSON, MES/SCN, archive/ISO/raw-CD
   checks, Track 2, and the guarded North American wrapper.
3. **Validation** — duplicate JSON keys, malformed profile handling,
   deterministic report/build contracts, source health, style audit, and test
   coverage.
4. **Release safety** — clean staging behavior, neutral output naming, default
   North American selection, absence of obsolete build inputs, and public-tree
   hygiene.
5. **Documentation** — whether a new contributor can identify the right path,
   make a safe translation change, and distinguish source proof from Ares
   evidence.

## Evidence rules

- Report only evidence-based findings. Every finding needs severity (`P0`–`P3`),
  exact file and line(s), explanation, and the smallest safe fix or regression
  test.
- Do not invent runtime bugs from static code. Static checks and deterministic
  hashes prove reproducibility and boundary preservation, not on-screen redraw,
  page advances, transitions, save/reload behavior, or branch coverage.
- Do not rewrite translation text or recommend changing canonical text without
  identifying the exact record and a source-supported reason.
- Do not recommend adding copyrighted game assets, a BIOS, or generated builds
  to the repository.
- If no problem exists in an area, say so plainly. Do not offer speculative
  redesign work simply because the project is complex.

## Required response format

1. **Archive integrity** — manifest result, source-only content result, and any
   missing/extra files.
2. **Release assessment** — choose exactly one:
   - `SOURCE RELEASE: APPROVE`
   - `SOURCE RELEASE: HOLD`

   State the decisive evidence. Separately assess playable-release confidence
   from the exact hash-bound full Ares playtest and identify only genuinely
   unrecorded independent or changed-candidate runtime scope.
3. **Findings** — ordered P0 through P3. Include only actionable findings with
   exact code/doc references.
4. **Preservation audit** — confirm or challenge the corpus/binary boundaries,
   default region, and retired-audio removal.
5. **Recorded and future runtime evidence** — confirm the exact candidate hash
   and completed full Ares playtest, then identify only independent regression
   opportunities or fresh checks required by changed playable bytes. Do not
   restate completed checks as pending.
6. **Minimal next action** — one concrete action only. If no source blocker is
   found, say: `Commit, merge, and publish the source release.`

Do not provide a broad redesign proposal. The goal is a trustworthy final
release decision with clear separation between source evidence and emulator
evidence.

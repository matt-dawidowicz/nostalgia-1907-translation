# Getting started

This guide is the shortest safe route into the project. It is for contributors
who have not worked with Mega-CD images, SCN programs, or the earlier
translation history. Start here before reading the deeper format documents.

## Current release status

Version 1.0.2 remains the latest runtime-certified published reference; its
hash-identified North American build completed the recorded full maintainer Ares
playtest with no reported defects. The current source tree contains a later
2026-08-27 translation revision whose playable bytes change. Its source and
retail-backed static gates are green, but it still needs a fresh deterministic
release build and candidate-bound runtime checks. Read [the revision
record](TRANSLATION_REVISION_20260827.md) and [release policy](RELEASE.md)
before preparing a build for publication.

## Pick a contributor path

Choose the smallest path that matches your task.

| Path | You need | You may change | You must not claim |
| --- | --- | --- | --- |
| Source review | A normal source clone and Python | Documentation, tests, or synthetic formatter fixtures | A retail build or runtime result |
| Translation edit | Verified local retail inputs | Reviewed canonical English JSON after preview and validation | That a static preview proves Ares behavior |
| Renderer investigation | Retail inputs plus SCN evidence and Ares access | Shared formatter/compiler/layout rules with regression tests | That one screenshot proves a general rule |
| Release maintenance | Verified tracks, the U.S. BIOS, and Ares | A clean North American candidate and its evidence | That a successful build alone is a release certification |

North America is the default release region. Japan is an explicit diagnostic
override. Europe is not a supported target.

## Learn the three kinds of data

The project deliberately separates three authorities:

1. **Retail input** is the original Japanese disc and extracted structure. It
   is local, hash-guarded, read-only, and never committed.
2. **Canonical source** is tracked JSON and supporting policy. It is the only
   place reviewed English may be edited.
3. **Generated output** is MES, archives, reports, comparisons, and BIN/CUE
   files. It is disposable evidence, never an input to a later rebuild.

If a proposed change crosses one of these boundaries, stop and read
[Architecture](ARCHITECTURE.md) and [Binary formats](BINARY_FORMATS.md) before
editing anything.

## First session: source-only checkout

Use Python 3.11 or newer and install the development checks:

```powershell
python -m pip install -e ".[dev]"
python tools/source_health.py --root . --strict-release
python -m unittest discover -s tests -v
python -m ruff check nostalgia1907.py tools tests work
python tools/style_audit.py --root .
```

These commands are safe in a public clone and require no game media or BIOS.
Read failures from top to bottom. Do not remove a check, relax a hash, or add a
generated file merely to make the command pass. A contributor without private
retail fixtures can still improve documentation, tests, parsing, and synthetic
renderer coverage.

## First session: maintainer checkout

Keep private paths in the ignored `nostalgia1907.local.json` file. Supply your
own verified Japanese Track 1, Track 2, and U.S. Sega CD BIOS; do not copy
those files into the repository.

```powershell
python nostalgia1907.py doctor
python nostalgia1907.py prepare
python nostalgia1907.py validate
python nostalgia1907.py build --dry-run
```

The real `build` command uses empty staging and delivery directories, then
performs two clean builds and two North American wrapper builds. It creates the
neutral `Nostalgia1907_CleanRebuild_NorthAmerica` candidate name by default.
Load the resulting `.cue` in Ares; do not load an individual `.bin` file.

## Make a translation change safely

1. Find the stable `CHAPTER:NNN` ID in
   `work/clean_rebuild/sources/<CHAPTER>.json`.
2. Read its `policy`; `preserve` records are not translation targets.
3. Preview the wording through the supported CLI. Do not hand-wrap a record to
   imitate a screenshot.
4. Apply only reviewed wording to canonical JSON.
5. Run `validate`, then build and Ares-test the affected scene if the change is
   intended for release.

```powershell
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording"
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording" --apply
python nostalgia1907.py validate
```

The compiler and formatter own row selection. Translation text should remain
semantic English, not a collection of spacing workarounds.

## Diagnose before choosing a fix

| Observation | First place to investigate | Safe response |
| --- | --- | --- |
| Awkward or incorrect English | Canonical record and its policy | Revise reviewed wording and preview it |
| Repeated broken word, spacing, or page behavior | SCN-derived renderer class and shared formatter | Add a general test and fix shared code only with runtime evidence |
| One-off fixed overlay is wrong | The record's fixed-layout contract | Preserve placement unless SCN evidence establishes a broader rule |
| Build/ISO/track failure | First failing validation stage | Repair the reported invariant; never waive it |
| Ares-only defect | Candidate hash, record ID, route, and transition state | Record reproducible runtime evidence before changing the renderer |

For renderer work, test page advances, dialogue transitions, save/reload, and
normal progression. Static validation guards data and contracts; it cannot
prove emulator redraw behavior.

## Before opening a pull request

Run the checks appropriate to your path, inspect `git diff`, and make sure no
BIOS, retail input, extracted member, generated image, comparison screenshot,
or local configuration file is staged. Use [Contributing](../CONTRIBUTING.md)
for the full review checklist.

## Where to go next

- Need the command and validation details? Read [Development and
  validation](DEVELOPMENT.md).
- Need to understand text boxes? Read [Text-box contracts](TEXT_BOX_CONTRACTS.md).
- Need to change English safely? Read [Translation editing](TRANSLATION_EDITING.md).
- Need to build or publish? Read [Release and playtest policy](RELEASE.md).
- Need a whole-game playtest plan? Read [Whole-game testing](WHOLE_GAME_TESTING.md).

# Contributing to the Nostalgia 1907 translation

This repository is both a translation project and a binary-preservation
project. A wording change is acceptable only when it remains semantically
correct, fits the renderer selected by the original SCN program, compiles inside
original binary boundaries, and leaves unrelated game data untouched.

Start with:

- [Getting started](docs/GETTING_STARTED.md) for contributor paths and safe first
  commands.
- [Architecture](docs/ARCHITECTURE.md) for the trust model, production pipeline,
  and module boundaries.
- [Translation editing](docs/TRANSLATION_EDITING.md) for stable record IDs,
  canonical JSON, previewing, and batch edits.
- [Text-box contracts](docs/TEXT_BOX_CONTRACTS.md) for renderer ownership.
- [Binary formats](docs/BINARY_FORMATS.md) for MES, LZ, ISO, raw-CD, font, and
  SCN structures.
- [Development and validation](docs/DEVELOPMENT.md) for source/retail test layers
  and generated evidence.
- [Whole-game testing](docs/WHOLE_GAME_TESTING.md) and
  [release policy](docs/RELEASE.md) for runtime evidence.
- [the 2026-08-27 revision record](docs/TRANSLATION_REVISION_20260827.md) for the
  current post-1.0.2 source state.
- [the Python documentation standard](docs/DOCSTRING_STANDARD.md) for maintained
  code comments and docstrings.

## Contribution licensing

By submitting an original contribution, you license it under the license that
applies to its subject:

- code, tests, build tooling, and technical documentation: [MIT](LICENSE);
- reviewed English translation prose, glossary text, and translation-editing
  notes: [CC BY-NC-SA 4.0](LICENSE-TRANSLATION.md).

Do not add original game files, BIOS files, extracted assets, or other
third-party material without explicit rightsholder authorization. See
[THIRD_PARTY_NOTICE.md](THIRD_PARTY_NOTICE.md).

## Non-negotiable invariants

Every contribution must preserve unless the change is explicitly about the
relevant verified format contract:

- original Japanese Track 1 and Track 2 as read-only inputs;
- all 19 chapter names and all 2,905 record positions;
- stable record IDs/order and `policy: "preserve"` records;
- SCN bytes, branch targets, and non-MES archive members;
- fixed ISO extents and total logical ISO size;
- raw Track 1 sector geometry, headers, boot data, EDC, and ECC;
- Track 2 byte-for-byte; and
- the distinction between canonical text and generated wrapping.

Do not repair a screenshot by adding a chapter-specific binary patch. Correct
the canonical English when wording is wrong, or correct a shared renderer rule
when structurally equivalent windows are formatted wrong.

## Recommended workflow

1. Install the project and run `doctor`.
2. Prepare the retail reference from the exact original Japanese Track 1.
3. Identify the stable `CHAPTER:NNN` record.
4. Preview the English change with `edit`.
5. Apply only after the preview shows the expected role and rows.
6. Regenerate the comparison package when translation content changed.
7. Run complete validation.
8. Build only when a new BIN/CUE candidate is actually needed.
9. Playtest the affected scene; automated checks do not replace runtime
   evidence.

Typical commands:

```powershell
python nostalgia1907.py doctor
python nostalgia1907.py prepare
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording"
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording" --apply
python nostalgia1907.py compare
python nostalgia1907.py validate
```

## Put changes in the right layer

A translation-only change normally touches canonical files under
`work/clean_rebuild/sources/` and ignored regenerated reports. A renderer change
belongs in shared layout/compiler logic with a general regression test. A
binary-format change requires format evidence, malformed-input coverage,
round-trip or independent verification, and preservation-boundary tests.

`work/` contains active operator/build workspaces only. Historical reviewed
change ledgers belong under `provenance/`; generated evidence belongs under the
ignored `outputs/`. One-off forensic decoders, migration applicators,
intermediate snapshots, and ad-hoc capacity/report scripts should not be added
to the maintained clean-rebuild surface after their conclusions have been
promoted into shared code/tests/documentation.

Embedded chapter profiles are schema-checked. Add only documented active
fields. Historical `text_sources` values must be portable labels, never local
machine paths.

## Before requesting review

Use Python 3.12 or newer and install the development checks:

```powershell
python -m pip install -e ".[dev]"
```

Then run:

```powershell
python tools/source_health.py --root . --strict-release
python tools/source_manifest.py --root .
python -m compileall -q nostalgia1907.py tools tests work
python -m unittest discover -s tests -v
python -m ruff check nostalgia1907.py tools tests work
python tools/style_audit.py --root .
```

If intentional tracked source changed, regenerate the review manifest first:

```powershell
python tools/source_manifest.py --root . --write
```

Then inspect:

```powershell
git status --short
git diff --check
git diff -- work/clean_rebuild/sources
```

Confirm that canonical-source diffs are intentional and that no BIOS, retail
image, extracted media, generated comparison package, emulator state, BIN/CUE,
or local configuration is tracked.

A contributor without retail media can run every source-only command and the
synthetic renderer/region tests. Retail-backed validation, deterministic builds,
and candidate-bound Ares evidence remain maintainer responsibilities before a
release claim.

Documentation is part of the implementation. Maintained Python callables follow
[docs/DOCSTRING_STANDARD.md](docs/DOCSTRING_STANDARD.md), including non-obvious
assumptions, side effects, and expected failures. Comments should explain a
preservation or design decision rather than translate Python statements into
English.

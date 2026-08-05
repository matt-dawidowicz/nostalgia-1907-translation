# Contributing to the Nostalgia 1907 translation

This repository is both a translation project and a binary-preservation
project. A wording change is successful only when it remains semantically
correct, fits the renderer selected by the original SCN program, compiles
inside every original binary boundary, and leaves unrelated game data
untouched.

Start with these references:

- [Getting started](docs/GETTING_STARTED.md) identifies the supported
  contributor paths and the first commands that are safe without retail media.
- [Architecture](docs/ARCHITECTURE.md) explains the trust model, production
  pipeline, and module ownership.
- [Translation editing](docs/TRANSLATION_EDITING.md) explains stable record
  IDs, canonical JSON, previewing, batch edits, and screenshot-driven review.
- [Binary formats](docs/BINARY_FORMATS.md) documents the MES, LZ, ISO, raw-CD,
  font, and SCN structures enforced by the code.
- [Development and validation](docs/DEVELOPMENT.md) explains the test layers,
  generated reports, debugging sequence, and extension rules.
- [Release and playtest policy](docs/RELEASE.md) defines what automated proof
  establishes, records the completed 1.0.2 Ares playtest reference, and
  defines the Ares evidence required for changed playable bytes.
- [Python documentation standard](docs/DOCSTRING_STANDARD.md) defines the
  PEP 257 docstring and PEP 8 explanatory-comment contract for maintained code.

## Contribution licensing

By submitting an original contribution, you license the contribution to this
project under the license that applies to its subject:

- code, tests, build tooling, and technical documentation: [MIT](LICENSE);
- reviewed English translation prose, glossary text, and translation-editing
  notes: [CC BY-NC-SA 4.0](LICENSE-TRANSLATION.md).

Contributions must not add original game files, BIOS files, extracted assets,
or any other third-party material without explicit authorization from its
rightsholder. The project can license only its contributors' original work;
see [the third-party materials notice](THIRD_PARTY_NOTICE.md) for the full
boundary.

## Non-negotiable invariants

Every contribution must preserve:

- the original Japanese Track 1 and Track 2 as read-only inputs;
- all 19 chapter names and their order;
- all 2,905 MES record indexes and their order;
- records declared with `policy: "preserve"`;
- SCN bytes, branch targets, and non-MES archive members;
- fixed ISO extents and the total logical ISO size;
- raw Track 1 sector geometry, headers, boot data, EDC, and ECC;
- Track 2 byte-for-byte;
- the distinction between canonical text and generated wrapping.

Do not repair a screenshot by adding a chapter-specific binary patch. Correct
the canonical English when the wording is wrong, or correct the shared
renderer/layout inference when the same class of windows is formatted wrong.

## Recommended workflow

1. Install the tool and run `doctor`.
2. Prepare the retail reference from an exact original Japanese Track 1.
3. Identify the stable `CHAPTER:NNN` record.
4. Preview the proposed English with `edit`.
5. Apply only after the preview identifies the expected role and rows.
6. Regenerate the comparison package.
7. Run the complete validation command.
8. Build only when a new BIN/CUE is explicitly needed.
9. Playtest the affected scene; automated checks do not replace this gate.

The normal command sequence is:

```powershell
python nostalgia1907.py doctor
python nostalgia1907.py prepare
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording"
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording" --apply
python nostalgia1907.py compare
python nostalgia1907.py validate
```

## Scope changes deliberately

A translation-only change should normally touch one or more files under
`work/clean_rebuild/sources/` and regenerated ignored reports. A layout-engine
change should include tests that demonstrate a general SCN role or renderer
rule. A binary-format change requires stricter evidence: format analysis,
round-trip tests, unchanged-boundary proofs, and a deterministic two-run build.

Historical investigation directories are evidence, not production
dependencies. Do not import from them or copy their generated binaries into the
clean rebuild.

Embedded chapter profiles are schema-checked. Add only a documented active
field; unknown keys fail validation, while specifically enumerated historical
keys are retained as legacy no-op provenance. Historical `text_sources` values
must be portable labels, never contributor-machine paths.

## Before requesting review

Run:

```powershell
python tools/source_health.py --root . --strict-release
python -m compileall -q nostalgia1907.py tools tests work
python -m unittest discover -s tests -v
python tools/style_audit.py --root .
python -m black --check nostalgia1907.py tools tests work/clean_rebuild work/region_variant
python nostalgia1907.py validate
```

Then verify that `git diff -- work/clean_rebuild/sources` contains only the
intended canonical records, and that no BIN, CUE, ISO, WAV, extracted archive,
or generated comparison package is staged.

A contributor without retail media can still run every source-only command and
the synthetic renderer/region tests. The retail-backed validator, deterministic
build, and Ares playtest must be completed by a maintainer before release; a
green public CI run is not visual-runtime evidence.

Documentation is part of the implementation. New or changed Python callables
must describe their contract at the level required by
`docs/DOCSTRING_STANDARD.md`, including non-obvious assumptions, side effects,
and expected failures. Comments should explain preservation or design
decisions, not translate individual Python statements into English.

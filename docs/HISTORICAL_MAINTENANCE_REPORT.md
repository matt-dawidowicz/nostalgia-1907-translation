# Historical maintenance, verification, rollback, and cleanup report

Date: 2026-08-02

Comparison base: commit `a2fca0c` (`Publish revised translation and tooling`)

Retained candidate: North American maintenance reference

Architectural baseline: validated clean-rebuild architecture

> Historical status: this report records the maintenance decision made on the
> date above. Its then-pending runtime questions were subsequently addressed by
> the full maintainer Ares playtest of the hash-identified North American
> reference. Version 1.0.2 remains the latest runtime-certified published
> reference, while the current source tree contains a later translation
> revision that still requires fresh runtime evidence. Use [release
> policy](RELEASE.md) and [the 2026-08-27 revision
> record](TRANSLATION_REVISION_20260827.md) for current status.

## Release decision

The maintenance reference was retained as the North American playtest
candidate. A later renderer experiment produced additional runtime layout
regressions during manual testing. Its source experiment and generated image
were therefore retired rather than promoted. Nothing in this maintenance state
depends on the rejected experiment, and none of its BIN/CUE or run directories
is retained.

This decision did not declare the maintenance reference a final release. Manual
testing established that the stale-letter clearing problem and the earlier
leading-indentation problem were fixed, while some inter-word/apostrophe-adjacent spacing still needed
runtime review. Static success is not being presented as proof that
every scene is visually final.

North America remains the default region for all new normal builds. The
Japanese-region output is available only through the explicit
`--region japan` diagnostic override.

## Retained-candidate provenance and hashes

Before removing older artifacts, the maintained source was compared with the
input records embedded in the retained candidate's clean-delivery verification
manifest. All 52 workspace source, configuration, production, and validation
files checked in that comparison matched byte-for-byte. The full
retained-candidate input manifest records 115 files after original-disc and
prepared-retail fixtures are included.

| Evidence | Value |
| --- | --- |
| Aggregate clean-build input fingerprint | `9F065F96122C9D15B2D86718142D5EC6BB0E205A3329CAD5E181A7C6890B3827` |
| Independent clean builds | 2; byte-identical |
| Clean artifacts compared | 48 |
| Independent North American wrappers | 2; byte-identical |
| Clean logical ISO SHA-256 | `28AC56F89E53B3891A3B9CE805DCBBD149932DB888B0FE2E1819CAD8E87EF606` |
| North American logical ISO SHA-256 | `E6DDFC9CD0A1877E208FA5DF541F5719015E7245FE61BDD87C4121F117BD8C12` |
| North American Track 1 SHA-256 | `386461E409E391FF78A81C21533708D01E3AEB9242214D9998BDC307DDC321A1` |
| Track 2 SHA-256 | `F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991` |
| North American CUE SHA-256 | `CCFBDD75FF464DD57B06CBD32B5263BD794BE8059019E19E3F5172B42BAEE9BE` |

The North American wrapper changes only raw sectors 0 through 4, preserves the
relocated original boot payload exactly, leaves all later raw sectors and Track
2 byte-identical, and does not alter translation records, SCN data, ISO files,
or file extents.

## Canonical translation changes since `a2fca0c`

The canonical inventory remains 19 chapters, 2,905 records, 2,882 translated
records, and 23 deliberately preserved records. IDs, order, policies, control
codes, and binary boundaries are unchanged.

Exactly 377 translated record texts changed:

- 369 records adopted the compact ellipsis rule. A pause is written as
  `...word`, not `... word`; capitalization is retained only for names,
  acronyms, `I` forms, titles, quoted text, and other reviewed exceptions.
- Eight records received reviewed wording changes:

| Record | Previous text | Current text |
| --- | --- | --- |
| `PART1A:017` | `Hee hee, you may be tough. But I am lucky.` | `Heh. You may be tough, but I'm lucky.` |
| `PART1A:024` | `Let us do it!` | `Let's do it!` |
| `PART2E:133` | `Cut upper red wire.` | `Cut the upper red wire.` |
| `PART2E:150` | `Cut lower blue wire.` | `Cut the lower blue wire.` |
| `PART2E:212` | `Set the cutters around the red wire... Cut.` | `I've got the cutters on the red wire...I'm cutting it.` |
| `PART2E:213` | `Wire cutters on blue wire... Cut.` | `I've got the cutters on the blue wire...I'm cutting it.` |
| `PART4B:171` | `Cut upper red wire.` | `Cut the upper red wire.` |
| `PART4B:195` | `Cut lower blue wire.` | `Cut the lower blue wire.` |

Text-change counts by chapter are recorded here so future reviews can reconcile
the change without relying on a generated diff:

| Chapter | Changed records | Chapter | Changed records |
| --- | ---: | --- | ---: |
| PART1A | 13 | PART1B | 1 |
| PART1C | 22 | PART1D | 18 |
| PART2A | 13 | PART2B | 11 |
| PART2C | 17 | PART2D | 20 |
| PART2E | 44 | PART2F | 14 |
| PART3A | 42 | PART3B | 26 |
| PART3B_ | 40 | PART3C | 29 |
| PART4A | 3 | PART4B | 58 |
| PART4C | 6 | Total | 377 |

## Renderer and compiler changes

The lower-dialogue fix is shared renderer logic, not a prologue-specific or
chapter-specific patch:

- SCN-derived layout now distinguishes physical runtime cells from prose-visible
  cells and validates all geometry before compilation.
- The lower box follows its native repeating 12/11/11-cell row cadence.
- Retail main dialogue can carry one initial Japanese opening-quote cell. The
  English compiler replaces that one cell with the shared blank fixed cell.
- That gutter anchor is emitted once for the dialogue stream. Page transitions
  do not emit another blank cell, so later pages keep their complete first-row
  stride.
- Other prose boxes use their own SCN-derived geometry and do not inherit the
  dialogue gutter.
- Renderer-boundary audits reject split words, row overflow, invalid geometry,
  and a source character shifted into an unintended leading blank.
- Compact ellipses use a dedicated deterministic renderer rule and are guarded
  both in canonical sources and repair-table application.
- JSON source updates are transactional: duplicate keys, staging failures,
  replacement failures, serialization failures, and rollback failures are
  tested explicitly.

## Build, region, and verification hardening

- `nostalgia1907.py build` now defaults to `north-america` from project policy.
- The normal North American build performs two independent clean builds,
  verifies their artifact hashes and input fingerprints, then performs two
  independent guarded region wrappers before publishing.
- `--region japan` is the explicit unwrapped diagnostic path.
- `build-us` remains for a hash-locked older baseline and now verifies the exact
  expected source Track 1 before wrapping.
- Build/run/output roots reject equality, nesting, occupied destinations,
  invalid basenames, and path collisions before publication.
- `verification_manifest.py` fingerprints declared canonical sources, retail
  fixtures, production and validation code, configuration, original tracks,
  normalized command/profile, and runtime identity.
- Reports name and rehash every expected output directly, reject stale or extra
  product files, and bind human-readable verification to the same machine
  manifest and aggregate input fingerprint.
- MES reports use build-relative paths, allowing clean builds in different
  roots to remain byte-identical.

## Review and source-tree hardening

- The bilingual comparison exporter now uses a deterministic standard-library
  PNG and ZIP implementation. Fresh staging, an exact expected inventory,
  fixed metadata, member hashes, and sidecar validation prevent stale files
  from contaminating a package. Pillow is no longer a production dependency.
- Fixed-layout records have a separate evidence queue that explicitly avoids
  claiming runtime geometry from static previews.
- Translation proposals are evidence-only and cannot silently edit canonical
  JSON. The empty queue works without retail media.
- ISO and MES parsers gained strict bounds, duplicate-record, padding,
  terminator, and extent validation.
- `tools/source_health.py` enforces UTF-8/LF text hygiene, strict JSON keys,
  parseable maintained source, and a media-free source checkout. Its strict
  release mode audits the exact Git-tracked or unpacked-package inventory so
  ignored directory names cannot conceal retail media, local configuration,
  screenshots, or emulator states. It uses the standard-library TOML parser on
  Python 3.11+ and the conditional `tomli` backport on Python 3.10.
- New focused test modules cover build reports, comparison determinism,
  ellipsis style, renderer boundaries, review exports, source health, and
  verification-manifest binding.

## Cleanup performed

The cleanup was intentionally split between generated delivery state and the
maintained Git checkout. Required original Japanese tracks, the prepared retail
reference, canonical sources, tests, and retained-candidate provenance were preserved.

- The active delivery workspace removed the rejected renderer experiment,
  obsolete earlier delivery copies and run directories, a forgotten retry
  directory, and obsolete build logs. Only the retained North American
  delivery and its provenance remain there.
- The Git checkout removed 13 ignored legacy output/run directories, 175 loose
  ignored generated media files, three ignored generated build/dump trees, and
  three empty probe directories. This removed 5,844,392,056 bytes from that
  checkout before the final validation run.
- The final validation's generated comparison, audit, build, and Python cache
  directories were removed again after their results were captured.
- No tracked BIN, CUE, ISO, MES, SCN, LZ, FNT, PCM, WAV, or PNG file remains in
  the source checkout. Original and rebuilt media remain protected by
  `.gitignore`.

These local deletions were permanent filesystem removals, not Recycle Bin
operations. They do not appear as Git deletions because every removed artifact
was already ignored and untracked.

## Verification captured for this maintenance state

The following checks completed successfully with CPython 3.12.13 on Windows:

| Check | Result |
| --- | --- |
| Source-health audit | PASS; 201 files checked, zero forbidden media or failures |
| Python static compilation | PASS |
| Maintained unit-test discovery | PASS; 95 tests |
| Operator `doctor` | PASS for Python, canonical inventory, both original tracks, and prepared retail reference; optional BIOS skipped because not configured |
| Full `validate` command | PASS |
| Renderer-aware corpus audit | PASS; 2,759 adaptive and 123 fixed records, zero failures/warnings/legacy issues |
| Script-layout suite inside validation | PASS; 13 tests |
| Deterministic comparison package | PASS; 2,905 images and 2,928 exact package members |
| Semantic/generated-artifact validation | PASS; zero failures |

The project maintainer subsequently playtested the byte-identical
runtime-reviewed reference in Ares, including the targeted dialogue renderer,
page advances, and dialogue transitions, with no defect reported in the tested
coverage. Static and deterministic checks protect the build contract; they do
not expand that recorded coverage into a whole-game certification.

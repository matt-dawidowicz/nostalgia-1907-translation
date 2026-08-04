# Nostalgia 1907 English translation

Nostalgia 1907 is a Japanese Mega-CD adventure game. This repository is the
source-only preservation and fan-translation project that rebuilds its English
script from a verified original disc. It is intended to be understandable and
maintainable by a future translator, reverse engineer, or preservation-minded
contributor - not just by the people who worked through the original defects.

The repository contains reviewed English records, deterministic build tools,
format documentation, automated checks, and playtest procedures. It does
**not** contain a playable disc image, BIOS, original game files, extracted
assets, or generated build products.

## What the project is now

The project has a single supported workflow:

```text
doctor -> prepare -> edit/compare -> validate -> build -> Ares playtest
```

It rebuilds from the original Japanese Track 1 and Track 2 supplied locally by
the user. The translation source is organized as 19 canonical chapter files
with 2,905 stable records: 2,883 translated records and 22 deliberately
preserved records. Record IDs, order, Japanese source data, SCN/control bytes,
disc boundaries, and the original audio track are protected by validation.

North America is the default build region. The normal build name is deliberately
neutral and stable:

```text
Nostalgia1907_CleanRebuild_NorthAmerica
```

It has no version suffix. A Japanese-region build remains an explicit
diagnostic option; a European build is not currently supported or claimed.

## Development history

This project reached its current form through several distinct phases. The
important lesson is that English wording, text storage, and the game's native
renderers cannot be treated as independent problems.

### 1. From disc archaeology to a reproducible source tree

Early work identified the binary layers needed to rebuild the game without
depending on a previously translated disc: raw MODE1/2352 sectors, ISO 9660,
chapter LZ archives, MES script containers, font cells, and SCN renderer
commands. The project then separated these concerns into small modules and
made the original Japanese disc the only binary authority.

Canonical English was moved into ID-keyed JSON chapter files. Generated MES,
LZ, ISO, BIN/CUE, previews, reports, and temporary extracted data were made
disposable. This is why a future contributor edits a canonical record instead
of hex-editing a disc image.

### 2. The first shared renderer model

English exposed layout behavior that Japanese text did not make obvious. The
initial clean-rebuild work established that there are several renderer classes,
not one universal text box. In particular, lower dialogue, speaker labels,
fixed overlays, compact labels, floating windows, and a small number of anchor
records have different contracts.

The project therefore derived layout from SCN structure and preserved fixed
records where no safe general reflow rule had been proven. The formatter and
compiler share those contracts so a preview and a build use the same geometry.

### 3. The v26 maintenance baseline and rejected experiment

The v26 maintenance pass established North America as the normal build target,
proved two clean rebuilds and two North American wrappers byte-identical, and
removed obsolete generated images. It also fixed stale-letter clearing and an
earlier leading-indentation defect.

An experimental v27 change then introduced runtime layout regressions. It was
retired rather than promoted. This was a useful discipline point: a static
check or a promising local patch is never enough to override observed emulator
behavior. The complete evidence and decision are retained in
[the v26 maintenance report](docs/V26_MAINTENANCE_REPORT.md).

### 4. Runtime-led dialogue repair

Subsequent Ares playtesting found recurring lower-box defects: a visible
leading shift, split words at renderer row boundaries, inappropriate spacing
around ellipses, and incorrect continuation behavior after page advances.

The solution was not a collection of chapter-specific rewrites. The shared
formatter/compiler logic now:

- validates SCN-derived cell geometry before compiling;
- distinguishes physical runtime cells from prose-visible cells;
- applies the lower dialogue renderer's native 12/11/11 cell cadence;
- emits a single blank anchor only when the retail dialogue stream requires it;
- keeps continuation pages free of a second anchor;
- rejects row overflow, broken words, and unintended leading blanks; and
- handles compact ellipses as a shared formatting rule.

This was the decisive change: translation entries remain semantic English,
while renderer-aware code chooses safe rows. Future renderer fixes should be
shared and evidence-led, never speculative chapter patches.

### 5. Current verified candidate and public-source cleanup

The historical North American candidate
`Nostalgia1907_CleanRebuild_v33_EdgeCases_NorthAmerica` is the current
runtime-reviewed reference. It was produced by two independent byte-identical
clean builds followed by two independent byte-identical North American region
builds. Its Track 1 SHA-256 is
`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17` and
its unchanged Track 2 SHA-256 is
`F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991`.

After the runtime work, the repository was prepared for public collaboration:
obsolete forensic workspaces and generated recovery products were removed,
their retirement is recorded in
[`retired_workspace_register.json`](work/clean_rebuild/retired_workspace_register.json),
the active code was documented to PEP 257 standards, and source health/style
checks were added. Historical candidate labels remain only as evidence; new
build output uses the neutral name above.

## What is proven, and what is not

The automated build gate proves input hashes, canonical-source validation,
deterministic clean reconstruction, deterministic North American wrapping,
fixed binary boundaries, exact Track 2 preservation, and direct hashes for the
published artifacts.

It does **not** prove that every scene, branch, or text box has been played in
an emulator. The current candidate passed targeted Ares checks of the dialogue
renderer, including page advances and transitions. A whole-game playthrough
remains a separate, explicit task. See [release and playtest policy](docs/RELEASE.md)
and [whole-game testing](docs/WHOLE_GAME_TESTING.md).

## Start here

Read these documents in order:

1. [Architecture](docs/ARCHITECTURE.md) - authoritative inputs, module
   boundaries, and the rebuild graph.
2. [Translation editing](docs/TRANSLATION_EDITING.md) - safe ID-keyed English
   changes and record policies.
3. [Text-box contracts](docs/TEXT_BOX_CONTRACTS.md) - the renderer categories
   and formatting responsibilities.
4. [Development and validation](docs/DEVELOPMENT.md) - commands and test
   layers.
5. [Binary formats](docs/BINARY_FORMATS.md) - MES, LZ, ISO, raw CD, font, and
   SCN boundaries.
6. [Adaptive renderer assessment](docs/ADAPTIVE_RENDERER_ASSESSMENT.md) - why
   the project retains the native renderer instead of inventing a new one.

For contribution rules and required checks, read
[CONTRIBUTING.md](CONTRIBUTING.md). For Python docstrings and inline comments,
use [the documentation standard](docs/DOCSTRING_STANDARD.md).

## Quick start

Use Python 3.10 or newer. From a fresh Windows clone:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Provide legally obtained Japanese Track 1 and Track 2, plus the verified U.S.
BIOS for a North American build, through the ignored
`nostalgia1907.local.json` file:

```json
{
  "track1": "D:/Games/Nostalgia 1907/Nostalgia 1907 (Japan) (Track 1).bin",
  "track2": "D:/Games/Nostalgia 1907/Nostalgia 1907 (Japan) (Track 2).bin",
  "us_bios": "D:/Emulation/Sega CD (U) - Model 2 v2.00w (1993).bin"
}
```

Then prepare and check the local retail reference:

```powershell
python nostalgia1907.py doctor
python nostalgia1907.py prepare
python nostalgia1907.py validate
```

To inspect a neutral North American build plan without creating files:

```powershell
python nostalgia1907.py build --dry-run
```

The actual build refuses nonempty staging or delivery directories. After it
passes, play the generated CUE in Ares and complete the relevant runtime checks
before publishing anything.

## Making a safe change

Canonical translation lives in
`work/clean_rebuild/sources/<CHAPTER>.json` under stable `CHAPTER:NNN` record
IDs. Do not edit compiled MES/LZ/ISO/BIN/CUE data, and do not use screenshots
as sufficient evidence for a renderer change.

Preview a wording change first, then apply it only after review:

```powershell
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording"
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording" --apply
python nostalgia1907.py validate
```

The safe escalation path is:

1. Correct source wording in the canonical record when the issue is wording.
2. Correct a shared SCN-derived layout or compiler rule when the issue repeats
   across the same renderer type.
3. Add a regression test and run the full validator.
4. Build in a fresh staging directory.
5. Reproduce the affected scene in Ares, including page advances and dialogue
   transitions.

Preserve Japanese records, IDs, record order, policy fields, SCN/control bytes,
file extents, and Track 2 exactly.

## Repository map

| Path | Purpose |
| --- | --- |
| `nostalgia1907.py` | Supported command-line entry point and safety preflight. |
| `nostalgia1907.project.json` | Project policy, hash guards, and source inventory. |
| `work/clean_rebuild/sources/` | Canonical per-chapter English records. |
| `work/clean_rebuild/` | Compiler, formats, deterministic builders, and validators. |
| `work/region_variant/` | Guarded North American BIOS-security wrapper. |
| `work/audio_localization/` | Optional review-only audio tooling. |
| `tests/` | Source-only CLI, policy, documentation, and regression tests. |
| `tools/` | Source-health and style audits. |
| `docs/` | Architecture, contributor, format, testing, and release guides. |
| `outputs/` | Ignored local reports, comparisons, and playable products. |

## License and game materials

Contributor-created code and documentation are under the
[MIT License](LICENSE). That license does not grant rights to the original
game, its assets, story, characters, text, music, trademarks, or BIOS. See
[THIRD_PARTY_NOTICE.md](THIRD_PARTY_NOTICE.md).

Contributors must supply their own legally obtained game files and must not
commit a BIOS, retail image, rebuilt image, extracted game media, or generated
playable product to this repository.

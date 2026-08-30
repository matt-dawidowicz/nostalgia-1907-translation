# Nostalgia 1907 English translation

This repository is the source-only English fan-translation and preservation
project for **Nostalgia 1907**, a Japanese Mega-CD adventure game. It contains
the reviewed English corpus, deterministic rebuild tooling, binary-format
validation, source checks, and runtime-test procedures needed to reproduce a
candidate from legally obtained original media.

It does **not** contain a game image, BIOS, extracted retail assets, generated
BIN/CUE files, screenshots, or other copyrighted game media.

## Project status

The latest runtime-certified published reference remains **1.0.2**. Its exact
North American Track 1 completed a full maintainer Ares playthrough and is
identified by SHA-256:

`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`

The current source tree contains the later **2026-08-27 source-fidelity and
character-voice revision**. That revision re-audited the 2,905-record corpus and
changes playable bytes. It has source and retail-backed static validation, but
it does not inherit the 1.0.2 runtime certification. A fresh deterministic
candidate and candidate-bound Ares playthrough are still required before it can
become a successor release.

See [the revision record](docs/TRANSLATION_REVISION_20260827.md) and
[release policy](docs/RELEASE.md) for the exact evidence boundary.

## Supported workflow

Normal work uses one operator-facing command surface:

```text
doctor -> prepare -> edit/compare -> validate -> build -> Ares playtest
```

- `doctor` checks Python, source identity, and configured local inputs.
- `prepare` verifies the original Japanese Track 1 and creates an ignored,
  hash-locked retail reference.
- `edit` previews or applies an English change by stable record ID.
- `compare` regenerates the bilingual human-review package.
- `validate` runs source, renderer, semantic, compilation, and retail-backed
  regression gates.
- `build` performs two independent clean rebuilds and, by default, two guarded
  North American region-wrapper runs before publication.
- Ares playtesting remains the final gate for behavior static analysis cannot
  prove.

North America is the default build target. Japan is an explicit diagnostic
option. Europe is not currently supported.

## Quick start

Use Python 3.10 or newer. From a fresh clone:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Put machine-specific paths only in the ignored `nostalgia1907.local.json`:

```json
{
  "track1": "D:/path/to/Nostalgia 1907 (Japan) (Track 1).bin",
  "track2": "D:/path/to/Nostalgia 1907 (Japan) (Track 2).bin",
  "us_bios": "D:/path/to/verified-us-sega-cd-bios.bin"
}
```

Then:

```powershell
python nostalgia1907.py doctor
python nostalgia1907.py prepare
python nostalgia1907.py validate
python nostalgia1907.py build --dry-run
```

The real build refuses occupied or overlapping staging/delivery roots. Do not
weaken an input hash or boundary check to accept a different retail revision.

## Source-only development

No game media is needed for the public source checks:

```powershell
python tools/source_health.py --root . --strict-release
python tools/source_manifest.py --root .
python -m compileall -q nostalgia1907.py tools tests work
python -m unittest discover -s tests -v
python tools/style_audit.py --root .
```

`MANIFEST.sha256` is the deterministic inventory for the source-only review
bundle. Regenerate it only after intentional tracked-source changes:

```powershell
python tools/source_manifest.py --root . --write
```

CI verifies the manifest, so a source change cannot leave the review inventory
silently stale.

## Translation source

Canonical English lives under `work/clean_rebuild/sources/` as 19 chapter files
containing 2,905 stable records. The build never discovers a record by matching
mutable English text. Record IDs, order, preserve/translate policy, retail
MES/SCN identity, and renderer ownership are checked independently.

Preview before applying a wording change:

```powershell
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording"
python nostalgia1907.py edit PART1A:003 --text "Reviewed wording" --apply
python nostalgia1907.py validate
```

Preserve Japanese records, stable IDs, record order, SCN/control bytes, archive
member order, ISO extents, Track 2, and the distinction between semantic English
and generated wrapping.

## Renderer and binary safety

The game has multiple native text renderers. The project derives roles and
geometry from original SCN structure and shares that contract between preview
and compilation. Adaptive records store semantic English; fixed records retain
reviewer-owned spacing where safe general reflow has not been proven.

The rebuild also preserves the original binary envelope: MES record structure,
archive allocations, fixed ISO extents, raw MODE1/2352 geometry, and Track 2.
Deterministic hashes and static regression prove those boundaries, but they do
not prove on-screen clearing, timing, transitions, branch behavior, or emulator
compatibility. Those remain runtime-test responsibilities.

## Repository map

| Path | Purpose |
| --- | --- |
| `nostalgia1907.py` | Supported CLI and safety preflight |
| `nostalgia1907.project.json` | Frozen project policy, hashes, paths, corpus counts |
| `work/clean_rebuild/sources/` | Canonical English records |
| `work/clean_rebuild/` | Active compiler, formats, builders, validators, review helpers |
| `work/region_variant/` | Guarded North American security/region wrapper |
| `provenance/2026-08-27/` | Reviewed change ledgers for the post-1.0.2 revision |
| `tests/` | Source-only, synthetic, and regression tests |
| `tools/` | Source health, manifest, and style audits |
| `docs/` | Architecture, formats, editing, testing, and release policy |
| `outputs/` | Ignored generated reports and build products |

Historical reverse-engineering outcomes are retained as documentation or small
declarative provenance records. One-off applicators, forensic decoders,
intermediate snapshots, and ad-hoc capacity/report scripts are intentionally not
part of the maintained code surface.

## Read next

1. [Getting started](docs/GETTING_STARTED.md)
2. [Architecture](docs/ARCHITECTURE.md)
3. [Translation editing](docs/TRANSLATION_EDITING.md)
4. [Text-box contracts](docs/TEXT_BOX_CONTRACTS.md)
5. [Development and validation](docs/DEVELOPMENT.md)
6. [Binary formats](docs/BINARY_FORMATS.md)
7. [Whole-game testing](docs/WHOLE_GAME_TESTING.md)
8. [Release policy](docs/RELEASE.md)

For contribution requirements, read [CONTRIBUTING.md](CONTRIBUTING.md). Python
callables and explanatory comments follow
[the documentation standard](docs/DOCSTRING_STANDARD.md).

## AI assistance and responsibility

AI tools, including ChatGPT and Codex, were used substantially for translation
comparison, code generation/refactoring, documentation, test design, and
reverse-engineering analysis. Their output was not treated as evidence by
itself. Accepted changes were reviewed against source context, deterministic
checks, binary boundaries, and observed emulator behavior where runtime claims
were involved. The maintainer remains responsible for the accepted English,
code, documentation, release claims, and remaining errors.

## Licensing and third-party materials

Contributor-created code, tests, and technical documentation are licensed under
the [MIT License](LICENSE). Reviewed English translation contributions are
licensed under [CC BY-NC-SA 4.0](LICENSE-TRANSLATION.md).

Those licenses apply only to rights held by project contributors. They do not
grant rights to the original game, Japanese script, music, artwork, trademarks,
or BIOS. See [THIRD_PARTY_NOTICE.md](THIRD_PARTY_NOTICE.md).

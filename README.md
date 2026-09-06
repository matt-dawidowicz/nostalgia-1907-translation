# Nostalgia 1907 English translation

This repository is the source-only English fan-translation and preservation
project for **Nostalgia 1907**, a Japanese Mega-CD adventure game. It contains
the reviewed English corpus, deterministic rebuild tooling, binary-format
validation, source checks, and runtime-test procedures needed to reproduce a
candidate from legally obtained original media.

It does **not** contain a game image, BIOS, extracted retail assets, generated
BIN/CUE files, screenshots, or other copyrighted game media.

## Project status

Version **1.0.2** remains the latest runtime-certified published reference. Its
North American Track 1 completed the recorded full maintainer Ares playthrough
and is identified by SHA-256:

`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`

The maintained source is now the cumulative post-1.0.2 successor line, not only
the original 2026-08-27 revision. It includes the full-corpus source-fidelity
and voice work, the September complete-script audit, renderer/runtime fixes,
fixed-layout and script-integrity hardening, STAFF credit corrections and
centering, build/repository hardening, and deterministic performance work.
Those changes include playable-byte changes, so the source does **not** inherit
the 1.0.2 runtime certification.

The canonical corpus is 19 chapters / 2,905 records: 2,883 translated and 22
deliberately preserved. Public source CI is green for the maintained source
contract, but a successor release still requires a fresh deterministic build
and a candidate-bound Ares certification tied to the exact final hashes.

Read [current project status](docs/CURRENT_STATUS.md) before using dated revision
reports as evidence. See [release policy](docs/RELEASE.md) for the publication
boundary.

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
- `validate` runs the maintained source gate plus renderer, semantic,
  compilation, archive, and retail-backed regression checks.
- `build` performs two independent clean rebuilds and, by default, two guarded
  North American region-wrapper runs before publication.
- Ares playtesting remains the final gate for behavior static analysis cannot
  prove.

North America is the default build target. Japan is an explicit diagnostic
option. Europe is not currently supported.

## Quick start

Use Python 3.12 or newer. From a fresh clone:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
# The toolchain runs directly from this checkout; no project install is required.
```

The production and operator tooling has no third-party runtime dependencies.
Contributors who run source-quality checks install the repository-local
development requirements:

```powershell
python -m pip install -r requirements-dev.txt
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

No game media is needed for the public source contract:

```powershell
python -m tools.source_checks --root . --strict-release
```

That single command owns the maintained source-health, manifest, production
boundary, compilation, unit-test, Ruff-format, Ruff-lint, mypy, and public-API
documentation checks. CI runs the complete gate on Ubuntu/Python 3.12 and
Windows/Python 3.14, with additional Python 3.13/3.14 compatibility coverage on
Ubuntu.

`MANIFEST.sha256` is the deterministic inventory for the source-only review
bundle. Regenerate it only after intentional tracked-source changes:

```powershell
python tools/source_manifest.py --root . --write
```

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

Preserve Japanese records, stable IDs, record order, archive member order, ISO
extents, Track 2, and the distinction between semantic English and generated
wrapping. Retail SCN remains the structural authority; the generated game has
one separately hash-locked, runtime-reviewed two-byte PART1A selector-coordinate
correction documented in `scn_patch.py`.

## Renderer and binary safety

The game has multiple native text renderers. The project derives roles and
geometry from original SCN structure and shares that contract between preview
and compilation. Adaptive records store semantic English; fixed records retain
reviewer-owned spacing where safe general reflow has not been proven.

The rebuild preserves the original binary envelope: MES record structure,
archive allocations, fixed ISO extents, raw MODE1/2352 geometry, and Track 2.
Authenticated unchanged raw sectors may be reused byte-for-byte; changed sectors
receive regenerated EDC/ECC and are checked directly. Deterministic hashes and
static regression prove those boundaries, but they do not prove on-screen
clearing, timing, transitions, branch behavior, or emulator compatibility.
Those remain runtime-test responsibilities.

## Repository map

| Path | Purpose |
| --- | --- |
| `nostalgia1907.py` | Supported CLI and safety preflight |
| `nostalgia1907.project.json` | Frozen project policy, hashes, paths, corpus counts |
| `work/clean_rebuild/sources/` | Canonical English records |
| `work/clean_rebuild/` | Active compiler, formats, builders, validators, review helpers |
| `work/region_variant/` | Guarded North American security/region wrapper |
| `provenance/` | Dated reviewed-change ledgers; never build inputs |
| `tests/` | Source-only, synthetic, integration, and regression tests |
| `tools/` | Unified source gate, repository inventory/health, manifest, and documentation audit |
| `docs/` | Current status, architecture, formats, editing, testing, historical revision, and release policy |
| `outputs/` | Ignored generated reports and build products |

Historical reverse-engineering outcomes are retained as documentation or small
declarative provenance records. One-off applicators, forensic decoders,
intermediate snapshots, and ad-hoc capacity/report scripts are intentionally not
part of the maintained code surface.

## Read next

1. [Current project status](docs/CURRENT_STATUS.md)
2. [Getting started](docs/GETTING_STARTED.md)
3. [Architecture](docs/ARCHITECTURE.md)
4. [Translation editing](docs/TRANSLATION_EDITING.md)
5. [Text-box contracts](docs/TEXT_BOX_CONTRACTS.md)
6. [Development and validation](docs/DEVELOPMENT.md)
7. [Binary formats](docs/BINARY_FORMATS.md)
8. [Whole-game testing](docs/WHOLE_GAME_TESTING.md)
9. [Release policy](docs/RELEASE.md)

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

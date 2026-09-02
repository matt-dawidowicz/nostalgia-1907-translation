# Architecture

## Trust model

Nostalgia 1907 is rebuilt from verified Japanese retail media plus tracked
translation source. A previously translated disc, generated MES/LZ files, or a
runtime-reviewed BIN is never a build input.

The repository has three trust classes:

| Class | Examples | Authority |
| --- | --- | --- |
| Retail input | Japanese Track 1/2, extracted MES/SCN | Read-only binary and structural authority |
| Canonical source | `work/clean_rebuild/sources/*.json`, glossary and layout policy | Human-reviewed English and translation policy |
| Generated output | MES, LZ, ISO, BIN/CUE, reports and review packages | Disposable products that must be reproducible |

Version 1.0.2 remains the latest runtime-certified published reference. The
current source tree contains the later 2026-08-27 translation revision, which
changes playable bytes and therefore requires fresh candidate-bound runtime
evidence before it can supersede 1.0.2. See
[the revision record](TRANSLATION_REVISION_20260827.md) and
[release policy](RELEASE.md).

## Supported flow

Normal work goes through the top-level CLI:

```text
doctor -> prepare -> edit/compare -> validate -> build -> runtime test
```

`nostalgia1907.py` owns operator-facing path resolution, input guards, command
composition, and safe error reporting. `nostalgia1907.project.json` owns the
frozen project contract: retail hashes, corpus counts, default region, and
repository-relative paths.

The build path is deliberately staged:

1. `prepare_retail.py` verifies Track 1 and derives a hash-locked retail
   reference.
2. `mes_compiler.py` combines canonical English with the original MES/SCN
   structure and shared renderer rules.
3. `build_archives.py` replaces MES members within guarded archive capacity and
   installs the single hash-locked `PART1A.SCN` selector-coordinate correction.
4. `iso9660.py`, `main_patch.py`, `scn_patch.py`, and `font_render.py` create the logical disc
   payload without relocating unrelated files.
5. `raw_cd.py` reconstructs MODE1/2352 Track 1 and copies Track 2 exactly.
6. `regression.py` checks cross-layer preservation invariants.
7. `verification_manifest.py` binds declared inputs and direct output hashes.
8. `rebuild.py` repeats the clean build independently and publishes only when
   both runs agree.
9. The North American wrapper under `work/region_variant/` repeats its guarded
   region stage independently before publication.

## Repository boundaries

| Path | Responsibility |
| --- | --- |
| `nostalgia1907.py` | Supported operator CLI and preflight |
| `nostalgia1907.project.json` | Project policy, hashes, corpus counts, paths |
| `work/clean_rebuild/sources/` | Canonical per-chapter translation records |
| `work/clean_rebuild/` | `work.clean_rebuild` package: compiler, binary formats, builders, validators, review helpers |
| `work/region_variant/` | `work.region_variant` package: guarded North American region wrapper |
| `provenance/2026-08-27/` | Historical reviewed-change ledgers; never a build input |
| `tests/` | Source-only and synthetic regression tests |
| `tools/` | Repository health, source-manifest, and style checks |
| `docs/` | Contributor, format, testing, revision, and release documentation |
| `outputs/` | Ignored generated reports, comparisons, and playable products |

Retired workspace names and completed one-off review queues are documented in
historical maintenance records rather than carried as active files under
`work/clean_rebuild/`.

`MANIFEST.sha256` describes the complete source-only review tree. The maintained
`tools/source_manifest.py` generator/checker makes that inventory reproducible
instead of relying on manual hash edits.

## Production module boundary

`work.clean_rebuild.rebuild` defines `PRODUCTION_MODULES`. That tuple is the exact
local Python allowlist for the byte-producing clean build. Package modules use
explicit relative sibling imports, and the production-independence audit rejects
a missing module, an import outside the allowlist, a deeper relative escape, a
canonical source path outside `sources/`, or a known historical-workspace marker.

Each production module has one primary responsibility:

| Module | Owns |
| --- | --- |
| `raw_cd.py` | MODE1/2352 sectors, EDC/ECC, CUE writing |
| `iso9660.py` | ISO directory records, extents, logical sizes |
| `lz_format.py` | Chapter archive parsing and compression |
| `mes_format.py` | MES parsing and structural validation |
| `source_json.py` | Strict UTF-8 JSON loading and duplicate-key rejection |
| `font_render.py` | Fixed and generated glyph bitmaps |
| `scn_layout.py` | SCN-derived renderer roles and geometry |
| `renderer_format.py` | Shared text normalization, wrapping, and row reconstruction |
| `profile_schema.py` | Chapter-profile schema and active/legacy field classification |
| `mes_compiler.py` | Canonical records to guarded MES bytes |
| `prepare_retail.py` | Exact retail verification and extraction |
| `build_mes_set.py` | Whole-corpus MES compilation and font assembly |
| `build_archives.py` | MES and guarded PART1A SCN installation within original archive allocation |
| `main_patch.py` | Frozen hash-guarded executable adjustment |
| `scn_patch.py` | Frozen two-byte PART1A Call/Fold selector alignment correction |
| `regression.py` | Cross-layer binary preservation proofs |
| `verification_manifest.py` | Input fingerprints and explicit output binding |
| `rebuild.py` | Orchestration, two-run determinism, publication |

Production code expresses general format or renderer rules. Chapter-specific
forensic experiments and one-time migration scripts do not belong in this
boundary.

## Validation and review boundary

Validation code is maintained separately from the byte-producing allowlist. The
supported `validate` path uses `translation_formatter.py`,
`translation_audit.py`, `translation_validation.py`, `bomb_audit.py`,
`export_bilingual_comparison.py`, and the retail-backed
`test_script_layout.py` suite. `export_fixed_layout_review.py` and
`whole_game_test.py` support runtime-evidence planning.

The completed translation-proposal compatibility shim was removed after the
queue reached zero. New canonical changes use the supported edit/validate/build
path instead; historical review outcomes remain under `docs/` and `provenance/`.

Public CI deliberately runs source-only checks without copyrighted retail
fixtures. Retail-backed layout, semantic, archive, deterministic-build, and
runtime gates remain maintainer operations with verified local inputs.

## Canonical source contract

`sources/index.json` fixes chapter order and per-chapter counts. Each chapter
contains a contiguous zero-based record table with an explicit translation
policy and layout ownership.

Important invariants are:

- stable `CHAPTER:NNN` IDs and record order;
- `policy: "translate"` versus `policy: "preserve"`;
- `layout_policy: "adaptive"` only where SCN proves safe renderer geometry;
- `layout_policy: "fixed"` where reviewers still own exact spacing;
- Japanese retail MES/SCN hashes as source-side guards; and
- no discovery by matching mutable English text.

SCN text IDs are one-based while canonical record indexes are zero-based. That
conversion is explicit and tested.

## Renderer ownership

The game has multiple text renderers. `scn_layout.py` classifies lower dialogue,
speaker labels, continuation rows, floating thoughts/overlays, compact labels,
choices, and reviewed narration cases from original SCN structure.

`translation_formatter.py` and `mes_compiler.py` share the public
`renderer_format.py` behavior. Adaptive source stores semantic English while the
compiler derives safe rows. Fixed source retains reviewer-controlled spacing.
The compiler repeats authoritative row/token checks before encoding so direct
low-level compilation cannot bypass the formatter's safety model.

Static geometry is not a runtime claim. Window clearing, transitions, timing,
branch behavior, and emulator-visible redraw still require candidate-bound
playtesting.

## Binary preservation boundaries

The build avoids relocating disc structures:

1. MES record count and order stay fixed.
2. Compiled MES data must fit pointer and runtime glyph limits.
3. LZ replacement uses the original member slot when possible and guarded
   reflow only inside the original archive allocation.
4. ISO file extents stay fixed; only declared payload bytes and logical sizes
   may change.
5. Raw Track 1 preserves sector count and non-user-data geometry.
6. Track 2 is copied byte-for-byte.
7. The North American wrapper modifies only its explicitly guarded boot/security
   region.

`regression.py` verifies these boundaries against the retail reference rather
than trusting a previous translated product.

## Determinism and cryptographic binding

A clean run fingerprints declared canonical source, retail fixtures, production
and validation code, configuration, original tracks, normalized command/build
profile, and runtime identity. The resulting **aggregate input fingerprint** is
recorded with explicit hashes for every managed output.

`verification_manifest.py` never discovers release products by an unrestricted
output glob. Expected artifacts are named, snapshotted, rehashed immediately
before report creation, and checked for missing or unexpected files. Two clean
runs must agree before publication; the region wrapper has its own independent
repeatability check.

This proves reproducibility and direct report-to-byte binding. It does not turn
static success into a **runtime claim**.

## Historical provenance policy

Historical outcomes belong in `docs/` or `provenance/`, not as executable
one-off scripts beside production code. Once a discovery is promoted, the
durable form is a general implementation rule plus a focused regression test.
Obsolete forensic decoders, migration applicators, ad-hoc capacity planners,
generated review-bundle scaffolding, and intermediate translation snapshots are
removed rather than kept on the maintained Python surface.

When promoting a new reverse-engineering discovery:

1. record the evidence and scope;
2. express the behavior as a general parser/renderer/build rule;
3. add malformed-input and regression coverage;
4. run complete affected-corpus validation; and
5. keep generated evidence outside tracked source.

## Where changes belong

| Goal | Primary location |
| --- | --- |
| Correct English wording | `sources/<CHAPTER>.json` via `nostalgia1907.py edit` |
| Lock a repeated term | Canonical records plus `translation_glossary.json` when required |
| Fix a renderer rule | `scn_layout.py` or shared `renderer_format.py`/compiler logic |
| Add a semantic invariant | `translation_validation.py` and its tracked rule data |
| Change MES parsing | `mes_format.py` |
| Change archive handling | `lz_format.py` / `build_archives.py` |
| Change ISO placement | `iso9660.py` |
| Change sector handling | `raw_cd.py` |
| Change orchestration | `rebuild.py`, with deterministic regression coverage |
| Change repository policy | top-level CLI/project manifest plus source-only tests |

A proposed fix that starts from one screenshot coordinate or one chapter name
should first be reduced to the underlying renderer, format, or canonical-source
rule. That is how the project avoids rebuilding another layer of historical
special cases.

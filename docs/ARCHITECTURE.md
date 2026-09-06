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
maintained source is the cumulative post-1.0.2 successor line described in
[`CURRENT_STATUS.md`](CURRENT_STATUS.md). Later translation, renderer/runtime,
STAFF-layout, hardening, and production-path changes mean that line requires its
own exact candidate-bound deterministic and Ares evidence before publication.

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
2. `mes_compiler.py` combines canonical English with original MES/SCN structure
   and shared renderer rules.
3. `build_archives.py` replaces MES members within guarded archive capacity and
   installs the single closed `PART1A.SCN` selector-coordinate correction.
4. `iso9660.py`, `main_patch.py`, `scn_patch.py`, and `font_render.py` construct
   the logical disc payload without relocating unrelated files.
5. `raw_cd.py` reconstructs changed MODE1/2352 sectors and reuses authenticated
   unchanged raw sectors byte-for-byte when legal; Track 2 is copied exactly.
6. `regression.py` checks cross-layer preservation invariants, preserved-record
   rendering identity, SCN-to-MES referential integrity, and raw-disc integrity.
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
| `work/clean_rebuild/` | Compiler, binary formats, builders, validators, review helpers |
| `work/region_variant/` | Guarded North American region wrapper |
| `provenance/` | Dated reviewed-change ledgers; never build inputs |
| `tests/` | Source-only, synthetic, integration, and regression tests |
| `tools/` | Unified source gate, repository inventory/health, manifest, documentation audit |
| `docs/` | Current status, architecture, formats, editing, testing, history, release policy |
| `outputs/` | Ignored generated reports, comparisons, and playable products |

`MANIFEST.sha256` describes the complete source-only review tree except itself.
`tools/source_manifest.py` renders and verifies it deterministically from the
tracked inventory supplied by `tools/repository_inventory.py`.

## Production module boundary

`work.clean_rebuild.rebuild` defines `PRODUCTION_MODULES`. That tuple is the exact
local Python allowlist for the byte-producing clean build. Package modules use
explicit relative sibling imports, and the production-independence audit rejects
a missing module, an import outside the allowlist, a deeper relative escape, a
canonical source path outside `sources/`, or a known historical-workspace marker.

Every production dependency is documented below:

| Module | Owns |
| --- | --- |
| `raw_cd.py` | MODE1/2352 sectors, EDC/ECC, authenticated unchanged-sector reuse, CUE writing |
| `iso9660.py` | ISO directory records, fixed extents, logical sizes |
| `lz_format.py` | Chapter archive parsing and deterministic compression |
| `mes_format.py` | MES parsing and structural validation |
| `source_json.py` | Strict UTF-8 JSON loading and duplicate-key rejection |
| `font_render.py` | Fixed and generated glyph bitmaps |
| `scn_layout.py` | Shared SCN display inventory, renderer roles, geometry, row limits |
| `script_integrity.py` | SCN-to-MES text-reference integrity and choice-branch inventory |
| `renderer_format.py` | Shared normalization, wrapping, and row reconstruction |
| `profile_schema.py` | Active fail-closed chapter-profile schema and rules |
| `mes_compiler.py` | Canonical records to guarded MES bytes |
| `prepare_retail.py` | Exact retail verification and extraction |
| `build_mes_set.py` | Whole-corpus MES compilation and font assembly |
| `build_archives.py` | MES and guarded PART1A SCN installation within original allocation |
| `main_patch.py` | Frozen hash-guarded executable adjustment |
| `scn_patch.py` | Frozen two-byte PART1A Call/Fold selector alignment correction |
| `regression.py` | Cross-layer binary preservation proofs |
| `verification_manifest.py` | Input fingerprints and explicit output binding |
| `rebuild.py` | Orchestration, two-run determinism, publication |

Production code expresses general format or renderer rules. Chapter-specific
forensic experiments and one-time migration scripts do not belong in this
boundary.

## Validation and review boundary

`tools/source_checks.py` is the one maintained source-only contract. It combines
source health, source-manifest identity, production-dependency policy,
maintained-Python compilation, source-only tests, Ruff format, Ruff lint, mypy,
and the public-API documentation audit.

Retail-backed validation remains separate because public CI cannot carry
copyrighted fixtures. The supported `nostalgia1907.py validate` path uses the
shared formatter/audits, compilation/archive/regression modules, bilingual
comparison exporter, semantic validation, and
`tests/test_script_layout_integration.py` after verified retail prerequisites are
available.

`export_fixed_layout_review.py` and `whole_game_test.py` support runtime-evidence
planning. Whole-game certification is fail-closed against incomplete static
summaries, candidate identity, generated route/text-box inventories, evidence
notes, and open runtime issues.

The old active translation-proposal machinery and retired profile-compatibility
switches have been removed. New canonical changes use the supported
edit/validate/build path; historical outcomes remain under `docs/` and
`provenance/`.

## Canonical source contract

`sources/index.json` fixes chapter order and per-chapter counts. The maintained
project contract is 19 chapters / 2,905 records, currently 2,883 translated and
22 deliberately preserved.

Important invariants are:

- stable `CHAPTER:NNN` IDs and record order;
- `policy: "translate"` versus `policy: "preserve"`;
- `layout_policy: "adaptive"` only where a shared renderer contract is proven;
- `layout_policy: "fixed"` where reviewer-owned physical layout remains
  authoritative;
- Japanese retail MES/SCN hashes as source-side guards; and
- no discovery by matching mutable English text.

SCN text IDs are one-based while canonical record indexes are zero-based. That
conversion is explicit and tested.

## Renderer ownership

The game has multiple text renderers. `scn_layout.py` builds one structural
inventory and derives lower dialogue, continuation rows, floating windows,
labels, choices, and reviewed exceptional roles from original SCN evidence.

`translation_formatter.py` and `mes_compiler.py` share
`renderer_format.py`. Adaptive source stores semantic English while the compiler
derives physical rows. Fixed source retains reviewer-controlled spacing. The
compiler repeats authoritative row/token checks before encoding so direct
low-level compilation cannot bypass preview safety.

Static geometry is not a runtime claim. Window clearing, transitions, timing,
branch behavior, and emulator-visible redraw still require candidate-bound
playtesting.

## Binary preservation boundaries

The build avoids relocating disc structures:

1. MES record count and order stay fixed.
2. Compiled MES data must fit pointer and runtime glyph limits.
3. Preserved MES records retain fixed/control semantics and identical rendered
   dynamic glyphs even if legal glyph-bank compaction renumbers references.
4. Proven SCN text references resolve to canonical MES records; translated
   records have proven SCN references or explicit reviewed renderer contracts.
5. LZ replacement uses original member slots when possible and guarded reflow
   only inside the original archive allocation.
6. ISO file extents stay fixed; only declared payload bytes and logical sizes
   may change.
7. Raw Track 1 preserves sector count, headers, addresses, mode, and geometry.
   Authenticated unchanged sectors may be reused exactly; changed sectors receive
   direct EDC/ECC regeneration and verification.
8. Track 2 is copied byte-for-byte.
9. The North American wrapper modifies only its explicitly guarded boot/security
   region.

`regression.py` verifies these boundaries against authenticated retail evidence,
not a previous translated product.

## Determinism and cryptographic binding

Game builds use **fresh output roots**. A clean run fingerprints declared
canonical source, retail fixtures, production and validation code,
configuration, original tracks, normalized command/build profile, and runtime
identity. The resulting **aggregate input fingerprint** is recorded with direct
hashes for managed outputs.

`verification_manifest.py` never discovers release products by an unrestricted
output glob. Expected artifacts are named, snapshotted, rehashed immediately
before report creation, and checked for missing/unexpected files. Two clean runs
must agree before publication; the region wrapper has its own independent
repeatability check.

The bilingual comparison package fixes member paths, ordering, ZIP metadata,
PNG generation, and text line endings. Its byte-identity guarantee is scoped to
the same input bytes, exporter source, and **CPython major/minor** runtime.

Determinism proves reproducibility. It does not convert static evidence into a
**runtime claim**.

## Historical provenance policy

Historical outcomes belong in `docs/` or `provenance/`, not as executable
one-off scripts beside production code. Dated reports must preserve their
historical measurements while clearly pointing readers to `CURRENT_STATUS.md`
for the present release boundary.

When promoting a reverse-engineering discovery:

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
| Add a semantic invariant | `translation_validation.py` and tracked rule data |
| Change MES parsing | `mes_format.py` |
| Change SCN reference/branch validation | `script_integrity.py` |
| Change archive handling | `lz_format.py` / `build_archives.py` |
| Change ISO placement | `iso9660.py` |
| Change sector handling | `raw_cd.py` |
| Change orchestration | `rebuild.py`, with deterministic regression coverage |
| Change repository policy | top-level CLI/project manifest plus source-only tests |

A proposed fix that starts from one screenshot coordinate or one chapter name
should first be reduced to the underlying renderer, format, or canonical-source
rule. That is how the project avoids rebuilding another layer of historical
special cases.

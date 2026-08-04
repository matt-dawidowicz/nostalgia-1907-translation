# Development and validation

## Environment

The supported runtime is Python 3.10 or newer. Install the repository in
editable mode:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

For a formatting pass, install the isolated style extra and run Black:

```powershell
python -m pip install -e ".[style]"
python -m black nostalgia1907.py tools tests work/clean_rebuild work/region_variant work/audio_localization
```

The supported production and comparison path uses only the Python standard
library. The `test` extra adds NumPy for the audio codec/synthesis companion
tests. Speech recognition and synthesis packages are isolated behind the audio
extras.

Machine-specific retail, BIOS, and FFmpeg paths belong in the ignored
`nostalgia1907.local.json`, never in tracked source.

## Command layers

Use `nostalgia1907.py` for normal work:

| Command | Reads | Writes | Purpose |
| --- | --- | --- | --- |
| `doctor` | manifest, config, input hashes | nothing | readiness diagnosis |
| `prepare` | original Track 1 | ignored retail reference | strict extraction |
| `edit` preview | source and retail SCN | nothing | renderer-aware proposal review |
| `edit --apply` | source and retail SCN | canonical chapter JSON | validated English edit |
| `compare` | source and retail reference | ignored comparison package | bilingual human review |
| `validate` | source, retail reference, comparison | ignored reports/comparison | complete automated gate |
| `build --dry-run` | hashes and path state | nothing | resolved build plan |
| `build` | original tracks, canonical source, U.S. BIOS | isolated clean/region runs and delivery | deterministic North American BIN/CUE by default |
| `build --region japan` | original tracks and canonical source | isolated runs and delivery | explicit unwrapped diagnostic build |

The lower-level modules are intentionally importable for focused analysis. Run
them directly only when you understand which higher-level preflight stages you
are bypassing.

## Validation layers

Validation is layered so a failure can be localized:

1. **Python compilation** catches syntax and import-time source mistakes.
2. **Source-only unit tests** cover CLI contracts, manifests, repository
   policy, documentation inventory, and the maintained-code style audit.
3. **Audio companion unit tests** cover the reversible PCM/WAV codec and SCN
   audio mapping without changing the game.
4. **Renderer audit** classifies every translated record and checks adaptive or
   fixed ownership.
5. **Layout tests** compile every chapter from hash-locked inputs and cover
   known renderer edge cases.
6. **Comparison regeneration** creates the complete Japanese/English review
   package.
7. **Semantic validation** checks source fingerprints, duplicate consistency,
   glossary rules, exemptions, bomb terminology, ID order, comparison
   freshness, and the package manifest against exact disk and ZIP inventories.
8. **Build regression** checks MES/font capacity, LZ contents, fixed ISO
   extents, unchanged ISO regions, raw sectors, Track 2, and CUE formatting.
9. **Two-run comparison** proves deterministic output.
10. **Manual playtesting** remains the release gate for visual and branching
    behavior.

For a reproducible complete-corpus static check plus an explicit runtime
certification log, use `docs/WHOLE_GAME_TESTING.md`. The log is candidate-hash
bound and remains pending until every declared chapter, box type, and runtime
state has human evidence.

## Generated reports

Useful ignored artifacts include:

| Artifact | Produced by | Use |
| --- | --- | --- |
| `retail_report.json` | `prepare_retail.py` | retail Track/ISO and extracted-member evidence |
| `script_layout_audit.json` | `translation_formatter.py` | per-ID role, width, rows, and failures |
| comparison JSON/HTML/images/ZIP plus `.manifest.json` | `export_bilingual_comparison.py` | Japanese/English review and exact package inventory |
| `fixed_layout_runtime_review.tsv` / `.md` | `export_fixed_layout_review.py` | all fixed records awaiting runtime geometry evidence |
| `translation_polish_proposals.json` / `.md` | `export_translation_proposals.py` | non-applied wording proposals with source, layout, and encoded-size evidence |
| `mes_report.json` | `build_mes_set.py` | per-chapter size, glyph, and spill metrics |
| `archive_report.json` | `build_archives.py` | slot mode and remaining archive capacity |
| `iso_patch_report.json` | `iso9660.py` caller | extents, sizes, allocations, headroom |
| `verification_manifest.json` / `verification.json` | `verification_manifest.py` and `rebuild.py` | one run's exact input fingerprint and direct output hashes |
| `final_verification_manifest.json` / `final_verification.json` | `verification_manifest.py` and `rebuild.py` | delivery hashes bound to the two-run input fingerprint |

Reports are evidence, not source. Delete and regenerate them when investigating
staleness; do not edit them to satisfy a check.

## Focused source checks

Run tests that do not require retail media:

```powershell
python -m compileall -q nostalgia1907.py work tests
python -m unittest discover -s tests -v
python work/audio_localization/test_audio_localization.py
python tools/style_audit.py
python -m black --check nostalgia1907.py tools tests work/clean_rebuild work/region_variant work/audio_localization
```

`work/clean_rebuild/test_script_layout.py` is retail-backed integration
coverage. In a media-free checkout it reports one explicit skipped prerequisite
with the missing prepared-fixture inventory instead of emitting layout test
errors. `python nostalgia1907.py validate` still requires the complete prepared
retail reference and remains the release gate.

Run the retail-backed validation gate:

```powershell
python nostalgia1907.py validate
```

Inspect a build plan without creating output:

```powershell
python nostalgia1907.py build --dry-run
```

The dry run hashes both original tracks and the U.S. BIOS, reports the selected
region, and reports whether the selected run and delivery roots are absent,
empty, or occupied. A real build rejects occupied, equal, or nested roots and
performs full validation before its first build. North America is the manifest
default; the build publishes only after two clean runs and two region-wrapper
runs independently agree.

## Fixed-layout and proposal review exports

`export_fixed_layout_review.py` creates TSV and Markdown queues for every
translated record whose `layout_policy` is `fixed`. Unknown width, row count,
placement, centering, clear/redraw behavior, and timing remain explicitly
unknown; the queue never converts a static preview into a runtime claim.
`PART4C:051` through `PART4C:059` are the first capture priority.

`export_translation_proposals.py` exports the current approval queue without
writing canonical JSON. When the queue is empty, it produces an explicit
source-only `NO_PENDING_PROPOSALS` report and does not require retail fixtures.
For an active proposal, Japanese wording is accepted only from the tracked
human-reviewed `bomb_semantics.json`; retail MES record, token-stream, and
preview hashes bind that evidence to the exact record without embedding raw
retail records or generated preview images. The tool compiles proposed MES
bytes in memory and reports exact record/MES deltas plus conservative retail
slot and ISO-allocation bounds. It does not run production recompression, does
not claim final archive fit when the uncompressed upper bound is insufficient,
and writes no archive or BIN/CUE. Human approval remains mandatory before any
canonical edit.

## Debugging by failure stage

### `doctor` fails

Check the exact path, size, and SHA-256 in the JSON report. Do not disable a hash
guard to accept a different disc revision. Add explicit support only after
analyzing the revision and defining a separate contract.

### Retail preparation fails

The problem is below translation: raw sector header/checksum, ISO hash, file
extent, archive table, or canonical retail MES/SCN guard. Inspect the earliest
failing layer.

### Edit preview fails

Read the record's roles, layout, row limit, and message. Shorten or improve the
wording if it genuinely exceeds a proven box. If the inferred renderer is
wrong, analyze the SCN command shape and fix the shared inference with tests.

### Semantic validation fails

Use the stable ID in the error. Determine whether a glossary invariant,
preserve policy, source fingerprint, duplicate translation, or generated
comparison is stale. Do not blanket-replace common words across unrelated
contexts.

### MES compilation fails

Classify the constraint:

- unsupported source character;
- record policy/index mismatch;
- runtime row or glyph limit;
- 16-bit pointer overflow;
- PART3C hard boundary;
- preserved dynamic-glyph reference.

Prefer canonical wording or a general renderer/compiler improvement. Do not
move records or silently truncate text.

### Archive or ISO placement fails

Read the reported stored size and headroom. Compression and guarded archive
reflow may use existing allocation, but ISO extents and total size remain
fixed. A change that requires moving files is outside the current production
contract.

### Raw-track regression fails

Treat it as a release blocker. Sector address, EDC/ECC, boot payload, track
geometry, Track 2, and CUE failures must not be waived.

## Adding or changing code

Keep boundaries narrow:

- parsing functions validate before returning structured data;
- writing functions accept validated structures and verify their own output;
- orchestration calls format modules rather than duplicating format logic;
- reports include measurements needed to review capacity and boundaries;
- deterministic order is explicit whenever sets, mappings, files, or glyphs
  become serialized output;
- expected operator mistakes raise concise domain errors, not partial output.

Multi-file canonical edits and layout migration use same-directory staged files
and prepared backups. A process-visible failure must restore every target that
was already replaced or raise an explicit incomplete-rollback error while
retaining the affected recovery backup. Direct low-level rebuild calls validate
their artifact basename again rather than
trusting the higher-level CLI.

All maintained Python follows the
[Python documentation standard](DOCSTRING_STANDARD.md). Every module, class,
function, method, property, and nested helper has a PEP 257 docstring.
Non-trivial APIs document meaningful inputs, outputs, side effects, failure
conditions, assumptions, and design choices. PEP 8 block comments explain why
reverse-engineered or preservation-sensitive steps exist.

For a format change, add:

1. a documented observation;
2. a strict read path;
3. malformed-input tests;
4. a round-trip or independent verification;
5. a boundary proof for the write path;
6. integration coverage in `regression.py` when it affects the disc.

For a renderer change, add:

1. the SCN command evidence;
2. a general inference rule;
3. at least one focused layout test;
4. a whole-game renderer audit;
5. comparison regeneration and playtesting.

## Determinism checklist

Generated bytes must not depend on:

- directory enumeration order;
- hash/set iteration order;
- temporary absolute paths;
- timestamps;
- a prior output directory;
- an older translated build;
- environment-specific line endings;
- Pillow or compression-library heuristics;
- network services.

The comparison exporter guarantees a byte-identical ZIP when the input bytes,
exporter source, and CPython major/minor runtime are identical. The guarantee
covers Windows/Linux/macOS filesystem differences because text line endings,
member paths, member order, ZIP timestamps/platform/permissions, PNG metadata,
PNG filtering, and DEFLATE blocks are specified by the exporter. It deliberately
does not promise identity across different CPython major/minor versions or after
a third-party program rewrites the archive. The external package manifest records
the exact member inventory and hashes.

Each comparison run uses a newly created staging directory. The expected file
set is built from that invocation's canonical chapter/record inventory. Missing
files fail; unexpected files fail; the ZIP receives only manifest-listed files.
No incremental comparison output is reused.

For game builds, `verification_manifest.py` records one canonical declared-input
manifest and a stable aggregate input fingerprint. It then binds direct output
hashes to that fingerprint. Two clean runs in one recorded environment
prove same-environment determinism; cross-environment game-build identity still
requires independent runs in those environments.

Sort serialized collections, use fresh output roots, hash guarded inputs, and
run the complete build twice.

## Repository hygiene

Never commit original or generated game media, BIOS files, extracted members,
runtime models, comparison images, or local configuration. Before committing:

```powershell
git status --short
git diff --check
git diff -- work/clean_rebuild/sources
```

Confirm that every source diff is intentional and that no ignored binary was
force-added.

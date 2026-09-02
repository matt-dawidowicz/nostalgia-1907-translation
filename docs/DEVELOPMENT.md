# Development and validation

## Environment

The supported runtime is Python 3.12 or newer. The production build and review
pipeline use only the Python standard library. The optional `dev` extra supplies
the pinned Ruff version used by CI for fast static lint checks.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# no project install is required
```

For the complete contributor toolchain:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check nostalgia1907.py tools tests work
```

Machine-specific retail and BIOS paths belong only in the ignored
`nostalgia1907.local.json`.

## Command layers

Use `nostalgia1907.py` for normal work. Lower-level tooling is installed as the
`work.clean_rebuild` package, with the optional region stage under
`work.region_variant`. For focused execution use `python -m` with the dotted
module name; direct package modules can still bypass preflight or evidence steps
owned by the CLI.

| Command | Purpose |
| --- | --- |
| `doctor` | Diagnose Python, canonical source, original tracks, retail preparation, and optional BIOS readiness |
| `prepare` | Verify original Track 1 and create the ignored retail reference |
| `edit` | Preview or apply one validated canonical English change |
| `compare` | Regenerate the complete bilingual review package |
| `validate` | Run source, renderer, semantic, compilation, archive, and regression gates |
| `build --dry-run` | Show the resolved region, inputs, hashes, and output-root state |
| `build` | Validate, perform two clean rebuilds, then publish only agreeing products |
| `build --region japan` | Produce the explicit diagnostic Japanese-region variant |

North America is the manifest default. The guarded region stage runs twice
independently just like the clean build.

## Source-only checks

These commands require no game media and are the public CI contract:

```powershell
python tools/source_health.py --root . --strict-release
python tools/source_manifest.py --root .
python -m compileall -q nostalgia1907.py tools tests work
python -m unittest discover -s tests -v
python -m ruff check nostalgia1907.py tools tests work
python tools/style_audit.py --root .
```

The checks have separate responsibilities:

1. **Source health** validates UTF-8/LF policy, Python/JSON/TOML structure,
   duplicate JSON keys, source-only publication rules, and the absence of game
   media or generated/private state.
2. **Source manifest** proves that `MANIFEST.sha256` describes the exact tracked
   review tree. After intentional source changes, update it with
   `python tools/source_manifest.py --root . --write`.
3. **Compilation** parses every maintained Python surface, including tests.
4. **Unit tests** cover CLI contracts, format parsers, renderer rules,
   transactions, source/release policy, comparison packaging, documentation,
   deterministic reports, and synthetic region-wrapper behavior.
5. **Ruff** owns generic Python linting and catches undefined names, unused
   imports, obsolete syntax/APIs, and other high-signal defects using the pinned
   development version and the Python 3.12 target.
6. **Documentation audit** enforces the repository-specific docstring contract
   described in `docs/DOCSTRING_STANDARD.md` without requiring third-party
   runtime dependencies.

The historical filename `tools/style_audit.py` is retained for continuity, but
the tool is intentionally docstring-specific; generic linting belongs to Ruff.

## Retail-backed validation

`python nostalgia1907.py validate` starts with the source-only gates, then
requires the prepared retail reference and runs the evidence that public CI
cannot legally carry:

1. whole-corpus renderer/layout audit;
2. retail-backed layout integration tests;
3. bilingual comparison regeneration;
4. semantic, duplicate-consistency, glossary, exemption, bomb, and profile
   validation;
5. all-chapter MES compilation and font-capacity checks;
6. chapter archive replacement and allocation checks; and
7. ISO/raw-track/Track-2 regression checks.

The retail-backed layout suite is `tests/test_script_layout_integration.py` inside
the same package as the compiler. It reports an explicit skip when prepared
fixtures do not exist. The CLI invokes it again only after retail prerequisites
are satisfied.

A successful `validate` proves static and deterministic contracts. It is not a
runtime claim about window clearing, transitions, timing, branch behavior,
save/reload behavior, hardware, or emulator compatibility.

## Generated evidence

Generated reports are disposable evidence, never source inputs. Important
outputs include:

| Artifact | Producer | Purpose |
| --- | --- | --- |
| `retail_report.json` | `prepare_retail.py` | Retail Track/ISO/member identity |
| `script_layout_audit.json` | `translation_formatter.py` | Per-record renderer/layout classification |
| bilingual JSON/HTML/images/ZIP + package manifest | `export_bilingual_comparison.py` | Human Japanese/English review |
| fixed-layout TSV/Markdown | `export_fixed_layout_review.py` | Runtime geometry review queue |
| `mes_report.json` | `build_mes_set.py` | Chapter size/glyph/spill measurements |
| `archive_report.json` | `build_archives.py` | Archive slot/reflow mode and headroom |
| ISO patch report | ISO build stage | Extents, logical sizes, allocations, headroom |
| verification/final verification JSON | `verification_manifest.py` / `rebuild.py` | Input binding and direct product hashes |

Delete and regenerate reports when diagnosing staleness. Never edit a generated
report to satisfy validation.

The old active translation-proposal analysis and its later no-pending
compatibility exporter have been removed now that the queue is complete. New
wording goes through `nostalgia1907.py edit`, normal validation, a clean build,
and runtime review.

## Production and validation boundaries

`work.clean_rebuild.rebuild:PRODUCTION_MODULES` is the exact local dependency
allowlist for the byte-producing clean build. Production modules use explicit
package-relative sibling imports; the independence audit accepts only dependencies
inside that allowlist and rejects deeper relative escapes, missing dependencies,
canonical source paths outside `sources/`, and known historical workspace markers.

Validation/review modules are maintained separately. They may reject a bad
candidate, but they do not become an alternate source of game bytes.
Historical forensic scripts and one-time migration/applicator code are not kept
beside production modules after their conclusions have been promoted into
shared code, tests, or documentation.

Reviewed change ledgers for the 2026-08-27 translation revision live under
`provenance/2026-08-27/`. They are historical evidence and never build inputs.

## Determinism and binding

Game builds must use **fresh output roots**. Generated bytes must not depend on
filesystem enumeration order, hash/set order, timestamps, temporary absolute
paths, a previous output tree, or a prior translated image.

`verification_manifest.py` records declared canonical source, prepared retail
fixtures, production/validation code, configuration, original tracks, build
profile, and runtime identity. It derives one stable **aggregate input
fingerprint** and binds each managed output to an explicit SHA-256 immediately
before report creation. Two clean runs must agree before publication.

The bilingual comparison package independently fixes member paths, ordering,
ZIP metadata, PNG generation, and text line endings. Its byte-identity guarantee
is scoped to the same input bytes, exporter source, and **CPython major/minor**
runtime; it does not claim archive identity after another program rewrites the
ZIP or across an unspecified Python runtime.

Determinism proves reproducibility. It does not convert static evidence into a
runtime claim.

## Editing and transaction rules

Canonical edits are ID-keyed and transactional. Multi-file edit/migration paths
stage same-directory temporary files, create recovery backups, and either commit
all replacements or restore already-replaced targets. A process-visible failure
must never leave a silently half-applied corpus.

Parsers validate before returning structured data. Writers accept validated
structures and verify their own output. Deterministic order is explicit whenever
a set, mapping, directory listing, or glyph collection becomes serialized.

Expected operator mistakes should become concise domain errors. Low-level build
entry points repeat critical basename/path validation rather than assuming the
CLI was used.

## Changing formats or renderers

For a binary-format change, add:

1. documented structural evidence;
2. a strict read path;
3. malformed-input tests;
4. a round-trip or independent verification;
5. a boundary proof for the write path; and
6. integration coverage in `regression.py` when disc bytes are affected.

For a renderer change, add:

1. the SCN evidence;
2. a general inference rule rather than a chapter-specific patch;
3. focused synthetic coverage;
4. whole-game renderer/layout validation;
5. retail-backed compilation/comparison evidence; and
6. candidate-bound runtime testing of the affected behavior.

A screenshot can identify a symptom; it cannot by itself establish a renderer
rule.

## Debugging by failure stage

**`doctor`** — fix the earliest size/hash/path mismatch. Do not relax a frozen
hash guard to accept another retail revision.

**`prepare`** — investigate raw-sector, ISO, archive, MES/SCN, or fixed-font
identity before translation logic.

**`edit` / renderer audit** — check stable ID, inferred role, cell geometry,
row limits, and whole-token boundaries. Correct semantic English when wording is
wrong; correct a shared renderer rule when the behavior repeats structurally.

**semantic validation** — inspect the exact stable ID and the named glossary,
profile, duplicate, exemption, or source-fingerprint rule. Do not blanket-replace
words across unrelated contexts.

**MES/archive/ISO regression** — treat pointer overflow, fixed boundaries,
allocation failures, changed extents, raw-sector changes, Track 2 changes, or
unexpected output inventory as release blockers.

**runtime** — reproduce the exact candidate, scene/branch, transitions, and
page advances in Ares. Static checks cannot waive an observed runtime defect.

## Documentation standard

Maintained Python follows [the documentation standard](DOCSTRING_STANDARD.md).
Every module, class, function, method, property, and nested helper has a PEP 257
docstring. Non-trivial APIs document meaningful inputs, outputs, side effects,
failure conditions, assumptions, and design choices. Comments explain why a
preservation-sensitive or reverse-engineered step exists rather than translating
individual Python statements into English.

## Before committing

Run the source-only checks above, then inspect:

```powershell
git status --short
git diff --check
git diff -- work/clean_rebuild/sources
```

Confirm that every canonical-source diff is intentional and that no retail,
BIOS, generated comparison, or playable artifact is tracked. If playable bytes
changed, complete the retail-backed gates and candidate-bound runtime evidence
before making release claims.

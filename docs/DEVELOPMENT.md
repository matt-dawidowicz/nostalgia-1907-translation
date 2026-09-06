# Development and validation

## Environment

The supported runtime is Python 3.12 or newer. Production/operator code uses
only the Python standard library. The repository is run directly from the
checkout; there is no editable-install or package-install step.

Create a virtual environment if desired, then install only the development
quality tools:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Machine-specific retail and BIOS paths belong only in the ignored
`nostalgia1907.local.json`.

## Command layers

Use `nostalgia1907.py` for normal work. Lower-level code lives in repository-
local Python packages `work.clean_rebuild` and `work.region_variant`; focused
execution uses `python -m` from the repository root. Direct module execution can
bypass preflight or evidence steps owned by the operator CLI, so it is for
narrow testing/diagnosis rather than the normal release workflow.

| Command | Purpose |
| --- | --- |
| `doctor` | Diagnose Python, canonical source, original tracks, retail preparation, and BIOS readiness |
| `prepare` | Verify original Track 1 and create the ignored retail reference |
| `edit` | Preview or apply one validated canonical English change |
| `compare` | Regenerate the complete bilingual review package |
| `validate` | Run the unified source gate plus retail renderer/semantic/compilation/archive/regression gates |
| `build --dry-run` | Show resolved region, inputs, hashes, and output-root state |
| `build` | Validate, perform two clean rebuilds, then two guarded North American wrappers and publish only agreeing products |
| `build --region japan` | Produce the explicit diagnostic Japanese-region variant |

North America is the manifest default.

## Source-only checks

The authoritative contributor/CI command is:

```powershell
python -m tools.source_checks --root . --strict-release
```

Do not maintain a separate copied checklist as the contract. The command owns:

1. **Source health** — UTF-8/LF policy, structured-source parsing, duplicate JSON
   keys, source-only publication rules, and forbidden-media/local-state checks.
2. **Source manifest** — exact `MANIFEST.sha256` identity for the tracked review
   tree.
3. **Production dependency policy** — the `PRODUCTION_MODULES` import/data
   boundary used by the byte-producing clean build.
4. **Compilation** — every maintained Python surface, including tests.
5. **Unit tests** — CLI, format parsers, renderer contracts, source policy,
   deterministic reports, hardening, performance equivalence, and region logic.
6. **Ruff format** — canonical 79-column layout check.
7. **Ruff lint** — PEP 8/Pyflakes/import-order/pyupgrade/pydocstyle rules from
   `pyproject.toml`.
8. **mypy** — the maintained incremental target set.
9. **Public API documentation audit** — repository-specific structural
   documentation policy in addition to Ruff's PEP 257 rules.

After intentional tracked-source changes:

```powershell
python tools/source_manifest.py --root . --write
python -m tools.source_checks --root . --strict-release
```

The historical filename `tools/style_audit.py` remains, but generic Python style
is owned by Ruff; `style_audit.py` enforces the project-specific public-API
contract.

## CI contract

GitHub Actions runs two hosted jobs:

- Ubuntu: complete strict source gate on Python 3.12, then compile/unit
  compatibility on Python 3.13 and 3.14;
- Windows: complete strict source gate on Python 3.14.

Pull requests run through the PR event; direct push validation is limited to
`main`. A shared concurrency group cancels superseded PR revisions.

## Retail-backed validation

`python nostalgia1907.py validate` begins with the unified source gate, then
requires the prepared retail reference and runs evidence that public CI cannot
legally carry:

1. whole-corpus renderer/layout and fixed-layout ownership checks;
2. `tests/test_script_layout_integration.py` against prepared retail MES/SCN/font
   fixtures;
3. bilingual comparison regeneration and package validation;
4. semantic, duplicate-consistency, glossary, exemption, bomb, and profile
   validation;
5. all-chapter MES compilation and font-capacity checks;
6. chapter archive replacement/allocation checks; and
7. ISO/raw-track/Track-2 regression checks.

A successful `validate` proves static and binary contracts. It is not a runtime
claim about window clearing, transitions, timing, branch behavior, save/reload,
hardware, or emulator compatibility.

## Generated evidence

Generated reports are disposable evidence, never source inputs. Important
outputs include:

| Artifact | Producer | Purpose |
| --- | --- | --- |
| `retail_report.json` | `prepare_retail.py` | Retail Track/ISO/member identity |
| `script_layout_audit.json` | `translation_formatter.py` | Per-record renderer/layout classification |
| bilingual JSON/HTML/images/ZIP + package manifest | `export_bilingual_comparison.py` | Human Japanese/English review |
| fixed-layout TSV/Markdown | `export_fixed_layout_review.py` | Runtime geometry review inventory |
| `mes_report.json` | `build_mes_set.py` | Chapter size/glyph measurements |
| `archive_report.json` | `build_archives.py` | Archive slot/reflow mode and headroom |
| ISO patch report | ISO build stage | Extents, logical sizes, allocations, headroom |
| verification/final verification JSON | `verification_manifest.py` / `rebuild.py` | Input binding and direct product hashes |

Delete and regenerate reports when diagnosing staleness. Never edit a generated
report to satisfy validation.

The old active translation-proposal machinery has been removed. New wording
uses `nostalgia1907.py edit`, normal validation, a clean build when needed, and
runtime review.

## Production and validation boundaries

`work.clean_rebuild.rebuild:PRODUCTION_MODULES` is the exact local dependency
allowlist for the byte-producing clean build. Production modules use explicit
package-relative sibling imports; the independence audit accepts only
allowlisted dependencies and tracked data inside the declared production data
surface.

Validation/review modules may reject a bad candidate, but they do not become an
alternate source of game bytes. Historical forensic scripts and one-time
migration/applicator code are not kept beside production modules after their
conclusions are promoted into shared code, tests, or documentation.

Embedded profiles are likewise fail-closed: `profile_schema.py` accepts only
active fields and rejects retired migration flags or unknown keys.

## Determinism and binding

Game builds must use **fresh output roots**. Generated bytes must not depend on
filesystem enumeration order, hash/set order, timestamps, temporary absolute
paths, previous outputs, or a prior translated image.

`verification_manifest.py` records declared canonical source, prepared retail
fixtures, production/validation code, configuration, original tracks, build
profile, and runtime identity. It derives one stable **aggregate input
fingerprint** and binds each managed output to an explicit SHA-256 immediately
before report creation. Two clean runs must agree before publication.

The bilingual comparison package independently fixes member paths, ordering,
ZIP metadata, PNG generation, and text line endings. Its byte-identity guarantee
is scoped to the same input bytes, exporter source, and **CPython major/minor**
runtime; it does not claim archive identity after another tool rewrites the ZIP
or across an unspecified runtime.

Determinism proves reproducibility. It does not convert static evidence into a
runtime claim.

## Editing and transaction rules

Canonical edits are ID-keyed and transactional. Multi-file edit paths validate
all requested changes before replacement, stage same-directory temporary files,
retain recovery backups when needed, and roll back already-replaced targets on
a later failure. Duplicate JSON keys are rejected before object construction.

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
4. a round-trip, reference-algorithm, or independent verification;
5. a boundary proof for the write path; and
6. integration coverage when disc bytes are affected.

For a renderer change, add:

1. SCN/runtime evidence;
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

**source gate** — fix the named health, manifest, dependency, compile, unit,
format, lint, type, or documentation failure. Do not skip a later stage because
an earlier one is inconvenient.

**`edit` / renderer audit** — check stable ID, inferred role, cell geometry,
row limits, and whole-token boundaries. Correct semantic English when wording is
wrong; correct a shared renderer rule when behavior repeats structurally.

**MES/archive/ISO regression** — treat pointer overflow, fixed boundaries,
allocation failures, changed extents, raw-sector integrity failures, Track 2
changes, or unexpected output inventory as release blockers.

**runtime** — reproduce the exact candidate, scene/branch, transitions, and page
advances in Ares. Static checks cannot waive an observed runtime defect.

## Documentation standard

Maintained Python follows [the documentation standard](DOCSTRING_STANDARD.md).
Ruff's PEP 257 rules and the repository-specific documentation audit are both
part of the unified source gate. Comments explain why a preservation-sensitive
or reverse-engineered step exists rather than narrating Python syntax.

## Before committing

After refreshing `MANIFEST.sha256` when needed, run the unified source gate and
inspect:

```powershell
git status --short
git diff --check
git diff -- work/clean_rebuild/sources
```

Confirm that every canonical-source diff is intentional and that no retail,
BIOS, generated comparison, or playable artifact is tracked. If playable bytes
changed, complete the retail-backed gates and candidate-bound runtime evidence
before making release claims.

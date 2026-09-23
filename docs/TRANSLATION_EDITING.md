# Translation analysis and editing

## The safe mental model

Edit canonical meaning, not compiled bytes. English under
`work/clean_rebuild/sources/` is authoritative. MES, LZ, ISO, BIN/CUE, rendered
images, audits, and comparison files are generated and never become the source
of a wording change.

The supported key is a stable record ID:

```text
CHAPTER:NNN
PART1A:003
PART3B_:078
START:000
```

The numeric component is the zero-based `records[index]` value formatted with
three digits. It does not change when the sentence changes.

## Current translation policy

The 2026-08-27 full-corpus Japanese audit established the durable priority:
retail Japanese meaning first, then natural English, first-play clarity,
character voice, and period/register choices. The September complete-script
audit applied that standard across the rest of the game and synchronized
alternate-route material. See [current project status](CURRENT_STATUS.md) for
how those dated passes fit into the cumulative successor source line.

Voice work must never restore an older mistranslation. Regional speech should be
readable social/regional English without phonetic eye dialect. Source-authored
oddities and anachronisms are preserved when the Japanese evidence supports
them.

Character/terminology rules live in [the glossary and style
guide](GLOSSARY_STYLE_GUIDE.md).

## Prerequisites

Run directly from the repository checkout; **do not install the project as an
editable package**. Install development tools only when needed, then provide
exact Japanese retail tracks and prepare the retail reference:

```powershell
python -m pip install -r requirements-dev.txt
python nostalgia1907.py doctor
python nostalgia1907.py prepare
```

The prepared reference is ignored by Git. It contains hash-checked retail MES
and SCN data used to infer renderer contracts and verify source provenance.

## Chapter JSON schema

A chapter source has four conceptual sections:

```json
{
  "schema_version": 1,
  "chapter": "PART1A",
  "record_count": 136,
  "retail_mes": {"size": 5321, "sha256": "..."},
  "retail_scn": {"size": 3354, "sha256": "..."},
  "profile": {"translation_status": "locked"},
  "text_mode": "render-ready",
  "records": [
    {
      "index": 0,
      "policy": "translate",
      "text": "Game Hall",
      "layout_policy": "adaptive"
    }
  ]
}
```

### Record fields

| Field | Meaning | Editing rule |
| --- | --- | --- |
| `index` | Zero-based MES record position | Never renumber, insert, delete, or reorder |
| `policy: "translate"` | Record is generated from canonical English | Edit only through the reviewed workflow |
| `policy: "preserve"` | Retail record is intentionally retained | Keep `text` null; do not translate casually |
| `text` | Canonical English | Adaptive records store normalized semantic text |
| `display_text` | Optional constrained renderer text when supported | Keep semantic ownership explicit; use only with proven contract |
| `layout_policy: "adaptive"` | Shared renderer contract owns reflow | Do not add manual line breaks or padding |
| `layout_policy: "fixed"` | Reviewer-owned physical layout | Exact spaces/lines are part of the reviewed source |

Top-level `text_mode` remains part of the canonical schema, while per-record
`layout_policy` owns adaptive versus fixed formatting behavior.

## Active profile fields

`profile_schema.py` is fail-closed. Unknown fields and retired migration flags
are errors; they are **not** retained as compatibility state.

Active fields are:

- `schema_version`, `name`, and `translation_status`;
- `required_text_exact`, `required_text_prefixes`, and
  `forbidden_text_patterns`;
- `scn_dialogue_layout`, `scn_continuation_layout`,
  `scn_dialogue_runtime_layout`, `scn_continuation_runtime_layout`, and
  `scn_window_text_subtypes`;
- `layout_overrides`, `runtime_layout_overrides`, and `row_limit_overrides`;
- `text_box_overrides`; and
- `role_overrides`.

Indexed production rules must address valid translated records and use canonical
zero-based decimal keys. Do not add an override merely to make one screenshot
pass; first establish why shared SCN inference does not model the renderer.

## Find and preview a record

Use the stable ID:

```powershell
python nostalgia1907.py edit PART1A:003
```

The command reports current semantic text, inferred roles, visible/runtime
capacities, row limits, and the rendered preview when retail evidence is
available.

Search canonical wording with ordinary source tools when useful, but scripts
that apply changes must still target stable IDs rather than mutable English.

The bilingual comparison package correlates visible Japanese and English across
all chapters:

```powershell
python nostalgia1907.py compare
```

The exporter uses fresh staging, an exact expected inventory, deterministic
text/PNG/ZIP generation, and package validation. A comparison preview is human
review evidence, not proof of emulator behavior.

## Preview and apply one edit

Previewing is read-only:

```powershell
python nostalgia1907.py edit PART1A:003 `
  --text "How about we switch games and play one more round?"
```

Review the stable ID, current/proposed wording, inferred role, preview rows,
visible/runtime widths, and row limit. For adaptive records, whitespace is
normalized and the semantic text must round-trip through wrapping without losing
or fragmenting words.

Apply only after review:

```powershell
python nostalgia1907.py edit PART1A:003 `
  --text "How about we switch games and play one more round?" `
  --apply
```

The tool writes only the owning chapter JSON, updates applicable profile text
rules, and chooses layout ownership from the validated contract. It does not
patch MES/LZ/BIN output.

Inspect the canonical diff immediately:

```powershell
git diff -- work/clean_rebuild/sources/PART1A.json
```

## Apply a reviewed batch

Use stable IDs as keys:

```json
{
  "changes": {
    "PART1A:003": "First reviewed sentence.",
    "PART2C:041": "Second reviewed sentence."
  }
}
```

Apply:

```powershell
python nostalgia1907.py edit --changes reviewed-changes.json
```

All entries are validated before replacement. Duplicate JSON keys are rejected.
Affected chapters are staged beside canonical files; replacement failures roll
back already-replaced targets and retain recovery material if rollback itself
fails. This is an all-or-rollback process guarantee, not a claim of multi-file
crash atomicity.

## Screenshot-driven investigation

When a screenshot looks wrong:

1. Record the exact candidate, chapter/scene, and visible text.
2. Resolve the stable record ID.
3. Preview the canonical record without changing source.
4. Confirm the inferred role matches the renderer.
5. Decide whether the problem is wording, shared layout inference, fixed layout,
   or stale generated output.
6. Change canonical wording only if meaning/English is wrong.
7. Change shared layout code only if the general renderer contract is wrong.
8. Regenerate comparison evidence and run complete validation.
9. Playtest the same scene, transitions, and nearby branches.

The existing two-byte PART1A SCN fix is a closed hash-locked exception backed by
specific runtime evidence; it is not a template for screenshot-specific binary
patches.

## Semantic consistency data

Use [`GLOSSARY_STYLE_GUIDE.md`](GLOSSARY_STYLE_GUIDE.md) for reviewed naming,
terminology, dialogue, warning, choice, and layout conventions. Machine-enforced
rules include:

- `translation_glossary.json` for source-fingerprinted terms and contextual
  distinctions;
- `translation_exemptions.json` for reviewed visible/control exceptions;
- `translation_repairs.json` for bounded repairs and preserve decisions;
- `bomb_semantics.json` for bomb/cord/wire semantic constraints; and
- `script_layout_rules.json` for renderer/layout policy.

Add a glossary rule when a term must remain stable across future edits. Use a
record-scoped contextual exception when similar source material legitimately
requires different English.

## Validate after editing

Run:

```powershell
python nostalgia1907.py validate
```

Validation first invokes the maintained unified source gate, then requires the
prepared retail reference and runs renderer/layout, retail integration,
comparison, semantic/profile, compilation, archive, ISO, raw-track, and Track-2
checks.

Validation does not prove prose quality or live emulator behavior. A candidate
whose playable bytes change still requires candidate-bound Ares evidence.

## Direct JSON editing

Direct editing is useful for carefully reviewed bulk work, but it bypasses the
CLI's preview/apply guard. If editing JSON directly:

1. preserve UTF-8 and the existing schema;
2. keep indexes contiguous and unchanged;
3. do not change retail MES/SCN guards casually;
4. do not change `policy: "preserve"` records without source analysis;
5. do not add wrapping/padding to adaptive text;
6. update active glossary/profile invariants when intentionally changing locked
   text; and
7. run complete validation.

Never edit generated MES/LZ/BIN output and reverse-import it as canonical
English.

## Fixed-layout runtime evidence

A record marked `layout_policy: "fixed"` has reviewer-owned physical layout
rather than shared adaptive reflow. Fixed records are included in the permanent
release-validation inventory; static checks protect their encoded constraints,
but do not prove every live centering, transition, clearing, or timing state.

Use `export_fixed_layout_review.py` when preparing runtime evidence. For the
current successor release, `PART4C:051` through `PART4C:059` remain an explicit
uninterrupted ending-path checkpoint.

## Retired proposal workflow

The old active `export_translation_proposals.py` workflow and no-pending
compatibility machinery have been removed. There is no maintained proposal
queue that can write or stand in for canonical source.

For a new wording change, establish source evidence, preview the stable ID with
`nostalgia1907.py edit`, apply the reviewed canonical edit, regenerate comparison
evidence when appropriate, and rerun the maintained validation/release gates.

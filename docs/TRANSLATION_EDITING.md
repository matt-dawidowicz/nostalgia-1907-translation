# Translation analysis and editing

## The safe mental model

Edit canonical meaning, not compiled bytes. The English under
`work/clean_rebuild/sources/` is authoritative. MES, LZ, ISO, BIN/CUE, rendered
images, audits, and comparison files are generated and should never be used as
the source of a wording change.

The supported key is a stable record ID:

```text
CHAPTER:NNN
PART1A:003
PART3B_:078
START:000
```

The numeric component is the zero-based `records[index]` value formatted with
three digits. It does not change when the sentence changes.

## Prerequisites

Install the editable package, provide exact Japanese retail tracks, and prepare
the retail reference:

```powershell
python -m pip install -e .
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
  "retail_mes": {
    "size": 5321,
    "sha256": "..."
  },
  "retail_scn": {
    "size": 3354,
    "sha256": "..."
  },
  "profile": {
    "translation_status": "locked"
  },
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
| `policy: "preserve"` | Retail record bytes are semantically non-prose or intentionally retained | Keep `text` null; do not translate casually |
| `text` | Canonical English | Adaptive records store normalized semantic text |
| `layout_policy: "adaptive"` | SCN proves a shared renderer contract | Do not add manual line breaks or padding |
| `layout_policy: "fixed"` | No safe reflow geometry is proven | Exact spaces/lines are part of the reviewed layout |

Top-level `text_mode` is retained for compiler compatibility. Per-record
`layout_policy` is the current authority for the global formatter.

### Profile fields

The embedded `profile` records reviewed structural exceptions and regression
requirements. Common fields include:

| Field | Purpose |
| --- | --- |
| `required_text_prefixes` | Text whose beginning is a gameplay/UI invariant |
| `required_text_exact` | Exact text locked by a regression |
| `forbidden_text_patterns` | Known bad wording or format variants |
| `layout_overrides` | Reviewed visible cell widths where SCN inference alone is insufficient |
| `runtime_layout_overrides` | Engine stride when it differs from visible width |
| `row_limit_overrides` | Reviewed vertical capacity |
| `role_overrides` | Renderer role for a structurally exceptional record |

Do not add an override merely to make one screenshot pass. First show why the
original SCN selects a renderer that the shared inference does not yet model.

Paths in `text_sources` are historical provenance metadata. They are not
production dependencies and should not be copied into new logic.

## Find a record

Search by stable ID indirectly through chapter and index:

```powershell
python nostalgia1907.py edit PART1A:003
```

That command prints the current semantic text, inferred roles, visible/runtime
cell capacities, row limit, and rendered preview.

Search canonical wording:

```powershell
rg -n -F '"text": "How about we switch games' work/clean_rebuild/sources
```

Search a record with a short read-only Python query:

```powershell
python -c "import json,pathlib; p=pathlib.Path('work/clean_rebuild/sources/PART1A.json'); d=json.loads(p.read_text(encoding='utf-8')); print(d['records'][3])"
```

The bilingual comparison package is the best way to correlate visible Japanese
and English across all chapters:

```powershell
python nostalgia1907.py compare
```

Its JSON preserves IDs and raw Japanese source bytes; its HTML and images are
for human review. The exporter uses fresh run-specific staging, packages only
the current expected-file manifest, and writes an exact inventory/hash
sidecar. Static comparison previews do not prove runtime correctness.

## Preview a single edit

Previewing is read-only:

```powershell
python nostalgia1907.py edit PART1A:003 `
  --text "How about we switch games and play one more round?"
```

Review:

- the stable ID and current/proposed wording;
- inferred roles such as `main_dialogue` or `menu_choice`;
- `preview_rows`;
- visible cell widths versus runtime stride;
- floating-window `max_rows`;
- any failure explaining why the edit cannot be applied.

For adaptive records, whitespace is normalized before storage. Wording must
round-trip from semantic text to preview rows and back without losing or
changing words.

## Apply a single edit

After reviewing the preview:

```powershell
python nostalgia1907.py edit PART1A:003 `
  --text "How about we switch games and play one more round?" `
  --apply
```

The tool writes only the owning chapter JSON. It updates an applicable
`required_text_exact` entry and chooses adaptive or fixed policy from the SCN
contract. It does not patch a MES, archive, or disc image.

Immediately inspect the diff:

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

All entries are validated before chapter files are written. Duplicate keys are
rejected before JSON object construction can silently discard an earlier edit.
Affected chapters are staged beside their canonical files with byte-for-byte
backups; a later write or replacement failure rolls back chapters already
replaced. If the rollback itself fails, the tool retains the affected byte-for-byte
backup and reports its recovery path. This is an all-or-rollback process
guarantee, not a claim of multi-file crash atomicity. Do not combine `--changes` with a positional record,
`--text`, or `--apply`.

## Screenshot-driven investigation

When a screenshot looks wrong:

1. Record the chapter/scene and exact visible text.
2. Search the canonical source or comparison JSON for candidate IDs.
3. Preview each candidate ID without changing data.
4. Confirm the inferred role matches the on-screen renderer.
5. Decide whether the problem is wording, general layout inference, or a stale
   generated artifact.
6. Change canonical wording only if the meaning is wrong.
7. Change shared layout code only if the renderer contract is wrong.
8. Regenerate the comparison and validate.
9. Playtest the same scene and nearby branches.

Do not identify records by their current English alone when scripting a change.
Use stable IDs so duplicate wording cannot target the wrong record.

## Semantic consistency data

Use [`GLOSSARY_STYLE_GUIDE.md`](GLOSSARY_STYLE_GUIDE.md) for the reviewed English naming, terminology, dialogue, warning, choice, and layout conventions. The machine-enforced tables below remain authoritative where they define a source fingerprint or record-scoped exception.

The validation layer uses:

- `translation_glossary.json` for source-fingerprint terms, controlled phrases,
  authoritative records, and reviewed contextual distinctions;
- `translation_exemptions.json` for reviewed visible/control exceptions;
- `translation_repairs.json` for bounded repair rules and preserve decisions;
- `bomb_semantics.json` for the dedicated bomb/cord/wire terminology audit;
- `script_layout_rules.json` for renderer roles and project-wide layout gates.

Add a glossary rule when a term must remain consistent across future edits.
Use a contextual exception when identical-looking source material is
intentionally translated differently because the scene meaning differs. Every
exception should point to a stable record and source fingerprint.

## Validate after editing

Run:

```powershell
python nostalgia1907.py validate
```

This compiles Python, runs audio companion unit tests, audits every renderer
contract, runs layout compilation tests, regenerates the comparison package,
and checks semantic/generated-artifact consistency.

Validation does not prove that prose is elegant or that every branch was
visited. Manual playtesting remains the final release gate.

## Direct JSON editing

Direct editing is sometimes useful for research or carefully reviewed bulk
work, but it bypasses the CLI's preview/apply guard. If you edit JSON directly:

1. preserve UTF-8 and the existing JSON structure;
2. keep record indexes contiguous and unchanged;
3. do not change retail MES/SCN guards;
4. do not change preserved records without source analysis;
5. do not add wrapping to adaptive text;
6. update glossary/profile invariants when intentionally changing locked text;
7. run the complete validation sequence.

Never edit generated MES/LZ/BIN output and then attempt to reverse-import it as
canonical English.

## Fixed-layout runtime evidence

A record marked `layout_policy: "fixed"` has no safe general SCN-derived reflow
contract. Static character counts and preview rows may guide review, but they do
not prove runtime width, centering, clipping, row stride, page behavior, or
timing. Use `export_fixed_layout_review.py` to generate the complete review
queue. Capture the exact retail and candidate scene before changing layout
ownership; start with `PART4C:051` through `PART4C:059`.

## Non-applied wording proposals

`export_translation_proposals.py` produces evidence reports only. It does not
write canonical JSON. For Japanese claims, cite a tracked human-reviewed source
such as `bomb_semantics.json` by file hash and record key. Do not derive Japanese
readings from mojibake, uncertain byte decoding, or an unlabeled screenshot.
After human approval, preview and apply a canonical edit through the normal
`nostalgia1907.py edit` workflow, then rerun all validation.

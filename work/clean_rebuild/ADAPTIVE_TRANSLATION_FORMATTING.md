# Adaptive translation formatting

English wording is stored by stable `CHAPTER:NNN` record ID. The Japanese MES
record and the chapter SCN are authoritative; English text is never shifted to
a neighboring record and a UI role is never inferred from English context.

`translation_formatter.py` recognizes these renderers:

- top location and viewpoint labels (`0x22` + `0x23`)
- speaker names and lower dialogue (`0x21`)
- lower-window continuations (`0x21` with a zero second ID)
- side/thought windows (`0x24/0x27`), including immediately chained
  standalone `0x27` continuation records
- reviewed overlay/narration windows (`0x24/0x28`)
- menu choices (`0x31`) and structurally proven `0x42/0x43` selector windows

The width used to choose words and the runtime row stride are separate. Before
encoding, adaptive prose is normalized, word-wrapped, and padded to the exact
runtime stride. Most retail main-dialogue records begin with a Japanese
opening-quote gutter. For those records only, the compiler emits one shared
blank cell at the start. Lower dialogue then follows its repeating 12/11/11
physical row cadence: the gutter leaves 11 prose cells on row zero, while rows
3, 6, and later page starts retain all 12 prose cells. No artificial cell is
emitted at a page transition. Floating windows also have an SCN-derived maximum
row count.
Every translated record has one explicit policy:

- `adaptive` when SCN proves the renderer geometry; the compiler owns wrapping.
- `fixed` when SCN provides no safe reflow geometry, such as credits, counters,
  static navigation labels, and direct overlays; exact bitmap layout is retained.

## Ellipsis style

Canonical dialogue uses an attached ellipsis pause: `Wait...what happened?`
rather than `Wait... What happened?`. The formatter removes an immediate
post-ellipsis space and lowercases an ordinary following word across the full
translated script. It preserves capitalization for reviewed names, proper
adjectives, direct-address titles, acronyms, and the first-person pronoun and
its contractions. A renderer row may end after `...`; this is a soft wrapping
boundary only, so compilation never adds a visible space when the next row
continues the same thought. The compact ellipsis bitmap spans its full cell so
it does not create a false visual space before an attached following word.

Migration is atomic. It writes nothing if any classified record exceeds its
renderer, and the whole-game audit fails if a classified record is not adaptive
or a non-reflowable record is not explicitly fixed. The same audit also checks
every SCN-derived adaptive row for its visible packed-cell limit and verifies
that each whitespace-delimited canonical token remains whole across renderer
row boundaries. This catches a future formatter regression that would expose
parts of one word on adjacent lines; it cannot replace scene playtesting for a
renderer behavior that static SCN evidence does not describe.

## Preview a wording change

```powershell
python nostalgia1907.py edit PART1A:003 `
  --text 'How about we switch games and play one more round?'
```

## Apply reviewed changes

Create a JSON file keyed by stable IDs:

```json
{
  "changes": {
    "PART1A:003": "How about we switch games and play one more round?"
  }
}
```

Then run:

```powershell
python nostalgia1907.py edit --changes changes.json
```

For a proven renderer, the editor writes semantic English and marks the record
`layout_policy: adaptive`; the compiler derives its final rows from the
original SCN. A fixed record retains the reviewer's explicit rows and spaces.
The editor refuses an adaptive edit that exceeds a box or vertical limit.

## Migrate the complete canonical script

```powershell
python work\clean_rebuild\translation_formatter.py --migrate
```

This is a whole-script operation, not a record allowlist.

## Audit and tests

```powershell
python nostalgia1907.py validate
```

The whole-game audit is written to
`outputs/Nostalgia1907_Translation_Audit/script_layout_audit.json`.

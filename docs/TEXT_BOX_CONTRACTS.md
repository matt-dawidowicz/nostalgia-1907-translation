# Text-box contracts

## Purpose

Canonical adaptive English is semantic text, not hand-laid screen rows.
`scn_layout.py` derives named renderer contracts from the hash-locked retail SCN
and a small set of reviewed structural exceptions. `renderer_format.py` owns
semantic normalization, visible-cell wrapping, row reconstruction, and
whole-token validation. `mes_compiler.py` repeats the authoritative contract
checks before it packs bytes.

This separation lets a shared renderer correction regenerate physical MES rows
without rewriting English prose to compensate for stale storage geometry.

## Contract catalogue

| Contract | Evidence | Geometry ownership |
| --- | --- | --- |
| `lower_dialogue` | SCN `0x21 <speaker> <text>` | One initial 12-cell physical row, then 11-cell continuation stride. Retail `0x10` quote becomes a one-time blank opening gutter; later page clears do not reset the wider opening row. |
| `lower_continuation` | SCN `0x21 <text> 0x0000` | No opening gutter; begins directly on the native 11-cell continuation stride. |
| `floating_window` | SCN `0x24` descriptor plus MAIN.BIN `0x27`/`0x28` renderer | Descriptor bytes are X tile, Y tile, width tiles, and an initial height field. Text begins at `(8·X+8, 8·Y+10)`, advances 16 px per row, and owns `floor(((width-2)·8)/12)` 12-pixel cells. Final window height is recomputed as `2·rows+2` tiles. `0x27` enables a blinking bottom-center indicator sprite; `0x28` does not. |
| `full_screen_narration` | Reviewed START evidence | Explicit 16-cell full-screen narration contract. |
| `lower_caption` | Reviewed PART2A:093 evidence | Explicit lower-area route-caption contract. |
| `scene_label` | MAIN.BIN `0x22`/`0x23` DMA destinations plus invariant `SCREEN0.BS`/`SCREEN1.BS` tilemaps in all 19 archives | Location canvas is x=16..143, y=8..23 with text origin x=18 and 21 six-pixel character slots. Perspective canvas is x=152..239, y=8..23 with text origin x=154 and 14 character slots. |
| `special_line` | SCN `0x20`, MAIN.BIN mode-3 text state, and invariant bottom-strip tile maps | Three 224x16 strips at y=168, 184, and 200. Text starts at x=18 and y=170/186/202, with 18 12-pixel cells per line. `0x55` clears all three strips and resets the line index; a fourth successive line scrolls the lower two strips upward and reuses the bottom strip. |

`text_box_overrides` is allowed only for a reviewed exceptional renderer whose
geometry is already supported by active layout data. The profile schema rejects
retired migration keys and unknown fields; an override cannot silently pretend
to be active.

## Permanent whole-game gates

Layout safety is no longer a one-off proposal-preview exercise. Maintained
validation now inventories the complete translated corpus and distinguishes
shared adaptive contracts from reviewer-owned fixed records. It also binds the
renderer view to script structure:

- every translated record must have a proven SCN reference or explicit
  profile-backed contract;
- SCN-to-MES references and menu-choice branch targets are inventoried;
- adaptive records are checked for legal row cadence, token boundaries, gutter
  behavior, and row-edge encoding;
- fixed-layout records remain explicit and cannot silently opt into adaptive
  reflow; and
- preserved records retain control/fixed bytes and remap-stable rendered token
  identity.

Direct `compile_mes()` calls repeat the same semantic-row validation, so a lower
level build path cannot bypass the preview model.

## Lower-dialogue row-edge rule

The native lower-dialogue routine gives fixed codes `02`, `03`, `04`, `05`,
`08`, and `11` special lookahead behavior at a row boundary. They remain valid
retail fixed-font cells, but generated English must use an equivalent dynamic
cell when one would otherwise land at that protected edge.

The emitted-byte gate compiles the corpus and decodes records into the same
logical cells consumed by the native reader. It verifies the 12/11 physical
cadence, one-time opening gutter, complete token boundaries, and protected
row-edge rule.

## Fixed layouts and STAFF

A `layout_policy: "fixed"` record remains reviewer-owned because its literal
spacing/composition must not be semantically reflowed. Fixed no longer means
that its renderer family is unknown. The complete current corpus contains 123
fixed translated records, and retail SCN proves a generic renderer contract for
all 123:

- 76 records are displayed only by `0x20`;
- 38 are displayed only by `0x22`;
- 2 are displayed only by `0x23`;
- 3 are the PART1A width-`0x05` `0x24/0x28` countdown; and
- 4 records are deliberately reused by more than one of those already-proven
  families.

The SCN referential-integrity audit requires every fixed record to pass the
applicable native width contract for every renderer that references it. There
are therefore no remaining fixed records whose text placement depends on an
unclassified or bespoke renderer.

STAFF's 62 fixed records remain literal because visual centering is encoded by
source padding, but their renderer is the ordinary proven `0x20` three-strip
path.

Static evidence still cannot prove every live timing, transition, or animation
state. The successor candidate must therefore exercise fixed-layout
representatives in Ares. `PART4C:051` through `PART4C:059` remain an explicit
uninterrupted ending-path runtime checkpoint even though their renderer family
is now fully classified.

## Required evidence for a renderer change

1. Identify the retail SCN command/control path and owning MES record.
2. Express the correction as a general contract, not chapter-specific prose
   padding or a guessed binary coordinate.
3. Add synthetic and corpus-level regressions for cadence, anchors, token
   boundaries, and any changed encoding rule.
4. Run `python -m tools.source_checks --root . --strict-release`.
5. Run complete retail-backed validation and a fresh deterministic build if
   playable bytes change.
6. Replay the affected scene, transitions, page advances, and nearby choices in
   Ares against the exact new candidate hash.

The one existing PART1A Game Hall SCN mutation is a deliberately closed
exception: two exact coordinate bytes are hash-locked and regression-tested
because direct runtime evidence established the defect. It is not precedent for
screenshot-driven chapter patches.

## Release status

Version 1.0.2 remains the latest runtime-certified reference. The maintained
post-1.0.2 source line includes later script, renderer, Game Hall, STAFF, layout,
and production changes and therefore requires its own exact candidate-bound
runtime certification. Read [Current project status](CURRENT_STATUS.md) and
[Release policy](RELEASE.md), rather than treating an older dated revision
report as current status.

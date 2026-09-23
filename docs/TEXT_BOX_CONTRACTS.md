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
| `floating_window` | Valid `0x24` window and `0x27` continuation chain, including selector targets | Width and row limit come from SCN operands. A selector can retain `menu_choice` semantics while using the same physical window. |
| `full_screen_narration` | Reviewed START evidence | Explicit 16-cell full-screen narration contract. |
| `lower_caption` | Reviewed PART2A:093 evidence | Explicit lower-area route-caption contract. |
| `scene_label` | Reviewed PART3C location/speaker evidence | Explicit top scene-label contract. |

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

A `layout_policy: "fixed"` record remains reviewer-owned because a safe general
reflow contract has not been proven. Fixed does not mean unchecked: fixed-width
and capacity rules are part of permanent release validation, and STAFF credits
have their own maintained centering/layout logic and regression coverage.

Static evidence still cannot prove every live centering, clear, transition, or
animation state. The successor candidate must therefore exercise fixed-layout
representatives in Ares. `PART4C:051` through `PART4C:059` remain an explicit
uninterrupted ending-path runtime checkpoint.

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

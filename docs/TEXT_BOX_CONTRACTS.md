# Text-box contracts

## Purpose

Canonical English records are semantic text only. They must not contain
hand-inserted row padding or screenshot-specific line breaks. `scn_layout.py`
derives a named text-box contract from the hash-locked retail SCN, then
`mes_compiler.py` alone wraps, packs, and pads the record for that contract.

This separation means a renderer correction regenerates physical MES rows from
the same English wording; it never requires translation prose to be rewritten
to compensate for stale storage geometry.

## Contract catalogue

| Contract | Evidence | Geometry ownership |
| --- | --- | --- |
| `lower_dialogue` | SCN `0x21 <speaker> <text>` | One initial 12-cell row followed by an 11-cell continuation stride; a retail `0x10` quote cell becomes a one-time blank opening gutter. A three-line page clear does not reset the wider row. |
| `lower_continuation` | SCN `0x21 <text> 0x0000` | Separate lower-box continuation layout; it never receives the opening gutter. |
| `floating_window` | Valid SCN `0x24` text window and its `0x27` chain, including selector targets | Width and row limit derive from the window operands. A selector retains its `menu_choice` role while using the same window geometry. |
| `full_screen_narration` | Reviewed `START` SCN/profile evidence | Explicit 16-cell full-screen narration contract. |
| `lower_caption` | Reviewed `PART2A:093` SCN/profile evidence | Explicit lower-area route-caption contract. |
| `scene_label` | Reviewed `PART3C` location/speaker profile evidence | Explicit top scene-label contract. |

The profile field `text_box_overrides` is permitted only for a reviewed,
nonstandard renderer whose geometry is already supplied by the existing layout
override. It names the renderer; it does not change text, IDs, order, SCN, or
binary boundaries.

## Required evidence for a change

1. Identify the SCN command/control-code path and retail MES record.
2. Add or update the shared contract, not a chapter-specific prose workaround.
3. Add a regression test for row cadence, anchor behavior, and word boundary.
4. Run the full source/health/validation gates.
5. Build from a fresh staging directory and replay an affected scene in Ares,
   including page advances and dialogue transitions.

Static checks prove source and compiler consistency. Ares evidence remains the
release gate for visible spacing, wrapping, and stale-glyph behavior.

## Whole-game emitted-byte gate

`translation_validation.py` does not stop at a source preview. It compiles all
19 chapters in memory and has `mes_compiler.py` decode each adaptive MES stream
into native logical cells. The gate verifies the physical row count and cadence
for every SCN-measured prose record, the one-time lower-dialogue gutter, and
the absence of `02`, `03`, `04`, `05`, `08`, and `11` at a lower-dialogue row
edge. Those fixed bytes take a special native look-ahead path; generated
English must use an equivalent dynamic cell there instead.

Records with no measured prose layout remain explicitly `fixed` and are not
silently reflowed. The emitted-byte gate therefore provides exhaustive compiler
coverage for proven adaptive geometry, while the final Ares route samples every
box type and state transition that could depend on unmodeled live state.

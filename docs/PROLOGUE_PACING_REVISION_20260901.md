# 2026-09-01 prologue pacing and voice revision

## Scope

This reviewed source edit tightens the opening narration and the Indian-poker
prologue without changing card-game mechanics, branch semantics, record order,
or retail provenance. The pass changes 32 canonical records: START:000,
29 PART1A records, and PART1B:002/PART1B:004.

The complete before/after ledger is
`provenance/2026-09-01/prologue_pacing_voice_pass_20260901.json`.

## Localization intent

The original English was broadly source-aligned but made a weak first
impression because the rule explanation was formal and repetitive and Kasuke
and Ilyu's banter was flatter than the Japanese. The revision keeps the
project's established priority order: retail Japanese meaning, correct
speaker/context, natural English, then character/period flavor.

The most important semantic repair is PART1A:017. Ilyu says that she is a
**liar**, not that she is lucky. That restores the intended bluffing joke with
Kasuke's following line about women being liars and makes the poker game serve
as character introduction rather than only as a tutorial.

Kasuke remains an educated conversational professional, with shorter and more
competitive internal thoughts during play. Ilyu remains playful and
cosmopolitan. No phonetic accent or new plot information is introduced.

The post-game exchange is also tightened so the scene ends on Kasuke/Ilyu
chemistry before the date card and the abrupt hijacking transition.

## Validation

Against the prepared hash-locked retail reference:

- all 19 chapters / 2,905 records compiled successfully;
- START rebuilt in its existing fixed archive slot with 228 bytes headroom;
- PART1A rebuilt in its existing fixed archive slot with 28 bytes headroom;
- PART1B rebuilt in its existing fixed archive slot with 256 bytes headroom.

PART1A is therefore capacity-safe but comparatively tight. Avoid gratuitously
lengthening this scene without rerunning retail-backed archive-fit validation.

This source edit is **not** a new runtime certification. Candidate-bound Ares
validation remains required after the broader pending translation-correction
pass is assembled into a new build.

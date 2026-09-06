# 2026-09-01 prologue and early Action 1 dialogue revision

## Historical scope

This dated report records the September 1 pacing/voice pass that began with the
opening narration and Indian-poker prologue and expanded into early Action 1.
The review later became part of the complete-script audit merged into the
maintained successor source line.

## Subsequent status

The original report ended with retail archive-fit and runtime work still pending
for its expanded candidate. That specific pending state is now historical.
Subsequent September work completed the full 19-chapter script audit, retail-
backed renderer/capacity validation, deterministic clean and North American
build proofs for later intermediate candidates, and targeted Ares confirmation
of the Game Hall fix. Later renderer, STAFF, hardening, and production changes
then moved candidate identity again.

Accordingly, do **not** rerun the old prologue-only gate as if it were the
remaining release task. The current successor source requires one fresh final
candidate build and candidate-bound whole-game Ares certification. See
[Current project status](CURRENT_STATUS.md).

## Original scope

The review began as a pacing and voice pass over the opening narration and
Indian-poker prologue. First-play review showed that semantic fidelity alone was
not enough: several scenes were accurate but still stiff, confusing, or
inert in English.

The backward sweep re-reviewed:

- `START`;
- all of `PART1A`;
- all of `PART1B`;
- `PART1C:000` through `PART1C:146`; and
- duplicated / alternate-route Action 1 material in `PART1D`.

`START` was reread under the stricter standard and required no additional change
beyond the already approved opening revision. The original 32-record prologue
ledger remains in
`provenance/2026-09-01/prologue_pacing_voice_pass_20260901.json`.

## Review standard

Fidelity to retail Japanese was treated as the floor rather than the finish
line. Scenes were judged on:

1. source fidelity;
2. first-play comprehension;
3. natural spoken English/pacing;
4. character differentiation/register; and
5. dramatic purpose without flattening deliberate source weirdness.

Source-authored period attitudes, abrasive language, sexual material, racial
prejudice, black comedy, and other uncomfortable content were preserved where
supported. The pass did not modernize every character into the same voice or
invent accents absent from the source.

## Localization intent

A key prologue repair remained `PART1A:017`: Ilyu says she is a **liar**, not
that she is lucky. That restores the bluffing joke with Kasuke's next line and
makes the poker game function as character introduction rather than only a
mechanics tutorial.

Kasuke remained an educated conversational professional with shorter,
competitive thoughts during play. Ilyu remained playful and cosmopolitan.

### Poker prologue

Hand-result banter was naturalized with contractions, prompts, and reactions
while card mechanics and branch semantics stayed unchanged.

### Bridge emergency

Terse reports and orders were made operationally clearer, including direct
identification of the *Nostalgia*, nautical `Hard to port!`, a complete engine-
room warning, and the order `Check the engine room and report back!`.

### Captain / Ashby / crew meeting

The pass deliberately retained Lloyd's pomposity, the Captain's anti-British
bluster, steam-versus-sail argument, California-drawl insult, bone-collector
imagery, shark material, and other source-supported period abrasiveness. The
purpose was readability and cadence, not sanitization.

### Dunant / Ashby scheme

The insurance-fraud causal chain was made explicit:

1. Ashby hires Dunant to recover `The Russian Fog` and identify the culprit.
2. If the real culprit cannot be found, Ashby tells Dunant to frame a crew
   member.
3. Dunant recognizes that a crew-member culprit would void the insurance
   contract.
4. He accepts the arrangement.
5. Ashby approves of Dunant's lack of scruples.

The plot did not change; the English made the existing logic legible on first
play.

### Alternate-route consistency

The sweep found duplicated Action 1 material in PART1D that still used older,
stiffer wording after corresponding PART1C scenes were polished. Verified
duplicate beats were synchronized so alternate routing did not produce an
obviously rougher localization.

## Validation recorded for the original prologue candidate

The initial prologue pass was validated against the prepared hash-locked retail
reference:

- all 19 chapters / 2,905 records compiled;
- START fit its fixed archive slot with 228 bytes headroom;
- PART1A fit with 28 bytes headroom; and
- PART1B fit with 256 bytes headroom.

Those headroom numbers belong only to that historical candidate. The expanded
review changed additional text, so the original report correctly required a
fresh archive-fit check at that time. Later integrated candidates did receive
stronger retail-backed and deterministic build validation; those later hashes
are likewise not the identity of today's final successor candidate.

## Current relevance

The prose-review principles and historical ledger remain useful. The dated
candidate status does not. Current validation commands, corpus counts, CI, and
release requirements are documented in [Development and validation](DEVELOPMENT.md),
[Release policy](RELEASE.md), and [Current project status](CURRENT_STATUS.md).

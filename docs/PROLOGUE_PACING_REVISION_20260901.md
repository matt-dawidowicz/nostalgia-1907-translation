# 2026-09-01 prologue and early Action 1 dialogue revision

## Scope

This review began as a pacing and voice pass over the opening narration and
Indian-poker prologue. It was expanded after first-play review showed that
semantic fidelity alone was not enough: several scenes were technically
accurate but still read as stiff, confusing, or dramatically inert in
English.

The backward sweep re-reviewed the complete material from the opening through
the Dunant/Ashby insurance scheme:

- `START`;
- all of `PART1A`;
- all of `PART1B`;
- `PART1C:000–146`;
- duplicated / alternate-route Action 1 material in `PART1D`.

`START` was re-reviewed under the stricter standard and required no additional
change beyond the already-approved opening revision.

The original 32-record prologue before/after ledger remains at
`provenance/2026-09-01/prologue_pacing_voice_pass_20260901.json`.

## Review standard

Fidelity to the retail Japanese is the floor rather than the finish line. Each
reviewed scene is evaluated independently on five axes:

1. fidelity to the retail Japanese;
2. first-play comprehension;
3. natural spoken English and pacing;
4. character differentiation and register;
5. whether the dramatic purpose of the scene is legible without flattening
   deliberate source weirdness.

Source-authored period attitudes, abrasive language, sexual material, racial
prejudice, black comedy, and other uncomfortable content are preserved when
supported by the Japanese. The pass does not modernize the cast into a uniform
contemporary voice and does not invent accents absent from the source.

## Localization intent

The original English was broadly source-aligned but made a weak first
impression because some explanations were formal or repetitive and some
character dialogue read more like translated prose than speech.

The most important semantic repair in the prologue remains `PART1A:017`.
Ilyu says that she is a **liar**, not that she is lucky. That restores the
intended bluffing joke with Kasuke's following line about women being liars and
makes the poker game serve as character introduction rather than only as a
tutorial.

Kasuke remains an educated conversational professional, with shorter and more
competitive internal thoughts during play. Ilyu remains playful and
cosmopolitan. No phonetic accent or new plot information is introduced.

### Poker prologue

The later hand-result banter now uses more natural contractions, prompts, and
reaction phrasing so the game reads as an exchange between two people rather
than a sequence of mechanically translated outcomes. The card-game mechanics
and branch semantics are unchanged.

### Bridge emergency

A few terse reports and commands were clarified without reducing urgency.
Examples include identifying the *Nostalgia* directly in the hijacking
reaction, using standard nautical `Hard to port!`, making the engine-room
damage report a complete spoken warning, and turning Stone's order into the
operationally clear `Check the engine room and report back!`.

### Captain / Ashby / crew meeting

The Action 1 pass remains deliberately conservative about the scene's stranger
material. Ashby's Lloyd's pomposity, the Captain's anti-British bluster, the
steam-versus-sail argument, the California-drawl insult, bone-collector
imagery, shark material, and abrasive period attitudes are retained. The
revisions target readability and spoken cadence rather than normalizing the
scene into a conventional modern thriller.

### Dunant / Ashby scheme

The insurance-fraud logic is now explicit enough to follow on a first
playthrough:

1. Ashby hires Dunant to recover `The Russian Fog` and identify the culprit.
2. If the real culprit cannot be found, Ashby tells Dunant to **frame one of
   the crew**.
3. Dunant realizes that a crew-member culprit would void the insurance
   contract.
4. He accepts the arrangement.
5. Ashby approves of Dunant's lack of moral scruples.

The Japanese-backed plot remains unchanged; the English now exposes the causal
chain instead of requiring the player to reconstruct it after the fact.

### Alternate-route consistency

The sweep found a route-dependent localization defect: duplicated Action 1
material in `PART1D` still used older, stiffer wording after the corresponding
`PART1C` scenes had been polished. Verified duplicate beats were synchronized
so the alternate route no longer produces a noticeably rougher version of the
same scene.

## Validation

The original prologue pass was validated against the prepared hash-locked
retail reference:

- all 19 chapters / 2,905 records compiled successfully;
- START rebuilt in its existing fixed archive slot with 228 bytes headroom;
- PART1A rebuilt in its existing fixed archive slot with 28 bytes headroom;
- PART1B rebuilt in its existing fixed archive slot with 256 bytes headroom.

Those capacity figures belong to the earlier prologue candidate. The expanded
dialogue sweep changes additional text and therefore requires a fresh
retail-backed archive-fit validation before release, especially because the
earlier `PART1A` candidate had only 28 bytes of fixed-slot headroom.

The expanded source candidate passes repository CI on Ubuntu / Python 3.12 and
Windows / Python 3.14 for source health, manifest verification, maintained
Python compilation, source tests, Ruff, and documentation policy.

This source edit is **not** a new runtime certification. A fresh deterministic
retail build, fixed-slot/capacity audit, and candidate-bound Ares playtest
remain required after the dialogue review is finalized.

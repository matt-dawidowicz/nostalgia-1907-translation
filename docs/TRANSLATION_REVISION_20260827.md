# 2026-08-27 translation and source-fidelity revision

## Status

This document records the post-1.0.2 source revision prepared on 2026-08-27.
The latest **runtime-certified published reference remains version 1.0.2** and
its hash-identified North American build. The current source tree changes the
canonical English and therefore does **not** inherit the 1.0.2 Ares playtest.
No new public release, two-track North American artifact, or runtime
certification is claimed here.

The revision was developed from `main` commit
`c84230633de636987e8d14f3d64636603cfccaf0`. Stable record IDs, record order,
preserve/translate policy, Japanese retail authority, SCN/control data, archive
member order, ISO boundaries, and Track 2 policy remain unchanged.

## Translation revision

The core source-fidelity audit rechecked the complete **2,905-record** corpus
against the retail Japanese evidence. Its approved application changed **345
canonical records**. That number is the semantic-audit application count, not
a count of every later editorial touch: subsequent voice, ending, capacity, and
validator passes intentionally revisited some of the same records.

The later reviewed voice batches comprised:

- 31 Charlie Muffin / Chief Engineer changes;
- 19 Ashby / Voysey / Director changes;
- 23 Kasuke / Ilyu changes that still matched the source-corrected canon;
- 3 secondary-cast changes; and
- 8 direct Japanese-register changes for Chanel, Old Karl, Dunant, Stra, and
  Tianon.

These counts describe reviewed edits, not distinct additional records. Voice
work was layered on top of Japanese meaning; a voice rewrite was rejected when
it would restore an older mistranslation.

The durable localization policy is:

- Japanese semantic evidence outranks fluency, period flavor, or an earlier
  English line.
- Regional speech becomes readable social/regional English without phonetic
  eye dialect. The Chief Engineer's strong Kansai register is represented as
  Western/California working-class speech because PART2E itself contains the
  East-versus-California joke. Charlie remains a rough Eastern-U.S.
  engineer/seaman without an invented city.
- Ashby and the British intelligence cast use class-conscious, institutional
  English rather than a phonetic British accent.
- Kasuke remains an educated conversational professional who becomes blunt
  under pressure; Ilyu remains an educated cosmopolitan woman whose diction
  becomes simpler when emotionally honest.
- No Russian, French, German, or other accent is invented where the Japanese
  does not encode one.

Source-authored oddities are preserved when the evidence supports them. That
includes usages such as `Mayday`, `Indian poker`, `simulation game`, `fiction`,
`Japan's king`, `satellite states`, Ashby's reference to the Queen, the
salaryman joke, the bomb/chastity-belt metaphor, and other deliberate or
anachronistic wording. Historical plausibility is not a license to rewrite the
source.

## Notable semantic repairs

The audit corrected or re-established, among many other records:

- PART2D:111: Ilyu is in the neighboring second-class cabin on the same port
  side; the old invented corridor detail is gone.
- PART2E: the bomb explanation uses **2,000 degrees**, white as neutral, and red
  / blue as the two candidate wires; the Charlie/Chief final gamble preserves
  the source logic.
- PART2F: `Russian Fog`, `British Intelligence Action`, Voysey as Deputy Chief,
  Ashby as its operative, signal `MEDE`, and the Dunant/Ashby relationship are
  source-aligned.
- PART3C: the deadline is **7 p.m.**, roughly 300 uninvolved people remain
  aboard, the submersible escape is retained, and Kasuke's deduction identifies
  Ilyu as the killer of Voysey and Braque while protecting Kirikov / the Russian
  Fog.
- PART4B: Ilyu was **21** when she recognized the regime's effect on her;
  Times/Reuters and Togo/Baltic Fleet references are restored; the unsupported
  Stockholm-syndrome interpretation is removed.
- PART4C: the final confrontation direction and Kirikov/disinformation logic
  are corrected, and PART4C:049 restores `Sorry.` before Kasuke's line about
  being the son of this century's last samurai.

The fixed ending block PART4C:051-PART4C:059 was re-read directly from the
retail Japanese. Its canonical English now includes `No one can catch up...`,
`Can you run with me?`, `No. No spies or salesmen.`, `Don't challenge me...`,
`Foolish men.`, `...alone again...`, and `Here, now.` These nine records remain
`layout_policy: fixed`: static SCN analysis does not prove their live placement
or transition behavior, so an uninterrupted runtime replay of the ending is
still required before a release can certify them.

## Retail-backed capacity and compiler work

Retail-backed compilation exposed constraints that public source CI cannot see
without the original MES/SCN data.

- PART2A:078 was shortened without losing meaning so its floating window stays
  within the proven four-row limit.
- PART3C:017, 114, 132, and 189 were tightened to restore binary reserve while
  preserving the audited facts.
- START:000 was revised and the compiler's fixed English pair dictionary was
  extended with reviewed literal pairs. The visible narration still follows
  the proven six-row full-screen contract.
- The final semantic-validator pass aligned navigation-room terminology,
  shark/evacuation wording, selected short replies, bomb/electrical wording,
  and tracked bomb semantic evidence with the retail source.

The dictionary change is an encoding/capacity optimization only. It does not
change Japanese records, SCN programs, record IDs/order, or the visible meaning
of records merely because a pair receives a fixed code.

## Validation recorded on 2026-08-27

Source-only validation on the clean branch passed on GitHub for both
Windows/Python 3.12 and Ubuntu/Python 3.10. The same source content also passed
locally:

- strict source health: PASS;
- 132 source-only unit tests: PASS;
- maintained-source style audit: 51 files, 0 violations; and
- tracked Python compilation: PASS.

Retail-backed validation used the required Japanese Track 1 with SHA-256
`EFE9A453849F52DC72B7E72EE98D8644882655536E59991C2C85C5A35A41D0E5`.
The prepared retail reference had already verified all **81,909 raw sectors**
and the 19 chapter MES/SCN inputs.

For the final source content before the documentation-only merge preparation:

- the complete retail layout regression suite passed **17/17** tests;
- all **19 chapters / 2,905 records** compiled successfully;
- PART3C compiled to **16,073 bytes (`0x3EC9`)**, below the project's
  `0x3EFF` safety ceiling and the `0x3FFF` absolute boundary;
- all **19 LZ archives** rebuilt successfully;
- minimum remaining archive headroom was **168 bytes**;
- 18 archives used fixed-slot replacement and 1 used guarded reflow.

This evidence proves source, renderer-contract, MES-capacity, and archive-fit
properties for the tested source. It does **not** claim a new full two-track
North American deterministic build or emulator-visible correctness.

## Runtime work still required before a new release

Because the canonical English changed, the historical 1.0.2 playthrough cannot
certify the new playable bytes. Before publishing a successor build:

1. run the complete retail-backed `validate` and deterministic North American
   build using the verified Track 1, unchanged Track 2, and verified U.S. BIOS;
2. record the new candidate hashes and verification manifest;
3. replay the affected scenes in Ares, with an uninterrupted full-frame capture
   of PART4C:051-PART4C:059; and
4. complete the candidate-bound runtime log required by
   [whole-game testing](WHOLE_GAME_TESTING.md).

Until those steps are recorded, version 1.0.2 remains the latest
runtime-certified reference even when this source revision is present on
`main`.

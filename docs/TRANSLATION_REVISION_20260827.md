# 2026-08-27 translation and source-fidelity revision

## Historical scope

This document records the major post-1.0.2 source-fidelity revision prepared on
2026-08-27. The measurements, counts, and capacity figures in the historical
sections below describe that dated revision state; they are provenance, not a
current candidate certification.

## Subsequent status

The maintained source moved substantially beyond this snapshot. In September it
received a complete English-script audit and additional pacing/voice work,
source-verified late-game corrections, shared renderer/runtime fixes, the
hash-locked Game Hall SCN correction, fixed-layout and script-integrity
hardening, STAFF fixes/centering, repository/build hardening, and further
deterministic performance/quality work.

Several later successor candidates passed stronger retail-backed and
deterministic build gates than the August 27 state. Those intermediate hashes do
not certify today's source after later playable/production changes. Version
**1.0.2 therefore remains the latest runtime-certified published reference**.
The exact current release boundary is maintained in
[Current project status](CURRENT_STATUS.md) and [Release policy](RELEASE.md).

## Original revision status

The revision was developed from `main` commit
`c84230633de636987e8d14f3d64636603cfccaf0`. Stable record IDs, record order,
preserve/translate policy, Japanese retail authority, SCN/control data, archive
member order, ISO boundaries, and Track 2 policy remained unchanged.

The core source-fidelity audit rechecked the complete **2,905-record** corpus
against retail Japanese evidence. Its approved application changed **345
canonical records**. That is the semantic-audit application count, not every
later editorial touch; voice, ending, capacity, and validator passes deliberately
revisited some of the same records.

Reviewed voice batches included:

- 31 Charlie Muffin / Chief Engineer changes;
- 19 Ashby / Voysey / Director changes;
- 23 Kasuke / Ilyu changes still consistent with source-corrected canon;
- 3 secondary-cast changes; and
- 8 direct Japanese-register changes for Chanel, Old Karl, Dunant, Stra, and
  Tianon.

These counts describe reviewed edits, not distinct additional records.

## Translation policy established by the revision

The durable localization rules established here remain active:

- Japanese semantic evidence outranks fluency, period flavor, or an earlier
  English line.
- Regional speech becomes readable social/regional English without phonetic eye
  dialect.
- The Chief Engineer's strong Kansai register is represented as
  Western/California working-class speech because PART2E contains an explicit
  East-versus-California joke.
- Charlie remains a rough Eastern-U.S. engineer/seaman without an invented city.
- Ashby and the British intelligence cast use class-conscious institutional
  English rather than a phonetic British accent.
- Kasuke remains an educated conversational professional who becomes blunter
  under pressure.
- Ilyu remains an educated cosmopolitan woman whose diction simplifies when she
  becomes emotionally candid.
- No Russian, French, German, or other accent is invented when the Japanese does
  not encode one.

Source-authored oddities remain authoritative when the evidence supports them,
including `Mayday`, `Indian poker`, `simulation game`, `fiction`, `Japan's
king`, `satellite states`, Ashby's Queen reference, the salaryman joke, and the
bomb/chastity-belt metaphor.

## Notable semantic repairs

The August 27 audit corrected or re-established, among many other records:

- `PART2D:111`: Ilyu is in the neighboring second-class cabin on the same port
  side; an invented corridor detail was removed.
- PART2E bomb logic: **2,000 degrees**, white as neutral, red/blue as the two
  candidate wires, and source-correct Charlie/Chief gamble semantics.
- PART2F: `Russian Fog`, `British Intelligence Action`, Voysey as Deputy Chief,
  Ashby as its operative, signal `MEDE`, and the Dunant/Ashby relationship.
- PART3C: a **7 p.m.** deadline, roughly 300 uninvolved people aboard, the
  submersible escape, and Kasuke's deduction that Ilyu killed Voysey and Braque
  while protecting Kirikov / Russian Fog.
- PART4B: Ilyu was **21** when she recognized the regime's effect on her;
  Times/Reuters and Togo/Baltic Fleet references were restored; an unsupported
  Stockholm-syndrome interpretation was removed.
- PART4C: final-confrontation direction and Kirikov/disinformation logic were
  corrected, and `PART4C:049` restored `Sorry.` before Kasuke's last-samurai
  line.

The fixed ending block `PART4C:051` through `PART4C:059` was reread directly
from retail Japanese. Its corrected English includes the reviewed beats
`No one can catch up...`, `Can you run with me?`, `No. No spies or salesmen.`,
`Don't challenge me...`, `Foolish men.`, `...alone again...`, and `Here, now.`
Those records remain an explicit uninterrupted runtime checkpoint because fixed
layout does not gain complete live placement/transition proof from static SCN
geometry alone.

## Retail-backed capacity/compiler work in the August 27 state

Retail-backed compilation exposed constraints that source-only CI could not see:

- `PART2A:078` was shortened to remain within its proven four-row window.
- `PART3C:017`, `114`, `132`, and `189` were tightened to restore binary reserve
  without changing audited facts.
- `START:000` was revised and reviewed fixed English pairs were added for
  capacity; the visible narration retained its proven six-row contract.
- semantic validation aligned navigation-room, shark/evacuation,
  bomb/electrical, and short-reply terminology with source evidence.

The dictionary work was a storage optimization only; it did not make SCN,
record-order, or semantic changes by itself.

## Validation recorded on 2026-08-27

At that point, source-only validation was reported green on Windows/Python 3.12
and Ubuntu/Python 3.10. Those interpreter/CI details are historical; the current
source contract uses Python 3.12+ and a different CI matrix.

Retail-backed evidence for that dated state included:

- exact Japanese Track 1 SHA-256
  `EFE9A453849F52DC72B7E72EE98D8644882655536E59991C2C85C5A35A41D0E5`;
- all **81,909 raw sectors** in the prepared retail reference verified;
- the complete retail layout regression suite: **17/17**;
- all **19 chapters / 2,905 records** compiled;
- PART3C size **16,073 bytes (`0x3EC9`)**, below the project's `0x3EFF` safety
  ceiling and `0x3FFF` absolute boundary;
- all **19 LZ archives** rebuilt;
- minimum remaining archive headroom **168 bytes**; and
- 18 fixed-slot replacements plus 1 guarded reflow.

Those results prove properties of the August 27 source. Later commits supersede
the exact candidate identity and some implementation details.

## Runtime boundary, then and now

The August 27 revision changed canonical English, so the historical 1.0.2 Ares
playthrough could never certify it. Later work did complete additional
retail-backed builds and targeted runtime checks, but subsequent changes mean the
current successor line still needs one final exact candidate certification.

For a successor release today:

1. freeze the exact source commit;
2. run the complete current source and retail-backed validation path;
3. perform the maintained two-clean-build and two-region-build deterministic
   process;
4. record final ISO, North American Track 1, Track 2, CUE, and verification
   hashes;
5. generate the candidate-bound whole-game plan; and
6. complete/verify the Ares runtime log, including uninterrupted
   `PART4C:051`-`PART4C:059` coverage.

Do not use the historical figures in this document as a substitute for those
final-candidate gates.

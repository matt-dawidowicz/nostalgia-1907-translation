# Whole-game test certification

`whole_game_test.py` separates exhaustive automatic validation from the live
evidence that only an emulator playthrough can provide. It never modifies
translation text, Japanese data, SCN controls, or a disc image.

## Current successor-source status

The maintained source is the cumulative post-1.0.2 successor line described in
[`CURRENT_STATUS.md`](CURRENT_STATUS.md). The runtime-certified 1.0.2 reference
cannot certify it because the successor line includes changed canonical English,
renderer/runtime corrections, STAFF layout changes, and later production-path
work.

Several intermediate successor candidates have strong retail-backed and
runtime-targeted evidence. That evidence remains useful for regression history,
but the final release claim must bind to a freshly built candidate from one
frozen exact source commit.

## 1.0.2 release evidence

The hash-identified North American 1.0.2 reference completed a full maintainer
playtest in Ares with no reported defects. That completed playthrough is release
evidence for the unchanged reference only. The Ares version was not recorded,
so do not invent one when reporting the historical evidence.

## Automatic gate

The whole-game plan is generated only after the static corpus gate succeeds. It
covers all 19 chapters and all 2,905 canonical records through the maintained
renderer, script-integrity, and compilation contracts. Static validation
includes adaptive/fixed layout ownership, physical cursor cadence, opening
gutters, dynamic references, row-edge rules, pointer/glyph capacity, fixed
binary boundaries, SCN-to-MES references, and the generated route/choice
inventory.

This gate is deliberately fail-closed. A missing or invalid static summary
blocks a runtime plan instead of reducing the required playtest scope.

## Runtime certification for a new candidate

Generate the plan from the exact candidate that will be tested:

```powershell
python -m work.clean_rebuild.whole_game_test `
  --cue <candidate.cue> `
  --track1 <candidate_Track1.bin> `
  --output <empty-output-directory>
```

The generated log remains `PENDING_RUNTIME` until the tester records evidence
for all generated scopes, including:

- boot and a fresh-game start;
- multi-page dialogue and page advances;
- speaker/dialogue and text-box transitions;
- choices and all generated route/branch coverage;
- every chapter required by the plan;
- every maintained text-box contract and required fixed-layout observation;
- save/reload followed by normal progression and audio; and
- the ending path.

`PART4C:051` through `PART4C:059` remain an explicit uninterrupted ending-path
checkpoint. Their static source/layout evidence is strong, but the live
placement and transition sequence still requires runtime observation.

Verification also requires exact candidate CUE and Track 1 filenames and
64-character uppercase SHA-256 hashes. Every scope marked complete must contain
a non-empty evidence note, and the runtime issue inventory must be empty.
Deleting a generated scope is an error, not a way to narrow certification.

After the log has been filled, verify it without modifying it:

```powershell
python -m work.clean_rebuild.whole_game_test --verify whole_game_runtime_log.json
```

`PASS` means the generated static inventories and declared runtime evidence for
that exact candidate are complete. It cannot be inherited by a candidate with
different playable bytes.

## Defect reporting

A screenshot may help identify a symptom, but it is not sufficient evidence by
itself. Record:

- candidate Track 1/CUE identity;
- Ares version;
- chapter and route/choice context;
- stable record ID or first visible words;
- whether the defect followed a page advance, transition, or reload; and
- a concise description of expected versus observed behavior.

If a defect changes source or production code, rebuild the candidate and start
a new candidate-bound certification cycle.

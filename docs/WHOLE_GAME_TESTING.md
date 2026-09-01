# Whole-game test certification

`whole_game_test.py` separates exhaustive automatic validation from the live
evidence that only an emulator playthrough can provide. It never modifies
translation text, Japanese data, SCN controls, or a disc image.

## Current post-1.0.2 source status

The 2026-08-27 source revision changes canonical English and therefore cannot
reuse the 1.0.2 runtime result. Its source and retail-backed static gates are
green, but its runtime log remains pending. In particular, replay
PART4C:051-PART4C:059 in one uninterrupted ending sequence because those fixed
records have no statically proven SCN geometry. See
[the revision record](TRANSLATION_REVISION_20260827.md).

## 1.0.2 release evidence

The hash-identified North American reference completed a full maintainer
playtest in Ares with no reported defects. That completed playthrough is release
evidence for the unchanged reference, not a reason to discourage further
testing. Independent and regression playtests are welcome, and every candidate
with changed playable bytes requires fresh, candidate-bound runtime evidence.

The historical published metadata identifies that reference as the 1.0.2 release. The exact
reference Track 1 hash and the recorded scope belong in
[the release policy](RELEASE.md). The Ares version was not recorded, so do not
invent a version number when reporting this historical evidence.

## Automatic gate

The plan compiles all 19 chapters against their hash-locked retail MES/SCN
inputs. This exercises all 2,905 records and the emitted-byte renderer audit:
adaptive wrapping, physical cursor cadence, lower-dialogue opening gutters,
dynamic references, native row-edge bytes, pointer bounds, glyph capacity, and
the PART3C binary boundary. A failure blocks plan generation.

## Runtime certification for a new candidate

For a newly built candidate, the generated log remains `PENDING_RUNTIME` until
the tester records:

- boot and a fresh-game start;
- multi-page dialogue, box/speaker transitions, choices, save/reload, and the
  ending path;
- every chapter archive reached through every available route/choice branch;
- every known text-box contract; and
- any fixed-layout record observed in the route.

Verification is fail-closed. A runtime log cannot pass unless it retains the
supported plan schema, successful static layout and emitted-renderer summaries,
the complete generated global/chapter/text-box inventories, and an empty runtime
issue list. It must also bind the playtest to exact CUE and Track 1 filenames and
64-character uppercase SHA-256 hashes. Every scope marked complete must include
a non-empty evidence note; deleting a generated certification scope is an error,
not a way to reduce the required coverage.

This is intentionally stricter than a screenshot gallery. A screenshot is
optional for routine success, but a defect report must identify the chapter,
route or choice, first visible words, and whether it followed a page advance,
transition, or reload.

Generate a candidate-bound plan from the supplied test build:

```powershell
python work\clean_rebuild\whole_game_test.py `
  --cue <candidate.cue> `
  --track1 <candidate_Track1.bin> `
  --output <empty-output-directory>
```

After the log has been filled, verify it without modifying it:

```powershell
python work\clean_rebuild\whole_game_test.py --verify whole_game_runtime_log.json
```

`PASS` means the static corpus gate and all declared runtime evidence for that
candidate are complete. It is not a substitute for investigating a reported
defect, and it cannot be inherited by a candidate with different playable
bytes.

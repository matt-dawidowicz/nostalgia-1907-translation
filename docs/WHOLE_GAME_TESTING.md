# Whole-game test certification

`whole_game_test.py` separates exhaustive automatic validation from the live
evidence that only an emulator playthrough can provide. It never modifies
translation text, Japanese data, SCN controls, or a disc image.

## Automatic gate

The plan compiles all 19 chapters against their hash-locked retail MES/SCN
inputs. This exercises all 2,905 records and the emitted-byte renderer audit:
adaptive wrapping, physical cursor cadence, lower-dialogue opening gutters,
dynamic references, native row-edge bytes, pointer bounds, glyph capacity, and
the PART3C binary boundary. A failure blocks plan generation.

## Runtime certification

The generated log remains `PENDING_RUNTIME` until the tester records:

- boot and a fresh-game start;
- multi-page dialogue, box/speaker transitions, choices, save/reload, and the
  ending path;
- every chapter archive reached through every available route/choice branch;
- every known text-box contract; and
- any fixed-layout record observed in the route.

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

`PASS` means the static corpus gate and all declared runtime evidence are
complete. It is not a substitute for investigating a reported defect.

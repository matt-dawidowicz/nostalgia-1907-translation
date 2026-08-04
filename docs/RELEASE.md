# Release and playtest policy

## Current build line

`Nostalgia1907_CleanRebuild_v33_EdgeCases_NorthAmerica` is the current North
American build line. It was created from the canonical source through two
independent byte-identical clean rebuilds followed by two byte-identical North
American region builds.

The v33 candidate has passed targeted runtime review of the dialogue renderer,
including page advances and dialogue transitions. This is strong evidence for
the shared formatter, not a claim that every scene and branch has been played.
Future issues belong in a new version with their own source change, tests,
clean staging directory, build hashes, and runtime evidence.

## What a release proves

A successful `nostalgia1907.py build` proves that:

- the supplied Japanese Track 1 and Track 2 match their required hashes;
- the canonical source, compiler, format code, and configuration pass the
  automated validation gate;
- two independent clean builds are byte-identical;
- two independent North American region builds are byte-identical;
- fixed disc boundaries, SCN data, Track 2, and required raw-CD checks remain
  intact; and
- the final verification manifest binds the delivery files to those inputs.

It does not prove visual behavior in an emulator. Manual playtesting is still
required before public release.

## Required manual checks

For every candidate, use the generated `.cue` file in Ares with the verified
U.S. Sega CD BIOS. Check the affected scenes and at least one representative of
each text-box type:

1. Advance every page in a multi-page lower dialogue box.
2. Cross at least one speaker or dialogue transition.
3. Inspect adaptive, fixed, compact-label, and anchor text records.
4. Save and reload once, then confirm normal progression and audio.
5. Capture a screenshot and record the chapter/record IDs for any defect.

Use [whole-game testing](WHOLE_GAME_TESTING.md) when scheduling a broader
playthrough. Do not treat static validation as runtime proof.

## Publishing checklist

Before publishing a build or patch:

1. Run source-only tests, source health, and `nostalgia1907.py validate`.
2. Build from a new, empty staging directory.
3. Confirm the final verification manifest reports both deterministic stages.
4. Complete the affected Ares checks above.
5. Publish only source, documentation, checksums, and legal instructions—not
   a BIOS or copyrighted game image.

# Release and playtest policy

## Runtime-reviewed reference

The North American artifact with Track 1 SHA-256
`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`
is the runtime-reviewed reference for the current renderer contracts. Its
unchanged Track 2 SHA-256 is
`F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991`.
The exact hashes are the durable identity; former private build-number labels
are deliberately not used in public-facing documentation.

Prior verification reports state that the artifact was created through two
independent byte-identical clean rebuilds followed by two byte-identical North
American region builds. The current source-hardening build produced the same
playable Track 1 bytes.

The project maintainer completed a full playtest of this exact Track 1 in
Ares. It included the targeted dialogue-renderer checks, page advances, and
dialogue transitions; no defect was reported during the playthrough. This is
the current runtime evidence for the release reference. Independent and future
regression playtests are welcome, especially for alternate choices, emulator
versions, hardware, and newly reported routes.

A source-only checkout cannot independently replay the emulator session or
re-prove the excluded artifact hashes. Every candidate whose playable bytes
change must generate fresh verification reports and new runtime evidence tied
to its exact hashes.

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

It does not prove visual behavior in an emulator. Manual playtesting remains
required whenever playable bytes change or a release claims broader runtime
coverage than the reference above.

## Required manual checks

For every changed candidate, use the generated `.cue` file in Ares with the
verified U.S. Sega CD BIOS. Check the affected scenes and at least one
representative of each text-box type:

1. Advance every page in a multi-page lower dialogue box.
2. Cross at least one speaker or dialogue transition.
3. Inspect adaptive, fixed, compact-label, and anchor text records.
4. Save and reload once, then confirm normal progression and audio.
5. Record the candidate Track 1 hash, Ares version, route or chapter coverage,
   and the chapter/record IDs for any defect.

Use [whole-game testing](WHOLE_GAME_TESTING.md) when scheduling an independent
or regression playthrough. Do not treat static validation as runtime proof, and
do not reuse the reference playtest as evidence for a candidate whose playable
bytes have changed.

## Publishing checklist

Before publishing a build or patch:

1. Run `python tools/source_health.py --root . --strict-release`, the source-only test suite,
   the style/Black checks, and `python nostalgia1907.py validate`.
2. Build from a new, empty staging directory.
3. Confirm the final verification manifest reports both deterministic stages.
4. Complete and record the required Ares checks for any changed playable bytes.
5. Publish only source, documentation, checksums, and legal instructions, not a
   BIOS or copyrighted game image.

Public source collaboration can review and test synthetic/compiler changes
without retail media. Only a maintainer with the hash-verified retail tracks
and licensed BIOS can certify the retail-backed and region-build gates, and
only recorded Ares evidence can certify visible runtime behavior.

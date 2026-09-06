# Release and playtest policy

## Current source status

Version **1.0.2 remains the latest runtime-certified published reference**.
The maintained source is the cumulative post-1.0.2 successor line described in
[`CURRENT_STATUS.md`](CURRENT_STATUS.md). It includes the August source-fidelity
revision plus later complete-script editing, renderer/runtime corrections,
fixed-layout and script-integrity hardening, STAFF centering, repository/build
hardening, and deterministic performance changes.

Because playable bytes changed after 1.0.2, the current source does **not**
inherit the historical 1.0.2 Ares result. Several intermediate successor
candidates completed retail-backed deterministic proofs, but later changes mean
those hashes are development evidence, not the release identity of the current
source. A successor release must freeze one exact final commit and certify the
products built from that exact source.

## Runtime-reviewed reference

The North American 1.0.2 artifact with Track 1 SHA-256
`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`
is the current runtime-reviewed reference. Its unchanged Track 2 SHA-256 is
`F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991`.

Prior verification reports state that the reference was created through two
independent byte-identical clean rebuilds followed by two byte-identical North
American region builds. The project maintainer completed a full playtest of
this exact Track 1 in Ares with no reported defect. The historical record does
not include an Ares version number; future reports must record their own version
rather than supplying one retroactively.

A source-only checkout cannot replay that emulator session or re-prove excluded
artifact hashes. Every candidate whose playable bytes differ needs fresh
verification reports and runtime evidence tied to its own exact hashes.

## What a build proves

A successful `nostalgia1907.py build` proves that:

- the supplied Japanese Track 1 and Track 2 match their required hashes;
- canonical source, production code, and configuration pass the maintained
  validation gates;
- two independent clean builds are byte-identical;
- two independent North American region builds are byte-identical;
- fixed disc boundaries, the guarded SCN mutation contract, Track 2, and raw-CD
  integrity remain intact; and
- final verification binds the delivery files to declared inputs and hashes.

Authenticated unchanged raw sectors may inherit checksum evidence by exact
identity to the verified retail reference; changed sectors are regenerated and
checked directly. This is a preservation proof, not an emulator-behavior claim.

A successful build does **not** prove visible window clearing, timing,
transitions, branch behavior, save/reload behavior, or emulator compatibility.

## Source gate before a release build

Install the development tools and run the one maintained source contract:

```powershell
python -m pip install -r requirements-dev.txt
python -m tools.source_checks --root . --strict-release
```

If tracked source changed, regenerate `MANIFEST.sha256` first:

```powershell
python tools/source_manifest.py --root . --write
python -m tools.source_checks --root . --strict-release
```

Do not substitute an older hand-copied list of source-health, Black, style, or
lint commands. The unified gate is authoritative and includes Ruff format,
Ruff lint, mypy, production-dependency, manifest, test, compilation, and
public-API documentation checks.

## Successor release procedure

Freeze an exact commit before beginning candidate certification. Then:

1. run `python nostalgia1907.py doctor`;
2. run `python nostalgia1907.py prepare` against the verified retail Track 1;
3. run `python nostalgia1907.py validate`;
4. run the normal North American `build` from new, empty staging/delivery roots;
5. confirm both clean builds and both region builds agree;
6. record final translated ISO, Track 1, Track 2, CUE, aggregate input
   fingerprint, and verification-manifest identities;
7. generate a candidate-bound whole-game runtime plan;
8. complete the Ares runtime log for the exact candidate; and
9. verify the completed runtime log before publishing a new version.

Any source or production-path change after the freeze creates a different
candidate and resets the build/runtime certification obligation. Documentation-
only changes do not change playable bytes, but they must still keep
`MANIFEST.sha256` and source CI synchronized.

## Required manual checks

For every changed playable candidate, use the generated `.cue` in Ares with the
verified U.S. Sega CD BIOS. The generated whole-game plan is authoritative for
scope. At minimum the evidence must cover:

1. boot and a fresh-game start;
2. multi-page lower dialogue and page advances;
3. speaker/dialogue and text-box transitions;
4. choices and the generated route/branch inventory;
5. every chapter required by the generated plan;
6. representative adaptive and fixed layouts plus all required text-box
   contracts;
7. save and reload followed by normal progression and audio; and
8. the ending path.

`PART4C:051` through `PART4C:059` require one uninterrupted ending-sequence
observation because their fixed placement/transition behavior is not completely
proved by static SCN geometry.

Record the candidate Track 1 hash, CUE identity, Ares version, route/chapter
coverage, evidence notes, and any defect IDs. Do not treat screenshots as a
substitute for the structured runtime log.

## Publishing checklist

Before publishing a build or patch:

1. confirm the exact frozen source commit and a green unified source gate;
2. confirm the complete retail-backed `validate` path passed;
3. build from new, empty staging/delivery roots;
4. confirm the final verification manifest reports both deterministic stages;
5. complete and verify the candidate-bound Ares runtime log;
6. ensure the runtime issue inventory is empty; and
7. publish only source, documentation, checksums, and legal instructions, not a
   BIOS or copyrighted game image.

Public source collaboration can review and test synthetic/compiler changes
without retail media. Only a maintainer with the hash-verified retail tracks
and licensed BIOS can certify the retail-backed and region-build gates, and
only recorded Ares evidence can certify visible runtime behavior.

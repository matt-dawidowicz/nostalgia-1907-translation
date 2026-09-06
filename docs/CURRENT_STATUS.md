# Current project status

Last synchronized: 2026-09-06.

This document is the authoritative current-state summary for the maintained
source tree. Dated revision and maintenance reports under `docs/` and
`provenance/` are historical snapshots; they remain useful evidence, but their
then-current test counts, candidate hashes, and pending-work lists must not be
read as the status of today's source.

## Published runtime reference

Version **1.0.2** remains the latest runtime-certified published reference. Its
North American Track 1 SHA-256 is:

`1D99B456DA49F3F98B059B5E5DBAA6075DDE762C91448ABF20485B098E565C17`

Its unchanged Track 2 SHA-256 is:

`F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991`

That exact 1.0.2 Track 1 completed the recorded full maintainer Ares playthrough.
The historical evidence belongs only to those exact bytes; it cannot certify a
later candidate whose playable bytes differ.

## Current successor source line

The maintained source is no longer accurately described as only the
"2026-08-27 revision." It is the cumulative post-1.0.2 successor line. It now
includes:

- the 2026-08-27 full-corpus Japanese source-fidelity and character-voice audit;
- the September 1-2 complete English-script audit and pacing/voice polish;
- source-verified late-game dialogue corrections and terminology consistency;
- shared lower-dialogue continuation and apostrophe-spacing fixes;
- the hash-locked two-byte PART1A Game Hall selector correction confirmed in
  Ares;
- complete retail-backed layout and script-integrity gates, including fixed
  layouts, SCN-to-MES references, choice branches, and preserved-record render
  identity;
- STAFF credit corrections and centering;
- defensive build/path/capacity/verification hardening and removal of obsolete
  maintenance code;
- deterministic rebuild performance work; and
- repository-wide Ruff formatting/linting, PEP 257 enforcement, and a mypy
  ratchet.

The canonical corpus remains **19 chapters / 2,905 records**, currently
**2,883 translated and 22 deliberately preserved**.

## Source-validation state

The maintained public source gate is:

```text
python -m tools.source_checks --root . --strict-release
```

It performs source-health and exact tracked-inventory checks, verifies
`MANIFEST.sha256`, audits the production dependency boundary, compiles maintained
Python, runs the source-only unit suite, checks Ruff formatting and lint, runs
the maintained mypy targets, and enforces the public-API documentation policy.

Current CI runs the complete source gate on Ubuntu/Python 3.12 and
Windows/Python 3.14, with additional compile/unit compatibility coverage on
Ubuntu/Python 3.13 and 3.14. The source tree entering this documentation sync
was `919f9f9e226132cc9816136ff7e59c4472851f2d`, whose Source Checks run was
green.

## What is complete

The project has strong static and deterministic evidence for the maintained
translation/build architecture. Completed work includes full-corpus source
review, renderer/layout enforcement, fixed-layout promotion, script-reference
integrity, archive/ISO/raw-CD preservation guards, deterministic packaging,
source-only CI, and focused Ares confirmation of the Game Hall renderer defect
that was repaired.

Several intermediate successor candidates also completed retail-backed
compilation and deterministic build proofs. Those hashes are historical
development evidence only. They are not the release identity of the current
source because later playable or production-path changes were integrated.

## What is still required for a successor release

The next release gate is **candidate certification, not another general
modernization campaign**. Freeze an exact source commit and, using the verified
retail tracks and U.S. BIOS:

1. run `doctor`, `prepare`, and the complete `validate` path;
2. run the normal build and record the exact two-clean-build and two-region-build
   deterministic evidence;
3. record the final translated ISO, North American Track 1, unchanged Track 2,
   CUE, and verification-manifest hashes;
4. generate the candidate-bound whole-game runtime plan;
5. complete and verify the Ares runtime log for that exact candidate; and
6. publish a successor version only after the runtime log passes with no open
   issues.

`PART4C:051` through `PART4C:059` remain an explicit uninterrupted ending-path
runtime checkpoint because those fixed-layout records do not obtain complete
live placement/transition proof from static SCN geometry alone. Normal
whole-game coverage must also exercise page advances, dialogue/box transitions,
choices, save/reload, every chapter/route inventory required by the generated
plan, and the maintained text-box contracts.

Until that exact final-candidate evidence exists, **1.0.2 remains the only
runtime-certified published reference**.

## Change policy during release freeze

Once a candidate is frozen, avoid unrelated source or production changes. A
real defect found by validation or Ares should be fixed with the smallest
source-supported change, regression coverage should be added, and the candidate
must then be rebuilt and re-certified because its identity changed.

Documentation-only corrections may proceed when they do not alter playable
bytes, but `MANIFEST.sha256` and the source gate must remain synchronized.

# Historical maintenance, verification, rollback, and cleanup report

Date: 2026-08-02

Comparison base: commit `a2fca0c` (`Publish revised translation and tooling`)

Retained candidate: North American maintenance reference

Architectural baseline: validated clean-rebuild architecture

## How to read this report now

This document preserves the measurements and decisions of the August 2
maintenance state. Its exact test counts, corpus split, build hashes, file
counts, and pending-work language are **historical values**, not the current
source contract.

Subsequent work completed the full 1.0.2 maintainer Ares playthrough and later
created a cumulative post-1.0.2 successor line with additional translation,
renderer, Game Hall, fixed-layout, STAFF, hardening, performance, and source-
quality changes. Version 1.0.2 remains the latest runtime-certified published
reference; the current successor still requires final candidate-bound build and
Ares certification. Use [Current project status](CURRENT_STATUS.md) and
[Release policy](RELEASE.md) for current claims.

## Historical release decision

The maintenance reference was retained as the North American playtest candidate.
A later renderer experiment introduced additional runtime layout regressions and
was retired rather than promoted. None of its generated BIN/CUE or run
directories became a build input.

At the time of this report, manual testing had established fixes for stale-letter
clearing and leading indentation while some spacing behavior still needed
runtime review. That pending language is intentionally preserved as the state of
August 2; later 1.0.2 playtesting superseded it.

North America was established as the normal default region, with Japan retained
as an explicit diagnostic path.

## Retained-candidate provenance and hashes

The historical maintenance source was compared against the retained candidate's
clean-delivery verification manifest. All 52 workspace source/configuration/
production/validation files in that comparison matched byte-for-byte; the full
input manifest contained 115 files after retail/prepared inputs were included.

| Evidence | Historical value |
| --- | --- |
| Aggregate clean-build input fingerprint | `9F065F96122C9D15B2D86718142D5EC6BB0E205A3329CAD5E181A7C6890B3827` |
| Independent clean builds | 2; byte-identical |
| Clean artifacts compared | 48 |
| Independent North American wrappers | 2; byte-identical |
| Clean logical ISO SHA-256 | `28AC56F89E53B3891A3B9CE805DCBBD149932DB888B0FE2E1819CAD8E87EF606` |
| North American logical ISO SHA-256 | `E6DDFC9CD0A1877E208FA5DF541F5719015E7245FE61BDD87C4121F117BD8C12` |
| North American Track 1 SHA-256 | `386461E409E391FF78A81C21533708D01E3AEB9242214D9998BDC307DDC321A1` |
| Track 2 SHA-256 | `F17C698255DA74F725A51EFC1119445E719A00A654BA6815E5C4729677347991` |
| North American CUE SHA-256 | `CCFBDD75FF464DD57B06CBD32B5263BD794BE8059019E19E3F5172B42BAEE9BE` |

These hashes identify that dated candidate only. They are not the identity of
1.0.2's later runtime-reviewed Track 1 and are not the identity of the current
successor source.

The region wrapper changed only raw sectors 0 through 4, preserved the relocated
original boot payload, left later raw sectors and Track 2 byte-identical, and
did not alter translation records, ISO extents, or unrelated archive content.

## Canonical translation changes in that historical state

At the August 2 snapshot the inventory was **19 chapters / 2,905 records** with
**2,882 translated and 23 preserved**. That split is intentionally recorded as
historical; current canonical policy is **2,883 translated / 22 preserved**.

Exactly 377 translated record texts had changed since the report's comparison
base:

- 369 adopted the then-reviewed compact ellipsis convention; and
- 8 received specific wording changes, including the reviewed contractions and
  bomb-wire instructions recorded in the original maintenance work.

The exact historical chapter-by-chapter count remains useful for reconciling
that maintenance transition, but it is not a target count for current source.

## Renderer/compiler outcome from the maintenance state

The durable discoveries promoted from that work included:

- separating physical runtime cells from prose-visible cells;
- modeling lower-dialogue opening and continuation geometry explicitly;
- emitting the English replacement for the Japanese opening-quote gutter only
  once per dialogue stream;
- keeping other prose boxes on their own SCN-derived geometry;
- rejecting word splits, row overflow, invalid geometry, and shifted text at
  renderer boundaries; and
- making canonical JSON updates transactional with explicit recovery behavior.

Later Ares investigations refined the lower-dialogue contract further by
establishing the protected row-edge fixed codes and native 11-cell continuation
stride; later still, apostrophe spacing was normalized. Read
[Adaptive renderer assessment](ADAPTIVE_RENDERER_ASSESSMENT.md) for that
historical chain and [Text-box contracts](TEXT_BOX_CONTRACTS.md) for the current
contract.

## Build/verification hardening established or foreshadowed here

The maintenance work established several long-lived policies:

- North America as the normal build target;
- repeated clean builds and region wrappers before publication;
- rejection of occupied/overlapping unsafe output roots;
- cryptographic binding of declared inputs and managed outputs;
- exact output inventory checks; and
- source-only review that excludes retail/game media.

Later repository work substantially strengthened these controls: current code
also rejects destructive source/output aliasing, uses typed archive-capacity
failures, validates tighter fixed-layout/script-integrity contracts, centralizes
production-dependency checks, and runs a unified source gate.

## Historical source-tree cleanup

The report recorded removal of rejected renderer experiments, obsolete delivery
copies/run directories, ignored generated media, build/dump trees, and probe
directories. Those were local ignored/untracked artifacts rather than Git source
deletions.

No retail BIN/CUE/ISO/MES/SCN/LZ/FNT/PCM/WAV/PNG product became part of the
source release. That source-only boundary remains current.

## Verification captured for the August 2 state

The historical Windows/Python 3.12 run reported, among other checks:

- source-health PASS;
- Python compilation PASS;
- 95 maintained unit tests PASS;
- `doctor` PASS for configured retail prerequisites;
- full `validate` PASS;
- renderer-aware corpus audit PASS;
- deterministic bilingual comparison PASS; and
- semantic/generated-artifact validation PASS.

Those exact test counts and tool internals have since changed. Do not use them to
judge current CI health; run the current unified gate:

```text
python -m tools.source_checks --root . --strict-release
```

## Subsequent runtime result

The later hash-identified **1.0.2** North American reference—not the older Track
1 hash listed in this report—completed the recorded full maintainer Ares
playthrough. That later exact Track 1 is documented in
[Current project status](CURRENT_STATUS.md). It is legitimate whole-game runtime
evidence for 1.0.2 only, and it does not transfer to the changed successor
candidate.

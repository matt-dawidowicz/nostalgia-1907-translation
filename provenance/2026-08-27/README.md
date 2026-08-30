# 2026-08-27 translation revision provenance

This directory preserves reviewed change ledgers for the post-1.0.2
source-fidelity and character-voice revision. The JSON files are historical
review evidence, not canonical translation source and not build inputs.

Canonical English remains under `work/clean_rebuild/sources/`. The authoritative
human-readable revision summary is
[`docs/TRANSLATION_REVISION_20260827.md`](../../docs/TRANSLATION_REVISION_20260827.md).

The ledgers record the major review passes that produced the current source:
semantic corrections, character/register passes, the PART4C ending correction,
retail capacity/layout reserve fixes, and final semantic-validator repairs.
They are retained so future maintainers can understand why source changed
without keeping the one-off applicator/report scripts that created intermediate
states.

Do not import these files from production code or edit them as a substitute for
a canonical wording change. New changes use stable record IDs through
`nostalgia1907.py edit`, followed by normal validation and candidate-bound
runtime evidence when playable bytes change.

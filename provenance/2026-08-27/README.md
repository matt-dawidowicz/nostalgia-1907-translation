# 2026-08-27 translation revision provenance

This directory preserves reviewed change ledgers for the major post-1.0.2
source-fidelity and character-voice revision performed on 2026-08-27. The JSON
files are historical review evidence, not canonical translation source and not
build inputs.

Canonical English remains under `work/clean_rebuild/sources/`. The authoritative
human-readable summary of this dated revision is
[`docs/TRANSLATION_REVISION_20260827.md`](../../docs/TRANSLATION_REVISION_20260827.md).
For current project/release status, use
[`docs/CURRENT_STATUS.md`](../../docs/CURRENT_STATUS.md).

The ledgers record the semantic corrections, character/register passes,
PART4C ending correction, retail capacity/layout reserve fixes, and semantic-
validator repairs that formed the August 27 revision. They do **not** describe
the whole current successor source line: later September work added the
complete-script audit, further dialogue polish, renderer/runtime fixes,
fixed-layout/script-integrity hardening, STAFF work, repository/build hardening,
and additional performance/source-quality changes.

The provenance files remain useful because they explain why the August 27
canonical source changed without retaining one-off applicators or intermediate
workspaces. Do not import them from production code or edit them as a substitute
for a canonical wording change.

New translation changes use stable record IDs through `nostalgia1907.py edit`,
then the maintained validation/build path and candidate-bound runtime evidence
when playable bytes change.

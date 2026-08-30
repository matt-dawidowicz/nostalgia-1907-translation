#!/usr/bin/env python3
"""Export the explicit no-pending translation-proposal status.

The 2026-08-27 review queue is complete. Historical active-proposal analysis
used retail recompilation and archive-capacity estimation, but carrying that
one-off machinery in the maintained tree added a large unsupported surface.
This module now preserves only the stable source-only report contract used by
review tooling. Canonical English changes belong in the supported
``nostalgia1907.py edit`` workflow and must pass normal validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
EVIDENCE = HERE / "bomb_semantics.json"
DEFAULT_COMPARISON = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Bilingual_Comparison"
    / "Nostalgia1907_Japanese_English_Comparison.json"
)
DEFAULT_JSON = (
    WORKSPACE
    / "outputs"
    / "Nostalgia1907_Translation_Audit"
    / "translation_polish_proposals.json"
)
DEFAULT_MARKDOWN = DEFAULT_JSON.with_suffix(".md")

# The former proposal queue was fully reviewed and applied. Keeping this empty
# mapping visible makes the completed state machine-readable without retaining
# the retired mutation-analysis implementation.
PROPOSALS: dict[str, dict[str, str]] = {}


def _sha256(path: Path) -> str:
    """Return the uppercase SHA-256 digest of one tracked evidence file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _archive_boundary_context(*_args: object, **_kwargs: object) -> dict[str, object]:
    """Reject use of the retired active-proposal archive-analysis path."""
    raise RuntimeError(
        "active translation-proposal boundary analysis has been retired; "
        "use the supported edit/validate/build workflow for new wording"
    )


def build_proposals(
    retail_root: Path = DEFAULT_RETAIL_ROOT,
    comparison_json: Path = DEFAULT_COMPARISON,
) -> dict[str, object]:
    """Return the completed proposal-queue status without reading retail media.

    Args:
        retail_root: Retained compatibility argument. It is intentionally not
            read while the queue is empty.
        comparison_json: Retained compatibility argument. It is intentionally
            not read while the queue is empty.

    Returns:
        A source-only status report proving that no canonical files or playable
        artifacts were modified.

    Raises:
        RuntimeError: If code reintroduces a pending proposal without restoring
            a separately reviewed analysis workflow.
    """
    del retail_root, comparison_json
    if PROPOSALS:
        raise RuntimeError(
            "pending proposals require a new reviewed analysis workflow; "
            "do not revive the retired one-off exporter"
        )
    return {
        "status": "NO_PENDING_PROPOSALS",
        "proposal_count": 0,
        "canonical_sources_modified": False,
        "bin_cue_built": False,
        "authoritative_evidence_file": EVIDENCE.relative_to(WORKSPACE).as_posix(),
        "authoritative_evidence_sha256": _sha256(EVIDENCE),
        "proposals": [],
    }


def render_markdown(payload: dict[str, object]) -> str:
    """Render the no-pending status as a short human-readable report."""
    return "\n".join(
        (
            "# Translation polish proposals",
            "",
            f"Status: **{payload['status']}**",
            "",
            "No wording proposals are pending. New wording changes must use the ",
            "supported `nostalgia1907.py edit` workflow and complete normal ",
            "validation before any candidate build.",
            "",
            "This report is source-only: it does not modify canonical sources or ",
            "build BIN/CUE artifacts.",
            "",
        )
    )


def write_reports(
    payload: dict[str, object],
    json_path: Path = DEFAULT_JSON,
    markdown_path: Path = DEFAULT_MARKDOWN,
) -> None:
    """Write deterministic JSON and Markdown status reports."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(
        render_markdown(payload),
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    """Write the completed proposal-queue status to ignored report paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    payload = build_proposals(args.retail_root, args.comparison)
    write_reports(payload, args.json, args.markdown)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

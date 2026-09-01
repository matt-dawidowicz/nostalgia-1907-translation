#!/usr/bin/env python3
"""Create and verify exhaustive Nostalgia 1907 test-certification plans.

The static half compiles every canonical chapter in memory and relies on the
same emitted-byte renderer contract used by normal validation.  The runtime
half is deliberately evidence-driven: it inventories every chapter, text-box
type, fixed-layout record, and state transition that a human playtest must
confirm.  It does not pretend that SCN reachability proves an emulator scene
was displayed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mes_compiler import CompileError, compile_mes
from source_json import load_json_object
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES
from translation_formatter import audit_layouts


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
PLAN_SCHEMA_VERSION = 1
PASS = "pass"
PENDING = "pending"
VALID_RUNTIME_STATES = frozenset((PASS, "fail", PENDING, "not_applicable"))
GLOBAL_RUNTIME_CHECKS = (
    (
        "boot",
        "Boot to the title screen from the supplied CUE without a prior save state.",
    ),
    (
        "new_game",
        "Start a fresh game and reach the first interactive scene.",
    ),
    (
        "page_advance",
        "Advance multi-page lower dialogue and confirm no word is split or stale glyph remains.",
    ),
    (
        "dialogue_transition",
        "Advance across a speaker, scene, or window transition and verify the next box clears correctly.",
    ),
    (
        "choice",
        "Exercise every available choice branch encountered during the route, then confirm the selected path continues.",
    ),
    (
        "save_reload",
        "Save during normal progression, reload that save, and advance at least one new dialogue page.",
    ),
    (
        "end_to_end",
        "Reach the normal ending/credits path and verify return, restart, or completion behavior.",
    ),
)


def _load(path: Path) -> dict[str, Any]:
    """Read one canonical JSON object with a checked top-level type."""
    return load_json_object(path)


def _compiled_static_summary(retail_root: Path) -> dict[str, Any]:
    """Compile all chapters and aggregate emitted-byte renderer evidence."""
    index = _load(SOURCES / "index.json")
    failures: list[str] = []
    totals: Counter[str] = Counter()
    for chapter_item in index["chapters"]:
        chapter = chapter_item["chapter"]
        retail = retail_root / "retail_unpacked" / chapter
        try:
            result = compile_mes(
                (retail / f"{chapter}.MES").read_bytes(),
                (retail / f"{chapter}.SCN").read_bytes(),
                _load(SOURCES / chapter_item["source"]),
            )
        except (CompileError, OSError, ValueError) as error:
            failures.append(f"{chapter}: {error}")
            continue
        totals["chapters"] += 1
        totals["records"] += result.record_count
        totals["renderer_contract_records"] += result.renderer_contract_records
        totals["renderer_contract_rows"] += result.renderer_contract_rows
        totals["renderer_contract_cells"] += result.renderer_contract_cells
        totals["renderer_contract_row_edges"] += result.renderer_contract_row_edges
    return {
        "status": PASS if not failures else "fail",
        "failure_count": len(failures),
        "failures": failures,
        **dict(sorted(totals.items())),
    }


def build_plan(retail_root: Path = DEFAULT_RETAIL_ROOT) -> dict[str, Any]:
    """Return an exhaustive static and runtime certification plan.

    Args:
        retail_root: Prepared hash-locked retail reference used for SCN/MES
            geometry and compilation.

    Returns:
        A JSON-serializable plan. Static status is pass only after every
        chapter compiles; runtime entries intentionally begin pending.

    Raises:
        OSError: If canonical or retail inputs are unavailable.
        ValueError: If source metadata or renderer contracts are malformed.
    """
    layout = audit_layouts(retail_root)
    compiled = _compiled_static_summary(retail_root)
    index = _load(SOURCES / "index.json")
    records_by_chapter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in layout["records"]:
        chapter = str(record["id"]).split(":", 1)[0]
        records_by_chapter[chapter].append(record)

    chapters: list[dict[str, Any]] = []
    text_boxes: dict[str, list[str]] = defaultdict(list)
    fixed_records: list[str] = []
    for chapter_item in index["chapters"]:
        chapter = str(chapter_item["chapter"])
        source = _load(SOURCES / chapter_item["source"])
        translated = [
            record for record in source["records"] if record["policy"] == "translate"
        ]
        fixed = [
            f"{chapter}:{record['index']:03d}"
            for record in translated
            if record.get("layout_policy") == "fixed"
        ]
        fixed_records.extend(fixed)
        role_counts: Counter[str] = Counter()
        box_counts: Counter[str] = Counter()
        for record in records_by_chapter[chapter]:
            role_counts.update(record["roles"])
            layout_data = record.get("layout")
            if isinstance(layout_data, dict):
                text_box = str(layout_data["text_box"])
                box_counts[text_box] += 1
                text_boxes[text_box].append(str(record["id"]))
        chapters.append(
            {
                "chapter": chapter,
                "record_count": source["record_count"],
                "translated_record_count": len(translated),
                "preserved_record_count": sum(
                    record["policy"] == "preserve" for record in source["records"]
                ),
                "adaptive_record_count": len(records_by_chapter[chapter]),
                "fixed_record_ids": fixed,
                "role_counts": dict(sorted(role_counts.items())),
                "text_box_counts": dict(sorted(box_counts.items())),
                "runtime_status": PENDING,
                "runtime_evidence": "",
            }
        )

    runtime_boxes = [
        {
            "text_box": text_box,
            "static_record_count": len(record_ids),
            "example_record_ids": record_ids[:3],
            "runtime_status": PENDING,
            "runtime_evidence": "",
        }
        for text_box, record_ids in sorted(text_boxes.items())
    ]
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "purpose": "Whole-game static validation plus human runtime certification",
        "static": {
            "layout": {
                key: value
                for key, value in layout.items()
                if key not in {"records", "failures", "warnings", "legacy_issues"}
            },
            "emitted_renderer": compiled,
        },
        "runtime": {
            "build_identity": {
                "cue_sha256": "RECORD_BEFORE_PLAYTEST",
                "track1_sha256": "RECORD_BEFORE_PLAYTEST",
            },
            "global_checks": [
                {
                    "id": item_id,
                    "requirement": requirement,
                    "status": PENDING,
                    "evidence": "",
                }
                for item_id, requirement in GLOBAL_RUNTIME_CHECKS
            ],
            "chapters": chapters,
            "text_boxes": runtime_boxes,
            "fixed_layout_record_ids": fixed_records,
            "issues": [],
        },
    }


def _markdown(plan: dict[str, Any]) -> str:
    """Render a concise human playtest guide from a machine plan."""
    static = plan["static"]
    emitted = static["emitted_renderer"]
    runtime = plan["runtime"]
    lines = [
        "# Nostalgia 1907 whole-game certification",
        "",
        "This checklist supplements, but never replaces, the automatic source and",
        "emitted-MES renderer gates. Fill the adjacent JSON log during one broad",
        "Ares playtest; do not mark a section passed without a route/evidence note.",
        "",
        "## Automatic coverage",
        "",
        f"- Layout records: {static['layout']['classified_record_count']}",
        f"- Adaptive records: {static['layout']['adaptive_record_count']}",
        f"- Explicit fixed records: {static['layout']['fixed_record_count']}",
        f"- Emitted MES rows: {emitted['renderer_contract_rows']}",
        f"- Emitted MES logical cells: {emitted['renderer_contract_cells']}",
        f"- Lower-dialogue row edges: {emitted['renderer_contract_row_edges']}",
        "",
        "## Runtime requirements",
        "",
    ]
    for check in runtime["global_checks"]:
        lines.append(f"- [ ] **{check['id']}** — {check['requirement']}")
    lines.extend(("", "## Chapter completion", ""))
    for chapter in runtime["chapters"]:
        lines.append(
            f"- [ ] **{chapter['chapter']}** — visit all reachable routes; "
            f"advance dialogue, exercise choices, and record the route/save used."
        )
    lines.extend(("", "## Text-box types", ""))
    for text_box in runtime["text_boxes"]:
        examples = ", ".join(text_box["example_record_ids"])
        lines.append(
            f"- [ ] **{text_box['text_box']}** ({text_box['static_record_count']} records; "
            f"examples: {examples})"
        )
    lines.extend(
        (
            "",
            "A static pass does not certify runtime presentation. If a defect appears,",
            "record the chapter, route/choice, first visible words, and whether it",
            "followed a page advance, transition, or reload. A screenshot is helpful",
            "but no longer required for routine coverage.",
            "",
        )
    )
    return "\n".join(lines)


def write_plan(output_dir: Path, plan: dict[str, Any]) -> tuple[Path, Path]:
    """Write a no-overwrite JSON runtime log and Markdown certification guide."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(
            f"refusing to overwrite non-empty test-plan directory: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "whole_game_runtime_log.json"
    markdown_path = output_dir / "WHOLE_GAME_PLAYTEST.md"
    json_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(plan), encoding="utf-8")
    return json_path, markdown_path


def bind_build_identity(plan: dict[str, Any], cue: Path, track1: Path) -> None:
    """Bind a generated certification plan to the exact playable candidate."""
    if not cue.is_file() or not track1.is_file():
        raise ValueError("cue and Track 1 must both exist before playtest binding")
    runtime = plan.get("runtime")
    if not isinstance(runtime, dict) or not isinstance(
        runtime.get("build_identity"), dict
    ):
        raise ValueError("runtime build identity is missing")
    runtime["build_identity"] = {
        "cue_filename": cue.name,
        "cue_sha256": hashlib.sha256(cue.read_bytes()).hexdigest().upper(),
        "track1_filename": track1.name,
        "track1_sha256": hashlib.sha256(track1.read_bytes()).hexdigest().upper(),
    }


def _bound_candidate(identity: object) -> bool:
    """Return whether runtime identity names and hashes bind one exact candidate."""
    if not isinstance(identity, dict):
        return False
    for key in ("cue_filename", "track1_filename"):
        value = identity.get(key)
        if not isinstance(value, str) or not value or Path(value).name != value:
            return False
    for key in ("cue_sha256", "track1_sha256"):
        value = identity.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789ABCDEF" for character in value)
        ):
            return False
    return True


def _require_runtime_evidence(
    item: dict[str, Any],
    *,
    state_key: str,
    evidence_key: str,
    label: str,
    pending: list[str],
    failed: list[str],
) -> None:
    """Validate one runtime state and require evidence for completed scopes."""
    state = item.get(state_key)
    if state not in VALID_RUNTIME_STATES:
        raise ValueError(f"invalid {label} runtime state: {state!r}")
    if state == "fail":
        failed.append(label)
    elif state == PENDING:
        pending.append(label)
    elif not isinstance(item.get(evidence_key), str) or not item[evidence_key].strip():
        pending.append(f"{label}:evidence")


def verify_runtime_log(plan: dict[str, Any]) -> dict[str, Any]:
    """Return pass only for a bound, statically valid runtime certification."""
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError("runtime log schema version is missing or unsupported")
    static = plan.get("static")
    runtime = plan.get("runtime")
    if not isinstance(static, dict):
        raise ValueError("static certification summary is missing")
    if not isinstance(runtime, dict):
        raise ValueError("runtime plan is missing")
    layout = static.get("layout")
    emitted = static.get("emitted_renderer")
    if not isinstance(layout, dict) or not isinstance(emitted, dict):
        raise ValueError("static layout or emitted-renderer summary is missing")

    pending: list[str] = []
    failed: list[str] = []
    if layout.get("status") != "PASS":
        failed.append("static:layout")
    if emitted.get("status") != PASS:
        failed.append("static:emitted_renderer")
    if not _bound_candidate(runtime.get("build_identity")):
        pending.append("build_identity")

    global_checks = runtime.get("global_checks")
    chapters = runtime.get("chapters")
    text_boxes = runtime.get("text_boxes")
    fixed_records = runtime.get("fixed_layout_record_ids")
    issues = runtime.get("issues")
    if not isinstance(global_checks, list):
        raise ValueError("global runtime checks are missing")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("runtime chapter inventory is missing")
    if not isinstance(text_boxes, list) or not text_boxes:
        raise ValueError("runtime text-box inventory is missing")
    if not isinstance(fixed_records, list):
        raise ValueError("fixed-layout runtime inventory is missing")
    if not isinstance(issues, list):
        raise ValueError("runtime issue inventory is missing")

    expected_global_ids = [item_id for item_id, _requirement in GLOBAL_RUNTIME_CHECKS]
    actual_global_ids = [
        check.get("id") if isinstance(check, dict) else None for check in global_checks
    ]
    if actual_global_ids != expected_global_ids:
        raise ValueError("global runtime checks do not match the generated contract")

    emitted_chapters = emitted.get("chapters")
    if not isinstance(emitted_chapters, int) or emitted_chapters != len(chapters):
        raise ValueError("runtime chapter inventory differs from static coverage")
    chapter_names = [
        chapter.get("chapter") if isinstance(chapter, dict) else None
        for chapter in chapters
    ]
    if any(not isinstance(name, str) or not name for name in chapter_names):
        raise ValueError("runtime chapter entry is malformed")
    if len(chapter_names) != len(set(chapter_names)):
        raise ValueError("runtime chapter inventory contains duplicates")

    static_box_counts = layout.get("text_box_counts")
    if not isinstance(static_box_counts, dict):
        raise ValueError("static text-box inventory is missing")
    text_box_names = [
        text_box.get("text_box") if isinstance(text_box, dict) else None
        for text_box in text_boxes
    ]
    if any(not isinstance(name, str) or not name for name in text_box_names):
        raise ValueError("runtime text-box entry is malformed")
    if len(text_box_names) != len(set(text_box_names)):
        raise ValueError("runtime text-box inventory contains duplicates")
    if set(text_box_names) != {str(name) for name in static_box_counts}:
        raise ValueError("runtime text-box inventory differs from static coverage")

    if any(
        not isinstance(record_id, str) or not record_id
        for record_id in fixed_records
    ):
        raise ValueError("fixed-layout runtime inventory contains an invalid record ID")
    if len(fixed_records) != len(set(fixed_records)):
        raise ValueError("fixed-layout runtime inventory contains duplicates")
    if issues:
        failed.append("runtime:issues")

    for check in global_checks:
        if not isinstance(check, dict):
            raise ValueError("global runtime check is malformed")
        _require_runtime_evidence(
            check,
            state_key="status",
            evidence_key="evidence",
            label=f"global:{check['id']}",
            pending=pending,
            failed=failed,
        )
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise ValueError("runtime chapter entry is malformed")
        _require_runtime_evidence(
            chapter,
            state_key="runtime_status",
            evidence_key="runtime_evidence",
            label=f"chapter:{chapter['chapter']}",
            pending=pending,
            failed=failed,
        )
    for text_box in text_boxes:
        if not isinstance(text_box, dict):
            raise ValueError("runtime text-box entry is malformed")
        _require_runtime_evidence(
            text_box,
            state_key="runtime_status",
            evidence_key="runtime_evidence",
            label=f"text_box:{text_box['text_box']}",
            pending=pending,
            failed=failed,
        )
    return {
        "status": PASS if not pending and not failed else "PENDING_RUNTIME",
        "pending_count": len(pending),
        "pending": pending,
        "failed_count": len(failed),
        "failed": failed,
    }


def main() -> None:
    """Generate a whole-game plan or verify a filled runtime certification log."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--cue", type=Path)
    parser.add_argument("--track1", type=Path)
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        parser.error("provide exactly one of --output or --verify")
    if args.output:
        plan = build_plan(args.retail_root)
        if bool(args.cue) != bool(args.track1):
            parser.error("provide both --cue and --track1 when binding a playtest")
        if args.cue:
            bind_build_identity(plan, args.cue, args.track1)
        json_path, markdown_path = write_plan(args.output, plan)
        print(
            json.dumps(
                {
                    "status": PASS,
                    "json": str(json_path),
                    "markdown": str(markdown_path),
                },
                indent=2,
            )
        )
        return
    plan = _load(args.verify)
    report = verify_runtime_log(plan)
    print(json.dumps(report, indent=2))
    if report["status"] != PASS:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

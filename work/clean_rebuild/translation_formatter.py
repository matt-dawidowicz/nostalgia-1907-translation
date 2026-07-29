#!/usr/bin/env python3
"""Role-aware editor and auditor for canonical Nostalgia 1907 English text.

This tool never translates Japanese.  It accepts English wording only at a
stable ``CHAPTER:NNN`` ID, derives that record's renderer from the original
SCN, and previews or stores semantic (unwrapped) text.  The MES compiler owns
the final wrapping so later wording edits cannot inherit stale manual spaces.

Stable IDs use the canonical zero-based record index; SCN's one-based operands
are converted inside ``scn_layout.py``. Preview and compilation share the same
``RecordContract``, so a translator sees the real role, visible widths, runtime
strides, and floating-window row limit before writing.

Batch changes are validated in memory before any chapter JSON is written, then
committed through same-directory temporary files with prepared rollback copies.
SCN-classified records become adaptive semantic text; records without proven
reflow geometry remain explicitly fixed. See ``docs/TRANSLATION_EDITING.md``
for the contributor workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from mes_compiler import _wrap_words, normalize_semantic_text
from scn_layout import (
    LABEL_ROLES,
    ROLE_CHOICE,
    RecordContract,
    infer_contracts,
)
from translation_audit import DEFAULT_RETAIL_ROOT, SOURCES


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
RULES = HERE / "script_layout_rules.json"
DEFAULT_REPORT = (
    WORKSPACE / "outputs" / "Nostalgia1907_Translation_Audit" / "script_layout_audit.json"
)
RECORD_ID = re.compile(r"^(?P<chapter>[A-Z0-9_]+):(?P<index>[0-9]{3})$")


class DuplicateJsonKeyError(ValueError):
    """Raised when a JSON object repeats a key before object construction."""


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Build one JSON object while rejecting every repeated source key."""
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateJsonKeyError(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _load(path: Path) -> dict[str, object]:
    """Load one UTF-8 JSON object or reject an incompatible top level."""
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except DuplicateJsonKeyError as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _json_source_bytes(source: dict[str, object]) -> bytes:
    """Serialize one canonical chapter deterministically as UTF-8 JSON."""
    return (
        json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def _write_transaction_temp(
    target: Path,
    payload: bytes,
    mode: int,
    kind: str,
) -> Path:
    """Write and fsync one same-directory transaction file.

    Args:
        target: Canonical file whose directory and basename seed the temp name.
        payload: Exact bytes to stage.
        mode: Permission bits copied from the canonical target.
        kind: Human-readable suffix distinguishing new data from backups.

    Returns:
        The created temporary path after its contents are durable to the file.

    Raises:
        OSError: If creation, writing, syncing, or permission preservation fails.

    Side Effects:
        Creates one hidden temporary file beside ``target``. Any failed write
        removes its incomplete temporary file before the error escapes.
    """
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=f".{kind}",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        try:
            stream = os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            raise
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _sync_directory(path: Path) -> None:
    """Fsync one directory where the platform supports directory handles."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cleanup_transaction_files(paths: set[Path]) -> None:
    """Best-effort remove transaction files that were not consumed by replace."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # Source contents are already committed or rolled back. A stale
            # hidden temp is safer than reporting a false content failure.
            pass


def _transactional_write_json_sources(
    pending: Mapping[Path, dict[str, object]],
) -> None:
    """Commit canonical JSON files as one all-or-rollback transaction.

    Every output and byte-for-byte backup is written beside its target before
    the first canonical file is replaced. Individual replacements are atomic.
    If a later replacement or directory sync fails, already replaced targets
    are restored from their prepared backups in reverse order.

    Args:
        pending: Canonical paths mapped to fully validated in-memory objects.

    Raises:
        OSError: If staging, replacement, syncing, or rollback fails.
        TypeError: If a pending source cannot be serialized as JSON.

    Side Effects:
        Replaces every requested canonical file on success. On an ordinary
        process-visible failure, restores every target whose replacement had
        completed. This does not claim crash-atomicity across multiple files.
    """
    ordered = sorted(pending.items(), key=lambda item: str(item[0]))
    if not ordered:
        return

    serialized: dict[Path, bytes] = {}
    originals: dict[Path, bytes] = {}
    modes: dict[Path, int] = {}
    for target, source in ordered:
        serialized[target] = _json_source_bytes(source)
        originals[target] = target.read_bytes()
        modes[target] = stat.S_IMODE(target.stat().st_mode)

    new_files: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    temporary_paths: set[Path] = set()
    replaced: list[Path] = []
    parents = sorted({target.parent for target, _source in ordered}, key=str)
    try:
        for target, _source in ordered:
            staged = _write_transaction_temp(
                target,
                serialized[target],
                modes[target],
                "new",
            )
            new_files[target] = staged
            temporary_paths.add(staged)
        for target, _source in ordered:
            backup = _write_transaction_temp(
                target,
                originals[target],
                modes[target],
                "backup",
            )
            backups[target] = backup
            temporary_paths.add(backup)

        for target, _source in ordered:
            os.replace(new_files[target], target)
            temporary_paths.discard(new_files[target])
            replaced.append(target)
        for parent in parents:
            _sync_directory(parent)
    except BaseException as error:
        rollback_errors: list[str] = []
        retained_backups: set[Path] = set()
        for target in reversed(replaced):
            backup = backups[target]
            try:
                os.replace(backup, target)
                temporary_paths.discard(backup)
            except OSError as rollback_error:
                retained_backups.add(backup)
                rollback_errors.append(f"{target}: {rollback_error}")
        if not rollback_errors:
            for parent in parents:
                try:
                    _sync_directory(parent)
                except OSError as rollback_sync_error:
                    rollback_errors.append(
                        f"cannot sync rollback directory {parent}: "
                        f"{rollback_sync_error}"
                    )
        if rollback_errors:
            # A backup that could not be restored is the only byte-for-byte
            # recovery copy of that target. Preserve it for manual recovery
            # while removing unrelated staged files and unused backups.
            _cleanup_transaction_files(temporary_paths - retained_backups)
            retained = sorted(
                str(path) for path in retained_backups if path.exists()
            )
            recovery = (
                f"; recovery backups retained at {retained}" if retained else ""
            )
            raise OSError(
                "canonical JSON transaction failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
                + recovery
            ) from error
        _cleanup_transaction_files(temporary_paths)
        raise
    _cleanup_transaction_files(temporary_paths)


def _chapter_sources() -> tuple[dict[str, object], dict[str, tuple[Path, dict[str, object]]]]:
    """Load the canonical index and every chapter in declared order.

    Returns:
        The index object and a chapter-keyed mapping of source paths and parsed
        chapter objects. The mapping preserves the index's insertion order.

    Raises:
        ValueError: If an input does not contain a JSON object.
        OSError: If a tracked source cannot be read.
    """
    index = _load(SOURCES / "index.json")
    chapters: dict[str, tuple[Path, dict[str, object]]] = {}
    for item in index["chapters"]:
        path = SOURCES / item["source"]
        source = _load(path)
        chapters[item["chapter"]] = (path, source)
    return index, chapters


def _contracts(source: dict[str, object], retail_root: Path) -> dict[int, RecordContract]:
    """Infer renderer contracts from one chapter's original retail SCN.

    Canonical English never supplies geometry. Only translated record indexes
    are requested from the source-independent SCN inference engine.

    Raises:
        FileNotFoundError: If the hash-locked retail SCN is unavailable.
        ScnLayoutError: If the SCN evidence is malformed or contradictory.
    """
    chapter = source["chapter"]
    scn = retail_root / "retail_unpacked" / chapter / f"{chapter}.SCN"
    if not scn.exists():
        raise FileNotFoundError(f"missing hash-locked retail SCN: {scn}")
    translated = {
        record["index"]
        for record in source["records"]
        if record.get("policy") == "translate"
    }
    return infer_contracts(
        scn.read_bytes(),
        source["record_count"],
        translated,
        source.get("profile"),
    )


def _rules_by_role() -> dict[str, dict[str, object]]:
    """Return the configured role rules after validating their container."""
    rules = _load(RULES).get("roles")
    if not isinstance(rules, dict):
        raise ValueError("script_layout_rules.json has no roles object")
    return rules


def _require_all_classified_adaptive() -> bool:
    """Return the project-wide migration gate from the canonical rules."""
    value = _load(RULES).get("require_all_classified_adaptive", False)
    if not isinstance(value, bool):
        raise ValueError(
            "script_layout_rules.json require_all_classified_adaptive is not boolean"
        )
    return value


def _require_explicit_fixed_policy() -> bool:
    """Return whether non-reflowable translated records must declare fixed."""
    value = _load(RULES).get("require_explicit_fixed_policy", False)
    if not isinstance(value, bool):
        raise ValueError(
            "script_layout_rules.json require_explicit_fixed_policy is not boolean"
        )
    return value


def format_preview(text: str, contract: RecordContract | None) -> list[str]:
    """Return visible, unpadded rows for a proposed semantic string.

    Records without proven SCN geometry remain a single fixed-layout value.
    The preview shares normalization and wrapping code with the compiler, so it
    is suitable for review but never writes canonical source.
    """
    semantic = normalize_semantic_text(text)
    if contract is None or contract.layout is None:
        return [semantic]
    return _wrap_words(semantic, contract.layout, False)


def _record_audit(
    record_id: str,
    text: str,
    adaptive: bool,
    contract: RecordContract | None,
    rules: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Describe one proposed record and collect renderer-policy violations.

    The function is pure: it returns failures and warnings rather than raising
    for ordinary layout problems, allowing whole-game audits to report all
    affected stable IDs in one pass.
    """
    semantic = normalize_semantic_text(text)
    rows = format_preview(text, contract)
    roles = sorted(contract.roles) if contract is not None else []
    failures: list[str] = []
    warnings: list[str] = []
    if contract is not None and contract.layout is not None:
        rebuilt = normalize_semantic_text("\n".join(rows))
        if rebuilt != semantic:
            failures.append("wrapped rows do not reconstruct the semantic text")
        if contract.max_rows is not None and len(rows) > contract.max_rows:
            failures.append(
                f"uses {len(rows)} rows but the renderer permits {contract.max_rows}"
            )
    label_roles = LABEL_ROLES.intersection(roles)
    if label_roles and (contract is None or contract.layout is None):
        limits = [
            rules[role].get("max_characters")
            for role in label_roles
            if isinstance(rules.get(role), dict)
        ]
        limits = [limit for limit in limits if isinstance(limit, int)]
        if limits and len(semantic) > min(limits):
            failures.append(
                f"label is {len(semantic)} characters; maximum is {min(limits)}"
            )
    if ROLE_CHOICE in roles and ("\n" in text or "\r" in text):
        failures.append("menu choice is not a single line")
    if adaptive and (roles or (contract and contract.layout)):
        if text != semantic:
            failures.append("adaptive canonical text contains legacy layout whitespace")
    layout = None
    if contract is not None and contract.layout is not None:
        layout = {
            "visible_cells": {
                "first": contract.layout.visible_first,
                "continuation": contract.layout.visible_continuation,
            },
            "runtime_cells": {
                "first": contract.layout.runtime_first,
                "continuation": contract.layout.runtime_continuation,
            },
        }
    return {
        "id": record_id,
        "roles": roles,
        "layout": layout,
        "max_rows": contract.max_rows if contract is not None else None,
        "semantic_text": semantic,
        "preview_rows": rows,
        "preview_row_lengths": [len(row) for row in rows],
        "failures": failures,
        "warnings": warnings,
    }


def audit_layouts(retail_root: Path = DEFAULT_RETAIL_ROOT) -> dict[str, object]:
    """Audit every canonical record against its original SCN renderer.

    Args:
        retail_root: Prepared, hash-locked Japanese retail reference.

    Returns:
        A JSON-serializable report containing per-record contracts, aggregate
        role counts, migration state, warnings, and mandatory failures.

    Raises:
        OSError: If canonical data or required retail SCN files cannot be read.
        ValueError: If canonical configuration is malformed.
        ScnLayoutError: If SCN evidence cannot produce safe shared contracts.

    Side Effects:
        Reads tracked source and retail reference files; writes nothing.
    """
    _, chapters = _chapter_sources()
    rules = _rules_by_role()
    records: list[dict[str, object]] = []
    role_counts: Counter[str] = Counter()
    adaptive_chapters: list[str] = []
    adaptive_record_count = 0
    for chapter, (_, source) in chapters.items():
        contracts = _contracts(source, retail_root)
        text_mode = source["text_mode"]
        if text_mode == "adaptive":
            adaptive_chapters.append(chapter)
        for record in source["records"]:
            if record.get("policy") != "translate":
                continue
            record_id = f"{chapter}:{record['index']:03d}"
            contract = contracts.get(record["index"])
            adaptive = text_mode == "adaptive" or record.get("layout_policy") == "adaptive"
            adaptive_record_count += adaptive
            item = _record_audit(
                record_id,
                record["text"],
                adaptive,
                contract,
                rules,
            )
            item["adaptive"] = adaptive
            item["layout_policy"] = record.get("layout_policy")
            role_counts.update(item["roles"])
            records.append(item)
    failures = [
        f"{item['id']}: {failure}"
        for item in records
        if item["adaptive"]
        for failure in item["failures"]
    ]
    legacy_issues = [
        f"{item['id']}: {failure}"
        for item in records
        if not item["adaptive"]
        for failure in item["failures"]
    ]
    warnings = [
        f"{item['id']}: {warning}"
        for item in records
        for warning in item["warnings"]
    ]
    classified = [item for item in records if item["roles"] or item["layout"]]
    fixed = [
        item
        for item in records
        if not (item["roles"] or item["layout"]) and item["layout_policy"] == "fixed"
    ]
    undeclared = [
        item
        for item in records
        if not (item["roles"] or item["layout"]) and item["layout_policy"] != "fixed"
    ]
    unmigrated = [item["id"] for item in classified if not item["adaptive"]]
    migration_failures = (
        [
            f"{record_id}: SCN-classified record is not using adaptive layout"
            for record_id in unmigrated
        ]
        if _require_all_classified_adaptive()
        else []
    )
    failures.extend(migration_failures)
    if _require_explicit_fixed_policy():
        failures.extend(
            f"{item['id']}: record without proven reflow geometry is not declared fixed"
            for item in undeclared
        )
    return {
        "status": "PASS" if not failures else "FAIL",
        "schema_version": 1,
        "adaptive_chapters": adaptive_chapters,
        "adaptive_record_count": adaptive_record_count,
        "role_counts": dict(sorted(role_counts.items())),
        "classified_record_count": len(classified),
        "fixed_record_count": len(fixed),
        "undeclared_record_count": len(undeclared),
        "undeclared_record_ids": [item["id"] for item in undeclared],
        "unmigrated_classified_count": len(unmigrated),
        "unmigrated_classified_ids": unmigrated,
        "failure_count": len(failures),
        "failures": failures,
        "legacy_issue_count": len(legacy_issues),
        "legacy_issues": legacy_issues,
        "warning_count": len(warnings),
        "warnings": warnings,
        "records": records,
    }


def _parse_record_id(value: str) -> tuple[str, int]:
    """Parse an exact zero-based ``CHAPTER:NNN`` stable record ID."""
    match = RECORD_ID.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid stable record ID: {value!r}")
    return match.group("chapter"), int(match.group("index"))


def _changes(path: Path) -> dict[str, str]:
    """Load an ID-to-English change set in object or entry-list form.

    Duplicate object keys are rejected by ``_load`` before normal JSON object
    construction can discard an earlier value. Duplicate list entries are also
    rejected instead of allowing the last value to win silently.
    """
    payload = _load(path)
    raw = payload.get("changes", payload)
    if isinstance(raw, dict):
        changes = raw
    elif isinstance(raw, list):
        changes = {}
        for position, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ValueError(f"changes list entry {position} is not an object")
            record_id = item.get("id")
            text = item.get("text")
            if not isinstance(record_id, str) or not isinstance(text, str):
                raise ValueError(
                    f"changes list entry {position} requires string id and text"
                )
            if record_id in changes:
                raise ValueError(f"changes list repeats stable ID {record_id!r}")
            changes[record_id] = text
    else:
        raise ValueError("changes must be an ID-to-text object or an entry list")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in changes.items()):
        raise ValueError("every change must map a stable ID to English text")
    return changes


def apply_changes(path: Path, retail_root: Path = DEFAULT_RETAIL_ROOT) -> dict[str, object]:
    """Atomically apply reviewed English changes using per-record contracts.

    Every requested ID is resolved, policy-checked, and audited in memory
    before any chapter file is written. SCN-classified records store normalized
    semantic text with adaptive layout; unclassified records preserve the
    reviewer's exact fixed layout.

    Args:
        path: UTF-8 JSON change set accepted by ``_changes``.
        retail_root: Prepared Japanese reference that supplies original SCNs.

    Returns:
        A report with before/after text, roles, and preview rows for each ID.

    Raises:
        ValueError: If any ID, policy, text, or renderer contract is invalid.
        OSError: If source files cannot be read or written.

    Side Effects:
        Rewrites only canonical chapter JSON files affected by the validated
        batch. It does not compile MES data or modify retail files.
    """
    changes = _changes(path)
    _, chapters = _chapter_sources()
    pending: dict[Path, dict[str, object]] = {}
    report: list[dict[str, object]] = []
    for record_id, proposed in changes.items():
        chapter, record_index = _parse_record_id(record_id)
        if chapter not in chapters:
            raise ValueError(f"{record_id}: unknown chapter")
        source_path, source = chapters[chapter]
        if not 0 <= record_index < source["record_count"]:
            raise ValueError(f"{record_id}: index is outside the record table")
        record = source["records"][record_index]
        if record.get("index") != record_index or record.get("policy") != "translate":
            raise ValueError(f"{record_id}: record is not translated prose")
        contract = _contracts(source, retail_root).get(record_index)
        audited = _record_audit(
            record_id,
            proposed,
            True,
            contract,
            _rules_by_role(),
        )
        if audited["failures"]:
            raise ValueError(f"{record_id}: " + "; ".join(audited["failures"]))
        before = record["text"]
        if contract is not None and (contract.roles or contract.layout is not None):
            record["text"] = normalize_semantic_text(proposed)
            record["layout_policy"] = "adaptive"
        else:
            # Without proven SCN geometry the record is an explicit bitmap
            # layout.  Preserve the reviewer's exact line/space decisions.
            record["text"] = proposed
            record["layout_policy"] = "fixed"
        profile = source.get("profile")
        if isinstance(profile, dict):
            required_exact = profile.get("required_text_exact")
            if isinstance(required_exact, dict) and str(record_index) in required_exact:
                required_exact[str(record_index)] = record["text"]
        pending[source_path] = source
        report.append(
            {
                "id": record_id,
                "before": before,
                "after": record["text"],
                "roles": audited["roles"],
                "preview_rows": audited["preview_rows"],
            }
        )
    _transactional_write_json_sources(pending)
    return {"status": "PASS", "changed_record_count": len(report), "changes": report}


def migrate(retail_root: Path = DEFAULT_RETAIL_ROOT) -> dict[str, object]:
    """Adopt adaptive layout for every SCN-classified translated record.

    The migration first audits the complete source set in memory. If any
    classified record fails, it raises before writing. Records without proven
    geometry are explicitly marked fixed so future tooling cannot guess.

    Side Effects:
        Rewrites changed canonical chapter JSON files after the global
        preflight succeeds.
    """
    _, chapters = _chapter_sources()
    changed_records = 0
    adopted_records = 0
    fixed_records = 0
    changed_chapters: list[str] = []
    pending: list[tuple[Path, dict[str, object]]] = []
    blocking_failures: list[str] = []
    rules = _rules_by_role()
    for chapter, (path, source) in chapters.items():
        contracts = _contracts(source, retail_root)
        source_changed = False
        for record in source["records"]:
            if record.get("policy") != "translate":
                continue
            contract = contracts.get(record["index"])
            if contract is None or (not contract.roles and contract.layout is None):
                if record.get("layout_policy") != "fixed":
                    record["layout_policy"] = "fixed"
                    fixed_records += 1
                    source_changed = True
                continue
            semantic = normalize_semantic_text(record["text"])
            audited = _record_audit(
                f"{chapter}:{record['index']:03d}",
                semantic,
                True,
                contract,
                rules,
            )
            if audited["failures"]:
                blocking_failures.extend(
                    f"{chapter}:{record['index']:03d}: {failure}"
                    for failure in audited["failures"]
                )
                continue
            if record["text"] != semantic:
                record["text"] = semantic
                changed_records += 1
                source_changed = True
            if record.get("layout_policy") != "adaptive":
                record["layout_policy"] = "adaptive"
                adopted_records += 1
                source_changed = True
            profile = source.get("profile")
            if isinstance(profile, dict):
                required_exact = profile.get("required_text_exact")
                if (
                    isinstance(required_exact, dict)
                    and str(record["index"]) in required_exact
                ):
                    required_exact[str(record["index"])] = semantic
        if source_changed:
            pending.append((path, source))
            changed_chapters.append(chapter)
    if blocking_failures:
        raise ValueError(
            "adaptive migration aborted before writing; "
            + "; ".join(blocking_failures)
        )
    _transactional_write_json_sources(dict(pending))
    return {
        "status": "PASS",
        "changed_chapters": changed_chapters,
        "adaptive_records_adopted": adopted_records,
        "fixed_records_declared": fixed_records,
        "normalized_record_count": changed_records,
    }


def main() -> None:
    """Run preview, batch-apply, migration, or whole-game audit mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--record", help="preview one stable CHAPTER:NNN record")
    action.add_argument("--changes", type=Path, help="apply an ID-keyed English change file")
    action.add_argument("--migrate", action="store_true", help="adopt adaptive mode and semantic text")
    parser.add_argument("--text", help="proposed English for --record")
    args = parser.parse_args()

    if args.record:
        chapter, record_index = _parse_record_id(args.record)
        _, chapters = _chapter_sources()
        if chapter not in chapters:
            raise ValueError(f"unknown chapter: {chapter}")
        _, source = chapters[chapter]
        if not 0 <= record_index < source["record_count"]:
            raise ValueError(f"record outside table: {args.record}")
        record = source["records"][record_index]
        text = args.text if args.text is not None else record.get("text")
        if not isinstance(text, str):
            raise ValueError(f"{args.record} has no translatable text")
        contract = _contracts(source, args.retail_root).get(record_index)
        payload = _record_audit(
            args.record,
            text,
            source["text_mode"] == "adaptive"
            or record.get("layout_policy") == "adaptive",
            contract,
            _rules_by_role(),
        )
    elif args.changes:
        payload = apply_changes(args.changes, args.retail_root)
    elif args.migrate:
        payload = migrate(args.retail_root)
    else:
        payload = audit_layouts(args.retail_root)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        payload = {
            key: value
            for key, value in payload.items()
            if key not in {"records", "warnings", "failures", "legacy_issues"}
        } | {"report": str(args.report)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload.get("status") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

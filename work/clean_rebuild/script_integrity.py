#!/usr/bin/env python3
"""Audit SCN-to-MES text references and expose runtime branch inventory.

The project intentionally does not claim a complete SCN bytecode grammar. This
module therefore operates only on command shapes whose operand layout has been
proven from retail scripts and MAIN.BIN. It complements renderer inference by
checking that translated records are reachable through one of those proven
shapes (or an explicit profile contract) and by materializing every recognized
choice edge for runtime coverage.

Unknown bytes are never interpreted as commands merely because they equal an
opcode value. The recognized shapes are the same conservative structures used
by ``scn_layout.py`` and the box-layout audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mes_format import read_mes
from .scn_layout import (
    _selector_window_commands,
    _window_text_commands,
    infer_contracts,
)
from .source_json import load_json_object
from .translation_audit import DEFAULT_RETAIL_ROOT, SOURCES


@dataclass(frozen=True)
class ScnTextReference:
    """One statically proven SCN reference to a zero-based MES record."""

    offset: int
    command: str
    record_index: int
    role: str
    branch_target: int | None = None
    target_opcode: int | None = None


@dataclass(frozen=True)
class ScnChoiceEdge:
    """One recognized 0x31 menu-choice edge and its destination opcode."""

    offset: int
    record_index: int
    branch_target: int
    target_opcode: int


def _window_subtypes(profile: dict[str, object] | None) -> set[int]:
    """Return visible 0x24 subtypes using the profile default from layout inference."""
    settings = profile or {}
    raw = settings.get("scn_window_text_subtypes", [0x27])
    if not isinstance(raw, list) or not all(isinstance(item, int) for item in raw):
        raise ValueError("profile scn_window_text_subtypes is invalid")
    return set(raw)


def scan_scn_text_references(
    scn: bytes,
    record_count: int,
    profile: dict[str, object] | None,
) -> tuple[ScnTextReference, ...]:
    """Return every reference identified by a proven text-bearing SCN shape.

    This is deliberately conservative. In particular, 0x22/0x23 labels are
    accepted only as the adjacent pair used by the scene UI, while 0x31 is
    accepted only with its marker byte, an in-range record ID, and an in-range
    branch target. Floating and selector windows reuse the reviewed parsers in
    ``scn_layout`` so layout and referential audits cannot drift apart.
    """
    if record_count <= 0:
        raise ValueError("record_count must be positive")

    references: list[ScnTextReference] = []

    def add(
        offset: int,
        command: str,
        record_index: int,
        role: str,
        *,
        branch_target: int | None = None,
    ) -> None:
        if not 0 <= record_index < record_count:
            raise ValueError(
                f"{command} at 0x{offset:X} references out-of-range "
                f"record {record_index}"
            )
        target_opcode = scn[branch_target] if branch_target is not None else None
        references.append(
            ScnTextReference(
                offset=offset,
                command=command,
                record_index=record_index,
                role=role,
                branch_target=branch_target,
                target_opcode=target_opcode,
            )
        )

    for offset in range(len(scn)):
        opcode = scn[offset]
        if opcode in (0x20, 0x22, 0x23) and offset + 3 <= len(scn):
            text_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            if 1 <= text_id <= record_count:
                role = {
                    0x20: "fixed_line",
                    0x22: "location_name",
                    0x23: "perspective_name",
                }[opcode]
                add(offset, f"0x{opcode:02X}", text_id - 1, role)
        elif opcode == 0x21 and offset + 5 <= len(scn):
            first_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            second_id = int.from_bytes(scn[offset + 3 : offset + 5], "big")
            if 1 <= second_id <= record_count:
                if 1 <= first_id <= record_count:
                    add(offset, "0x21", first_id - 1, "speaker_name")
                add(offset, "0x21", second_id - 1, "dialogue_body")
            elif second_id == 0 and 1 <= first_id <= record_count:
                add(offset, "0x21", first_id - 1, "dialogue_continuation")
        elif opcode == 0x22 and offset + 6 <= len(scn) and scn[offset + 3] == 0x23:
            location_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            perspective_id = int.from_bytes(scn[offset + 4 : offset + 6], "big")
            if 1 <= location_id <= record_count and 1 <= perspective_id <= record_count:
                add(offset, "0x22/0x23", location_id - 1, "location_name")
                add(offset + 3, "0x22/0x23", perspective_id - 1, "perspective_name")
        elif (
            opcode == 0x24
            and offset + 8 <= len(scn)
            and scn[offset + 5] == 0x28
            and scn[offset + 3] == 0x05
        ):
            text_id = int.from_bytes(scn[offset + 6 : offset + 8], "big")
            if 1 <= text_id <= record_count:
                add(offset, "0x24/0x28", text_id - 1, "special_window")
        elif opcode == 0x31 and offset + 6 <= len(scn) and scn[offset + 3] == 0xFF:
            text_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
            target = int.from_bytes(scn[offset + 4 : offset + 6], "big")
            if 1 <= text_id <= record_count and 0 < target < len(scn):
                add(
                    offset,
                    "0x31",
                    text_id - 1,
                    "menu_choice",
                    branch_target=target,
                )

    subtypes = _window_subtypes(profile)
    for offset, _subtype, _width, _raw_y, indexes in _window_text_commands(
        scn, record_count, subtypes
    ):
        for position, index in enumerate(indexes):
            command_offset = (
                offset if position == 0 else offset + 8 + 3 * (position - 1)
            )
            add(
                command_offset,
                "0x24" if position == 0 else "0x27",
                index,
                "floating_window" if position == 0 else "floating_continuation",
            )

    for offset, _subtype, _width, _raw_y, indexes in _selector_window_commands(
        scn, record_count
    ):
        for index in indexes:
            add(offset, "0x24 selector target", index, "menu_choice_window")

    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.offset,
                item.command,
                item.record_index,
                item.role,
                item.branch_target if item.branch_target is not None else -1,
            ),
        )
    )


def choice_edges(references: tuple[ScnTextReference, ...]) -> tuple[ScnChoiceEdge, ...]:
    """Return every recognized menu-choice branch from a reference inventory."""
    return tuple(
        ScnChoiceEdge(
            offset=item.offset,
            record_index=item.record_index,
            branch_target=item.branch_target,
            target_opcode=item.target_opcode,
        )
        for item in references
        if item.command == "0x31"
        and item.branch_target is not None
        and item.target_opcode is not None
    )


def audit_project_scn_references(
    retail_root: Path = DEFAULT_RETAIL_ROOT,
) -> dict[str, object]:
    """Audit all canonical chapters against the hash-locked retail SCN/MES set.

    A translated record passes reachability when it appears in a statically
    proven SCN reference or has an explicit inferred profile contract. Profile
    coverage is retained for exceptional renderers that cannot be represented
    by the generic command shapes. The report also exposes every recognized
    0x31 branch edge for the runtime certification plan.
    """
    index = load_json_object(SOURCES / "index.json")
    failures: list[str] = []
    chapters: list[dict[str, object]] = []
    total_references = 0
    total_choice_edges = 0
    total_profile_only = 0

    for chapter_item in index["chapters"]:
        chapter = str(chapter_item["chapter"])
        source = load_json_object(SOURCES / str(chapter_item["source"]))
        record_count = int(source["record_count"])
        translated = {
            int(record["index"])
            for record in source["records"]
            if record.get("policy") == "translate"
        }
        retail = retail_root / "retail_unpacked" / chapter
        scn_path = retail / f"{chapter}.SCN"
        mes_path = retail / f"{chapter}.MES"
        if not scn_path.is_file() or not mes_path.is_file():
            raise FileNotFoundError(
                f"{chapter}: prepared retail SCN/MES files are unavailable"
            )
        scn = scn_path.read_bytes()
        mes = read_mes(mes_path)
        if mes.record_count != record_count:
            failures.append(
                f"{chapter}: retail MES has {mes.record_count} records; "
                f"source declares {record_count}"
            )
            continue
        profile = (
            source.get("profile")
            if isinstance(source.get("profile"), dict)
            else None
        )
        references = scan_scn_text_references(scn, record_count, profile)
        referenced = {item.record_index for item in references}
        contracts = infer_contracts(
            scn,
            record_count,
            translated,
            profile,
            retail_records=mes.records,
        )
        profile_only = sorted(
            index_value
            for index_value in translated - referenced
            if index_value in contracts
            and (
                contracts[index_value].layout is not None
                or bool(contracts[index_value].roles)
            )
        )
        missing = sorted(translated - referenced - set(profile_only))
        for record_index in missing:
            failures.append(
                f"{chapter}:{record_index:03d}: translated record has no proven "
                "SCN reference or profile contract"
            )
        edges = choice_edges(references)
        for edge in edges:
            if not 0 < edge.branch_target < len(scn):
                failures.append(
                    f"{chapter}:0x{edge.offset:X}: choice target "
                    f"0x{edge.branch_target:X} is out of range"
                )
        total_references += len(references)
        total_choice_edges += len(edges)
        total_profile_only += len(profile_only)
        chapters.append(
            {
                "chapter": chapter,
                "reference_count": len(references),
                "referenced_record_count": len(referenced),
                "translated_record_count": len(translated),
                "profile_only_translated_record_ids": [
                    f"{chapter}:{record_index:03d}" for record_index in profile_only
                ],
                "missing_translated_record_ids": [
                    f"{chapter}:{record_index:03d}" for record_index in missing
                ],
                "choice_edges": [
                    {
                        "id": f"{chapter}:0x{edge.offset:X}->0x{edge.branch_target:X}",
                        "record_id": f"{chapter}:{edge.record_index:03d}",
                        "offset": edge.offset,
                        "branch_target": edge.branch_target,
                        "target_opcode": edge.target_opcode,
                    }
                    for edge in edges
                ],
            }
        )

    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "chapter_count": len(chapters),
        "reference_count": total_references,
        "choice_branch_count": total_choice_edges,
        "profile_only_translated_record_count": total_profile_only,
        "chapters": chapters,
    }

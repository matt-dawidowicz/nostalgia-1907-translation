#!/usr/bin/env python3
"""Apply the one-shot September 2026 efficiency and style refactor."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _path(relative: str) -> Path:
    """Return a repository-relative path."""
    return ROOT / relative


def _replace_once(relative: str, old: str, new: str) -> None:
    """Replace one exact source fragment and reject drift or ambiguity."""
    path = _path(relative)
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{relative}: expected one replacement target, found {count}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def _replace_between(
    relative: str, start: str, end: str, replacement: str
) -> None:
    """Replace text between unique markers while preserving the end marker."""
    path = _path(relative)
    text = path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError(f"{relative}: replacement markers are not unique")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    path.write_text(
        text[:start_index] + replacement + text[end_index:],
        encoding="utf-8",
        newline="\n",
    )


def _replace_function(relative: str, name: str, replacement: str) -> None:
    """Replace one top-level function using parsed source line boundaries."""
    path = _path(relative)
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"{relative}: expected one top-level function {name!r}"
        )
    node = matches[0]
    if node.end_lineno is None:
        raise RuntimeError(f"{relative}: function {name!r} has no end line")
    lines = text.splitlines(keepends=True)
    start = node.lineno - 1
    if node.decorator_list:
        start = min(decorator.lineno for decorator in node.decorator_list) - 1
    end = node.end_lineno
    new_text = (
        "".join(lines[:start])
        + replacement.rstrip()
        + "\n\n"
        + "".join(lines[end:])
    )
    path.write_text(new_text, encoding="utf-8", newline="\n")


def _configure_standards() -> None:
    """Make Ruff the executable PEP 8 and PEP 257 contract."""
    _path("pyproject.toml").write_text(
        """[tool.ruff]\n"
        "line-length = 79\n"
        "target-version = \"py312\"\n\n"
        "[tool.ruff.lint]\n"
        "select = [\"E\", \"F\", \"I\", \"UP\", \"W\", \"D\"]\n"
        "ignore = [\"E501\"]\n\n"
        "[tool.ruff.lint.pydocstyle]\n"
        "convention = \"pep257\"\n\n"
        "[tool.mypy]\n"
        "python_version = \"3.12\"\n"
        "check_untyped_defs = true\n"
        "no_implicit_optional = true\n"
        "warn_redundant_casts = true\n"
        "warn_unused_configs = true\n"
        "warn_unused_ignores = true\n""",
        encoding="utf-8",
        newline="\n",
    )
    _replace_once(
        "tools/source_checks.py",
        '    _run((sys.executable, "-m", "ruff", "check", *CHECK_PATHS), root=root, label="Ruff lint checks")\n',
        "    _run(\n"
        '        (sys.executable, "-m", "ruff", "format", "--check", *CHECK_PATHS),\n'
        "        root=root,\n"
        '        label="Ruff format checks",\n'
        "    )\n"
        "    _run(\n"
        '        (sys.executable, "-m", "ruff", "check", *CHECK_PATHS),\n'
        "        root=root,\n"
        '        label="Ruff lint checks",\n'
        "    )\n",
    )


def _optimize_lz() -> None:
    """Replace long-copy enumeration with a range-minimum DP query."""
    _replace_function(
        "work/clean_rebuild/lz_format.py",
        "_copy_candidates",
        '''def _copy_matches(
    data: bytes, positions: dict[int, list[int]], position: int
) -> list[tuple[int, int]]:
    """Return legal copy distances and their maximum backward match lengths.

    One match now represents the complete long-copy interval instead of
    allocating one operation tuple for every length from five through the
    maximum. The DP selects the best long length with a range-minimum query.
    """
    max_distance = min(0xFFF, len(data) - position)
    if position < 2 or max_distance <= 0:
        return []
    key = (data[position - 2] << 8) | data[position - 1]
    matching = positions.get(key, [])
    first = bisect.bisect_left(matching, position)
    last = bisect.bisect_right(matching, position - 1 + max_distance)
    matches: list[tuple[int, int]] = []
    for source in matching[first:last]:
        distance = source - (position - 1)
        length = _match_length(data, position, distance, min(256, position))
        if length >= 2:
            matches.append((distance, length))
    return matches''',
    )
    _replace_function(
        "work/clean_rebuild/lz_format.py",
        "_choose_operations",
        '''def _choose_operations(data: bytes) -> list[tuple[int, Op]]:
    """Find the minimum-bit backward parse with deterministic tie breaking.

    Literal costs use a monotonic sliding minimum. Long-copy commands have a
    fixed 23-bit cost, so a segment tree selects the least-cost legal
    predecessor without materializing every candidate length. Equal-cost range
    minima choose the largest predecessor index, which is the shortest copy and
    therefore preserves the legacy ascending-length tie preference.
    """
    positions: dict[int, list[int]] = {}
    for endpoint in range(1, len(data)):
        key = (data[endpoint - 1] << 8) | data[endpoint]
        positions.setdefault(key, []).append(endpoint)
    infinity = 10**18
    costs = [infinity] * (len(data) + 1)
    choices: list[Op | None] = [None] * (len(data) + 1)
    costs[0] = 0
    long_literals: deque[tuple[int, int]] = deque()

    tree_size = 1 << max(0, len(data)).bit_length()
    range_minima = [(infinity, 0)] * (tree_size * 2)

    def update_range_minimum(index: int, cost: int) -> None:
        """Publish one completed DP cost to the iterative segment tree."""
        node = tree_size + index
        range_minima[node] = (cost, -index)
        node //= 2
        while node:
            range_minima[node] = min(
                range_minima[node * 2], range_minima[node * 2 + 1]
            )
            node //= 2

    def query_range_minimum(first: int, last: int) -> tuple[int, int]:
        """Return minimum cost and largest tied index in an inclusive range."""
        left = tree_size + first
        right = tree_size + last + 1
        best = (infinity, 0)
        while left < right:
            if left & 1:
                best = min(best, range_minima[left])
                left += 1
            if right & 1:
                right -= 1
                best = min(best, range_minima[right])
            left //= 2
            right //= 2
        return best[0], -best[1]

    update_range_minimum(0, 0)
    for position in range(1, len(data) + 1):
        for length in range(1, min(8, position) + 1):
            cost = costs[position - length] + 5 + length * 8
            if cost < costs[position]:
                costs[position] = cost
                choices[position] = ("literal", length, 0)

        eligible = position - 9
        if eligible >= 0:
            value = costs[eligible] - 8 * eligible
            while long_literals and value <= long_literals[-1][1]:
                long_literals.pop()
            long_literals.append((eligible, value))
        minimum_index = position - 264
        while long_literals and long_literals[0][0] < minimum_index:
            long_literals.popleft()
        if long_literals:
            predecessor = long_literals[0][0]
            length = position - predecessor
            cost = costs[predecessor] + 11 + length * 8
            if cost < costs[position]:
                costs[position] = cost
                choices[position] = ("literal", length, 0)

        for distance, match_length in _copy_matches(data, positions, position):
            if distance <= 0xFF:
                cost = costs[position - 2] + 10
                if cost < costs[position]:
                    costs[position] = cost
                    choices[position] = ("copy2", 2, distance)
            if match_length >= 3 and distance <= 0x1FF:
                cost = costs[position - 3] + 12
                if cost < costs[position]:
                    costs[position] = cost
                    choices[position] = ("copy3", 3, distance)
            if match_length >= 4 and distance <= 0x3FF:
                cost = costs[position - 4] + 13
                if cost < costs[position]:
                    costs[position] = cost
                    choices[position] = ("copy4", 4, distance)
            if match_length >= 5:
                predecessor_cost, predecessor = query_range_minimum(
                    position - match_length, position - 5
                )
                cost = predecessor_cost + 23
                if cost < costs[position]:
                    costs[position] = cost
                    choices[position] = (
                        "copylong",
                        position - predecessor,
                        distance,
                    )

        update_range_minimum(position, costs[position])

    selected: list[tuple[int, Op]] = []
    position = len(data)
    while position:
        operation = choices[position]
        if operation is None:
            raise LzError(f"compressor could not cover byte {position}")
        selected.append((position, operation))
        position -= operation[1]
    return selected''',
    )


def _optimize_scn_contracts() -> None:
    """Build renderer roles, layouts, and row limits from one shared inventory."""
    _replace_function(
        "work/clean_rebuild/scn_layout.py",
        "infer_layouts",
        '''def infer_layouts(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
    *,
    retail_records: tuple[bytes, ...] | None = None,
    occurrences: dict[int, list[dict[str, object]]] | None = None,
) -> dict[int, Layout]:
    """Infer translated-record geometry from shared structural SCN evidence.

    When ``occurrences`` is supplied by :func:`infer_contracts`, role, layout,
    and row-limit inference consume one common command inventory instead of
    independently rescanning the SCN byte stream.
    """
    settings = profile or {}
    dialogue_visible = _pair(settings, "scn_dialogue_layout", (12, 11))
    continuation_visible = _pair(settings, "scn_continuation_layout", (11, 10))
    dialogue_runtime = _pair(settings, "scn_dialogue_runtime_layout", dialogue_visible)
    continuation_runtime = _pair(
        settings, "scn_continuation_runtime_layout", (11, 11)
    )
    visible_overrides = _indexed_pairs(settings, "layout_overrides")
    runtime_overrides = _indexed_pairs(settings, "runtime_layout_overrides")
    text_box_overrides = _indexed_text_boxes(settings)
    layouts: dict[int, Layout] = {}
    if retail_records is not None and len(retail_records) != record_count:
        raise ScnLayoutError("retail MES record count does not match SCN layout input")
    inventory = occurrences or display_occurrences(scn, record_count, profile)
    dialogue_anchor_indexes: set[int] = set()

    def add(index: int, layout: Layout, source: str) -> None:
        """Merge one proven layout while rejecting conflicting SCN evidence."""
        if index not in translated_indexes:
            return
        previous = layouts.get(index)
        if previous is not None and previous != layout:
            raise ScnLayoutError(
                f"record {index} receives conflicting layouts at {source}: "
                f"{previous} versus {layout}"
            )
        if (
            layout.runtime_first < layout.visible_first
            or layout.runtime_continuation < layout.visible_continuation
        ):
            raise ScnLayoutError(
                f"record {index}: runtime stride is smaller than visible width"
            )
        layouts[index] = layout

    floating_roles = {ROLE_THOUGHT, ROLE_OVERLAY, ROLE_CHOICE}
    for index, record_occurrences in inventory.items():
        if index not in translated_indexes:
            continue
        for occurrence in record_occurrences:
            role = occurrence.get("role")
            source = str(occurrence.get("offset", "unknown SCN offset"))
            if role == ROLE_DIALOGUE:
                add(
                    index,
                    Layout(
                        *dialogue_visible,
                        *dialogue_runtime,
                        page_rows=3,
                        repeat_first_row_on_page=False,
                        text_box=TEXT_BOX_LOWER_DIALOGUE,
                    ),
                    f"0x21 dialogue at {source}",
                )
                if retail_records is not None and retail_records[index][:1] == bytes(
                    (DIALOGUE_OPENING_ANCHOR_CODE,)
                ):
                    dialogue_anchor_indexes.add(index)
                continue
            if role == ROLE_CONTINUATION:
                add(
                    index,
                    Layout(
                        *continuation_visible,
                        *continuation_runtime,
                        page_rows=3,
                        repeat_first_row_on_page=False,
                        text_box=TEXT_BOX_LOWER_CONTINUATION,
                    ),
                    f"0x21 continuation at {source}",
                )
                continue
            if occurrence.get("box") != "floating_window" or role not in floating_roles:
                continue
            cells = occurrence.get("permitted_cells")
            if not isinstance(cells, int):
                if index in visible_overrides:
                    continue
                width = occurrence.get("width_operand", "unknown")
                raise ScnLayoutError(
                    f"unsupported floating width {width} at {source}"
                )
            add(
                index,
                Layout(cells, cells, cells, cells, text_box=TEXT_BOX_FLOATING),
                f"floating window at {source}",
            )

    for index in sorted(
        set(visible_overrides) | set(runtime_overrides) | set(text_box_overrides)
    ):
        if index not in translated_indexes:
            continue
        previous = layouts.get(index)
        visible = visible_overrides.get(index)
        runtime = runtime_overrides.get(index)
        if visible is None:
            if previous is None:
                raise ScnLayoutError(
                    f"record {index}: runtime override has no inferred/visible layout"
                )
            visible = (previous.visible_first, previous.visible_continuation)
        if runtime is None:
            runtime = (
                visible
                if index in visible_overrides
                else (
                    (previous.runtime_first, previous.runtime_continuation)
                    if previous is not None
                    else visible
                )
            )
        override = Layout(
            *visible,
            *runtime,
            page_rows=previous.page_rows if previous is not None else None,
            repeat_first_row_on_page=(
                previous.repeat_first_row_on_page if previous is not None else False
            ),
            opening_anchor_cells=(
                previous.opening_anchor_cells if previous is not None else 0
            ),
            text_box=text_box_overrides.get(
                index,
                previous.text_box if previous is not None else TEXT_BOX_UNCLASSIFIED,
            ),
        )
        if (
            override.runtime_first < override.visible_first
            or override.runtime_continuation < override.visible_continuation
        ):
            raise ScnLayoutError(
                f"record {index}: runtime override is smaller than visible width"
            )
        layouts[index] = override
    for index in sorted(dialogue_anchor_indexes):
        layout = layouts.get(index)
        if layout is not None:
            layouts[index] = layout.with_opening_anchor()
    return layouts''',
    )
    _replace_function(
        "work/clean_rebuild/scn_layout.py",
        "infer_roles",
        '''def infer_roles(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
    *,
    occurrences: dict[int, list[dict[str, object]]] | None = None,
) -> dict[int, frozenset[str]]:
    """Infer UI roles from one shared structural display inventory."""
    settings = profile or {}
    roles: dict[int, set[str]] = {}
    inventory = occurrences or display_occurrences(scn, record_count, profile)

    for index, record_occurrences in inventory.items():
        if index not in translated_indexes:
            continue
        for occurrence in record_occurrences:
            role = occurrence.get("role")
            if isinstance(role, str):
                roles.setdefault(index, set()).add(role)

    for index, replacement in _role_overrides(settings).items():
        if index in translated_indexes:
            roles[index] = set(replacement)
    return {index: frozenset(values) for index, values in sorted(roles.items())}''',
    )
    _replace_function(
        "work/clean_rebuild/scn_layout.py",
        "infer_row_limits",
        '''def infer_row_limits(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
    *,
    occurrences: dict[int, list[dict[str, object]]] | None = None,
) -> dict[int, int]:
    """Infer floating-window row limits from shared structural occurrences."""
    settings = profile or {}
    limits: dict[int, int] = {}
    inventory = occurrences or display_occurrences(scn, record_count, profile)
    floating_roles = {ROLE_THOUGHT, ROLE_OVERLAY, ROLE_CHOICE}
    for index, record_occurrences in inventory.items():
        if index not in translated_indexes:
            continue
        for occurrence in record_occurrences:
            if (
                occurrence.get("box") != "floating_window"
                or occurrence.get("role") not in floating_roles
            ):
                continue
            raw_y = occurrence.get("y_operand")
            if not isinstance(raw_y, int):
                continue
            max_rows = (28 - raw_y - 2) // 2
            if max_rows <= 0:
                offset = occurrence.get("offset", "unknown SCN offset")
                raise ScnLayoutError(
                    f"floating window at {offset} has no visible rows"
                )
            previous = limits.get(index)
            limits[index] = min(previous, max_rows) if previous is not None else max_rows

    raw_overrides = settings.get("row_limit_overrides", {})
    if not isinstance(raw_overrides, dict):
        raise ScnLayoutError("profile row_limit_overrides is not an object")
    for raw_index, raw_limit in raw_overrides.items():
        try:
            index = canonical_profile_index(
                raw_index, field="row_limit_overrides", chapter="SCN profile"
            )
        except ValueError as exc:
            raise ScnLayoutError(f"invalid row-limit record {raw_index!r}") from exc
        if not isinstance(raw_limit, int) or raw_limit <= 0:
            raise ScnLayoutError(f"invalid row limit for record {raw_index!r}")
        if index in translated_indexes:
            limits[index] = raw_limit
    return limits''',
    )
    _replace_function(
        "work/clean_rebuild/scn_layout.py",
        "infer_contracts",
        '''def infer_contracts(
    scn: bytes,
    record_count: int,
    translated_indexes: set[int],
    profile: dict[str, object] | None,
    *,
    retail_records: tuple[bytes, ...] | None = None,
) -> dict[int, RecordContract]:
    """Return roles, layouts, and row limits from one shared SCN inventory.

    English text is never consulted. A single occurrence inventory is reused by
    every inference layer so structural command parsing cannot drift or be
    repeated three times for one chapter.
    """
    occurrences = display_occurrences(scn, record_count, profile)
    roles = infer_roles(
        scn,
        record_count,
        translated_indexes,
        profile,
        occurrences=occurrences,
    )
    layouts = infer_layouts(
        scn,
        record_count,
        translated_indexes,
        profile,
        retail_records=retail_records,
        occurrences=occurrences,
    )
    row_limits = infer_row_limits(
        scn,
        record_count,
        translated_indexes,
        profile,
        occurrences=occurrences,
    )
    indexes = set(roles) | set(layouts) | set(row_limits)
    return {
        index: RecordContract(
            roles=roles.get(index, frozenset()),
            layout=layouts.get(index),
            max_rows=row_limits.get(index),
        )
        for index in sorted(indexes)
    }''',
    )


def _optimize_compiler() -> None:
    """Reuse one bitmap plan and remove redundant compiler scans."""
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "    infer_layouts,\n    infer_roles,\n    infer_row_limits,\n",
        "    infer_contracts,\n    infer_layouts,\n",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "    def cells(self) -> tuple[Cell, ...]:\n"
        '        """Return the complete row in renderer order."""\n'
        "        return self.prefix + self.primary\n",
        "    def cells(self) -> tuple[Cell, ...]:\n"
        '        """Return the complete row in renderer order."""\n'
        "        return self.prefix + self.primary\n\n"
        "    @property\n"
        "    def cell_count(self) -> int:\n"
        '        """Return the row width without allocating a joined tuple."""\n'
        "        return len(self.prefix) + len(self.primary)\n",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "\n\nclass CompileError(ValueError):\n",
        "\n\nFIXED_BLANK_CELL_ENABLED = any(\n"
        "    code == FIXED_BLANK_CELL_CODE for code, _style, _unit in FIXED_ENGLISH_UNITS\n"
        ")\n\n\nclass CompileError(ValueError):\n",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "        expected_cells = sum(len(plan.cells()) for plan in plans)\n",
        "        expected_cells = sum(plan.cell_count for plan in plans)\n",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "            row_cells = len(plan.cells())\n",
        "            row_cells = plan.cell_count\n",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "                fixed_anchor_enabled = any(\n"
        "                    code == FIXED_BLANK_CELL_CODE\n"
        "                    for code, _style, _unit in FIXED_ENGLISH_UNITS\n"
        "                )\n"
        "                if fixed_anchor_enabled and row[: layout.anchor_cells(row_index)] != (\n",
        "                if FIXED_BLANK_CELL_ENABLED and row[: layout.anchor_cells(row_index)] != (\n",
    )
    _replace_between(
        "work/clean_rebuild/mes_compiler.py",
        '    needs_layouts = text_mode == "prose" or bool(adaptive_indexes)\n',
        "    old_to_new = {old: new for new, old in enumerate(retained_indexes)}\n",
        """    needs_layouts = text_mode == "prose" or bool(adaptive_indexes)
    if adaptive_indexes:
        contracts = infer_contracts(
            scn_data,
            retail.record_count,
            set(translated),
            profile,
            retail_records=retail.records,
        )
        layouts = {
            index: contract.layout
            for index, contract in contracts.items()
            if contract.layout is not None
        }
        roles = {
            index: contract.roles
            for index, contract in contracts.items()
            if contract.roles
        }
        row_limits = {
            index: contract.max_rows
            for index, contract in contracts.items()
            if contract.max_rows is not None
        }
    elif needs_layouts:
        layouts = infer_layouts(
            scn_data,
            retail.record_count,
            set(translated),
            profile,
            retail_records=retail.records,
        )
        roles = {}
        row_limits = {}
    else:
        layouts = {}
        roles = {}
        row_limits = {}
    retained_indexes = sorted(
        {
            index
            for record_index in preserved
            for index in _dynamic_indexes(retail.records[record_index])
        }
    )
""",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "    bitmap_to_index = {bitmap: index for index, bitmap in enumerate(glyphs)}\n"
        "    row_plans: list[RowPlan] = []\n",
        "    row_plans: list[RowPlan] = []\n",
    )
    _replace_between(
        "work/clean_rebuild/mes_compiler.py",
        "    generated_frequency: Counter[bytes] = Counter(\n",
        '    if glyph_order == "first-use":\n',
        """    bitmap_rows_by_record = {
        index: [
            tuple(stored_cell(*cell) for cell in plan.cells())
            for plan in plans
        ]
        for index, plans in rows_by_record.items()
    }
    bitmap_rows = [
        bitmap_row
        for index in sorted(bitmap_rows_by_record)
        for bitmap_row in bitmap_rows_by_record[index]
    ]
    generated_frequency: Counter[bytes] = Counter(
        bitmap
        for bitmap_row in bitmap_rows
        for bitmap in bitmap_row
        if bitmap not in fixed_by_bitmap
    )
    generated_first_use: list[bytes] = []
    seen_generated = set(glyphs)
    for bitmap_row in bitmap_rows:
        for bitmap in bitmap_row:
            if bitmap in fixed_by_bitmap or bitmap in seen_generated:
                continue
            seen_generated.add(bitmap)
            generated_first_use.append(bitmap)
""",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "        units = [cell for row in rows_by_record[index] for cell in row.cells()]\n"
        "        rendered_cells += len(units)\n"
        "        encoded = bytearray()\n"
        "        for unit in units:\n"
        "            bitmap = stored_cell(*unit)\n"
        "            fixed_code = fixed_by_bitmap.get(bitmap)\n",
        "        bitmap_rows_for_record = bitmap_rows_by_record[index]\n"
        "        rendered_cells += sum(len(row) for row in bitmap_rows_for_record)\n"
        "        encoded = bytearray()\n"
        "        for bitmap in (\n"
        "            bitmap\n"
        "            for bitmap_row in bitmap_rows_for_record\n"
        "            for bitmap in bitmap_row\n"
        "        ):\n"
        "            fixed_code = fixed_by_bitmap.get(bitmap)\n",
    )
    _replace_once(
        "work/clean_rebuild/mes_compiler.py",
        "    if split_offset > 0xFFFF or any(pointer > 0xFFFF for pointer in pointers):\n",
        "    if split_offset > 0xFFFF:\n",
    )


def _optimize_formatter() -> None:
    """Avoid duplicate normalization, MES parsing, and report classification scans."""
    _replace_function(
        "work/clean_rebuild/translation_formatter.py",
        "_contracts",
        '''def _contracts(
    source: dict[str, object],
    retail_root: Path,
    *,
    retail_records: tuple[bytes, ...] | None = None,
) -> dict[int, RecordContract]:
    """Infer contracts from a chapter's retail SCN and opening MES cells.

    A caller that already parsed the retail MES may supply ``retail_records``
    so auditing and contract inference share that immutable parse.
    """
    chapter = source["chapter"]
    records = source["records"]
    validate_profile(source.get("profile"), chapter=chapter, records=records)
    retail = retail_root / "retail_unpacked" / chapter
    scn = retail / f"{chapter}.SCN"
    mes = retail / f"{chapter}.MES"
    if not scn.exists():
        raise FileNotFoundError(f"missing hash-locked retail SCN: {scn}")
    if not mes.exists():
        raise FileNotFoundError(f"missing hash-locked retail MES: {mes}")
    if retail_records is None:
        retail_records = parse_mes(mes.read_bytes(), source=str(mes)).records
    translated = {
        record["index"]
        for record in records
        if record.get("policy") == "translate"
    }
    return infer_contracts(
        scn.read_bytes(),
        source["record_count"],
        translated,
        source.get("profile"),
        retail_records=retail_records,
    )''',
    )
    _replace_function(
        "work/clean_rebuild/translation_formatter.py",
        "format_preview",
        '''def format_preview(text: str, contract: RecordContract | None) -> list[str]:
    """Return visible, unpadded rows for a proposed semantic string."""
    semantic = normalize_ellipsis_style(normalize_semantic_text(text))
    return _format_semantic_preview(semantic, contract)''',
    )
    _replace_once(
        "work/clean_rebuild/translation_formatter.py",
        "\ndef _renderer_tokens(text: str) -> list[str]:\n",
        '''
def _format_semantic_preview(
    semantic: str, contract: RecordContract | None
) -> list[str]:
    """Wrap already-normalized semantic text without normalizing it again."""
    if contract is None or contract.layout is None:
        return [semantic]
    return wrap_words(semantic, contract.layout)


def _renderer_tokens(text: str) -> list[str]:
''',
    )
    _replace_once(
        "work/clean_rebuild/translation_formatter.py",
        "    rows = format_preview(semantic, contract)\n",
        "    rows = _format_semantic_preview(semantic, contract)\n",
    )
    _replace_once(
        "work/clean_rebuild/translation_formatter.py",
        "        contracts = _contracts(source, retail_root)\n"
        "        retail_records = parse_mes(\n",
        "        retail_records = parse_mes(\n",
    )
    _replace_once(
        "work/clean_rebuild/translation_formatter.py",
        '        ).records\n        text_mode = source["text_mode"]\n',
        "        ).records\n"
        "        contracts = _contracts(\n"
        "            source, retail_root, retail_records=retail_records\n"
        "        )\n"
        '        text_mode = source["text_mode"]\n',
    )
    _replace_between(
        "work/clean_rebuild/translation_formatter.py",
        "    failures = [\n",
        "    migration_failures = (\n",
        """    failures: list[str] = []
    legacy_issues: list[str] = []
    warnings: list[str] = []
    classified: list[dict[str, object]] = []
    unclassified_layouts: list[str] = []
    fixed: list[dict[str, object]] = []
    undeclared: list[dict[str, object]] = []
    anchors: list[dict[str, object]] = []
    unmigrated: list[str] = []
    for item in records:
        item_id = str(item["id"])
        item_failures = item["failures"]
        target = failures if item["adaptive"] else legacy_issues
        target.extend(f"{item_id}: {failure}" for failure in item_failures)
        warnings.extend(
            f"{item_id}: {warning}" for warning in item["warnings"]
        )
        is_classified = bool(item["roles"] or item["layout"])
        if is_classified:
            classified.append(item)
            if item["anchor"]:
                anchors.append(item)
            if not item["adaptive"] and not item["anchor"]:
                unmigrated.append(item_id)
        elif item["layout_policy"] == "fixed":
            fixed.append(item)
        else:
            undeclared.append(item)
        layout = item["layout"]
        if (
            isinstance(layout, dict)
            and layout.get("text_box") == "unclassified"
        ):
            unclassified_layouts.append(item_id)
""",
    )


def _optimize_source_health() -> None:
    """Decode each textual source once per source-health audit."""
    _replace_function(
        "tools/source_health.py",
        "_check_text",
        '''def _check_text(
    path: Path,
    relative: str,
    data: bytes,
    text: str,
    failures: list[str],
) -> None:
    """Validate decoded UTF-8 source text and line-ending hygiene."""
    suffix = path.suffix.lower()
    if b"\\r" in data and suffix != ".ps1":
        failures.append(f"{relative}: contains CR characters; source must use LF")
    if suffix == ".ps1":
        unmatched = data.replace(b"\\r\\n", b"")
        if b"\\r" in unmatched or b"\\n" in unmatched:
            failures.append(
                f"{relative}: PowerShell source must use consistent CRLF endings"
            )
    if data and not data.endswith(b"\\n"):
        failures.append(f"{relative}: missing final newline")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.rstrip(" \\t") != line:
            failures.append(f"{relative}:{line_number}: trailing whitespace")''',
    )
    _replace_function(
        "tools/source_health.py",
        "_check_structured_source",
        '''def _check_structured_source(
    path: Path,
    relative: str,
    text: str,
    failures: list[str],
) -> None:
    """Parse already-decoded Python, JSON, and TOML source text."""
    try:
        if path.suffix == ".py":
            ast.parse(text, filename=relative)
        elif path.suffix == ".json":
            json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
        elif path.suffix == ".toml":
            tomllib.loads(text)
    except (
        SyntaxError,
        json.JSONDecodeError,
        DuplicateJsonKeyError,
        tomllib.TOMLDecodeError,
    ) as exc:
        failures.append(f"{relative}: parse failure: {exc}")''',
    )
    _replace_once(
        "tools/source_health.py",
        "        if suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:\n"
        "            text_files_checked += 1\n"
        "            _check_text(path, relative, failures)\n"
        '        if suffix in {".json", ".py", ".toml"}:\n'
        "            structured_files_checked += 1\n"
        "            _check_structured_source(path, relative, failures)\n",
        "        text: str | None = None\n"
        "        data: bytes | None = None\n"
        "        if suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:\n"
        "            text_files_checked += 1\n"
        "            try:\n"
        "                data = path.read_bytes()\n"
        '                text = data.decode("utf-8")\n'
        "            except UnicodeDecodeError as exc:\n"
        '                failures.append(f"{relative}: not valid UTF-8: {exc}")\n'
        "            else:\n"
        "                _check_text(path, relative, data, text, failures)\n"
        '        if suffix in {".json", ".py", ".toml"}:\n'
        "            structured_files_checked += 1\n"
        "            if text is not None:\n"
        "                _check_structured_source(path, relative, text, failures)\n",
    )


def _optimize_exporter() -> None:
    """Cache immutable glyph rasters and use native Adler-32."""
    _replace_once(
        "work/clean_rebuild/export_bilingual_comparison.py",
        "import zipfile\nfrom pathlib import Path, PurePosixPath\n",
        "import zipfile\nimport zlib\nfrom functools import lru_cache\nfrom pathlib import Path, PurePosixPath\n",
    )
    _replace_function(
        "work/clean_rebuild/export_bilingual_comparison.py",
        "_glyph_matrix",
        '''@lru_cache(maxsize=None)
def _glyph_matrix(stored: bytes) -> tuple[tuple[int, ...], ...]:
    """Decode and rotate one native glyph once per unique stored bitmap."""
    if len(stored) != GLYPH_BYTES:
        raise ValueError(f"glyph has {len(stored)} bytes, expected {GLYPH_BYTES}")
    bits = [(byte >> shift) & 1 for byte in stored for shift in range(7, -1, -1)]
    source = [
        bits[row * GLYPH_WIDTH : (row + 1) * GLYPH_WIDTH]
        for row in range(GLYPH_HEIGHT)
    ]
    return tuple(
        tuple(source[x][GLYPH_WIDTH - 1 - y] for x in range(GLYPH_WIDTH))
        for y in range(GLYPH_HEIGHT)
    )''',
    )
    _replace_function(
        "work/clean_rebuild/export_bilingual_comparison.py",
        "_adler32",
        '''def _adler32(payload: bytes) -> int:
    """Return the RFC 1950 Adler-32 checksum through CPython's native codec."""
    return zlib.adler32(payload) & 0xFFFFFFFF''',
    )
    _replace_once(
        "work/clean_rebuild/export_bilingual_comparison.py",
        "\ndef _render_record(\n",
        '''
@lru_cache(maxsize=None)
def _scaled_black_offsets(
    glyph: bytes, scale: int
) -> tuple[tuple[int, int], ...]:
    """Return cached scaled black-pixel offsets for one immutable glyph."""
    offsets: list[tuple[int, int]] = []
    for y, source_row in enumerate(_glyph_matrix(glyph)):
        for x, bit in enumerate(source_row):
            if not bit:
                continue
            x_base = x * scale
            y_base = y * scale
            offsets.extend(
                (x_base + dx, y_base + dy)
                for dy in range(scale)
                for dx in range(scale)
            )
    return tuple(offsets)


def _render_record(
''',
    )
    _replace_function(
        "work/clean_rebuild/export_bilingual_comparison.py",
        "_render_record",
        '''def _render_record(
    glyphs: list[bytes], output: Path, *, columns: int = 48
) -> tuple[int, int]:
    """Render one record while reusing cached immutable glyph rasters."""
    scale = 2
    padding = 4
    cell = GLYPH_WIDTH * scale
    if glyphs:
        used_columns = min(columns, len(glyphs))
        rows = (len(glyphs) + columns - 1) // columns
        width = padding * 2 + used_columns * cell
        height = padding * 2 + rows * cell
        row_bytes = (width + 7) // 8
        pixels = bytearray([0xFF]) * (row_bytes * height)
        for index, glyph in enumerate(glyphs):
            row, column = divmod(index, columns)
            x_base = padding + column * cell
            y_base = padding + row * cell
            for x_offset, y_offset in _scaled_black_offsets(glyph, scale):
                _set_black(
                    pixels,
                    row_bytes,
                    x_base + x_offset,
                    y_base + y_offset,
                )
    else:
        width, height = 240, 32
        pixels = _blank_placeholder(width, height)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_encode_monochrome_png(width, height, bytes(pixels)))
    return width, height''',
    )
    _replace_once(
        "work/clean_rebuild/export_bilingual_comparison.py",
        "        if (\n"
        '            mes_path.stat().st_size != canonical["retail_mes"]["size"]\n'
        '            or sha256(mes_path) != canonical["retail_mes"]["sha256"]\n'
        "        ):\n",
        "        mes_size = mes_path.stat().st_size\n"
        "        mes_digest = sha256(mes_path)\n"
        "        if (\n"
        '            mes_size != canonical["retail_mes"]["size"]\n'
        '            or mes_digest != canonical["retail_mes"]["sha256"]\n'
        "        ):\n",
    )
    _replace_once(
        "work/clean_rebuild/export_bilingual_comparison.py",
        '                "retail_mes_sha256": sha256(mes_path),\n',
        '                "retail_mes_sha256": mes_digest,\n',
    )


def _optimize_whole_game() -> None:
    """Reuse canonical chapter loads and stream large build-identity hashes."""
    _replace_function(
        "work/clean_rebuild/whole_game_test.py",
        "_compiled_static_summary",
        '''def _compiled_static_summary(
    retail_root: Path,
    index: dict[str, Any],
    sources_by_chapter: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compile all chapters using already-loaded canonical source objects."""
    failures: list[str] = []
    totals: Counter[str] = Counter()
    for chapter_item in index["chapters"]:
        chapter = chapter_item["chapter"]
        retail = retail_root / "retail_unpacked" / chapter
        try:
            result = compile_mes(
                (retail / f"{chapter}.MES").read_bytes(),
                (retail / f"{chapter}.SCN").read_bytes(),
                sources_by_chapter[chapter],
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
    }''',
    )
    _replace_once(
        "work/clean_rebuild/whole_game_test.py",
        "    layout = audit_layouts(retail_root)\n"
        "    compiled = _compiled_static_summary(retail_root)\n"
        "    scn_integrity = audit_project_scn_references(retail_root)\n"
        '    index = _load(SOURCES / "index.json")\n',
        '    index = _load(SOURCES / "index.json")\n'
        "    sources_by_chapter = {\n"
        '        str(item["chapter"]): _load(SOURCES / item["source"])\n'
        '        for item in index["chapters"]\n'
        "    }\n"
        "    layout = audit_layouts(retail_root)\n"
        "    compiled = _compiled_static_summary(\n"
        "        retail_root, index, sources_by_chapter\n"
        "    )\n"
        "    scn_integrity = audit_project_scn_references(retail_root)\n",
    )
    _replace_once(
        "work/clean_rebuild/whole_game_test.py",
        '        source = _load(SOURCES / chapter_item["source"])\n',
        "        source = sources_by_chapter[chapter]\n",
    )
    _replace_once(
        "work/clean_rebuild/whole_game_test.py",
        "\ndef bind_build_identity(plan: dict[str, Any], cue: Path, track1: Path) -> None:\n",
        '''
def _sha256_file(path: Path) -> str:
    """Return an uppercase SHA-256 digest without loading a large file whole."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def bind_build_identity(plan: dict[str, Any], cue: Path, track1: Path) -> None:
''',
    )
    _replace_once(
        "work/clean_rebuild/whole_game_test.py",
        '        "cue_sha256": hashlib.sha256(cue.read_bytes()).hexdigest().upper(),\n'
        '        "track1_filename": track1.name,\n'
        '        "track1_sha256": hashlib.sha256(track1.read_bytes()).hexdigest().upper(),\n',
        '        "cue_sha256": _sha256_file(cue),\n'
        '        "track1_filename": track1.name,\n'
        '        "track1_sha256": _sha256_file(track1),\n',
    )


def _extend_regressions() -> None:
    """Add focused equivalence tests for the new fast paths."""
    _replace_once(
        "tests/test_performance_equivalence.py",
        "import unittest\nfrom pathlib import Path\n",
        "import unittest\nimport zlib\nfrom pathlib import Path\n",
    )
    _replace_once(
        "tests/test_performance_equivalence.py",
        "from work.clean_rebuild import lz_format\n"
        "from work.clean_rebuild import mes_compiler\n"
        "from work.clean_rebuild import raw_cd\n",
        "from work.clean_rebuild import export_bilingual_comparison\n"
        "from work.clean_rebuild import lz_format\n"
        "from work.clean_rebuild import mes_compiler\n"
        "from work.clean_rebuild import raw_cd\n"
        "from work.clean_rebuild import scn_layout\n",
    )
    _replace_once(
        "tests/test_performance_equivalence.py",
        '            b"A" * 96,\n',
        '            b"A" * 96,\n            b"AB" * 256,\n',
    )
    _replace_once(
        "tests/test_performance_equivalence.py",
        "\n\nclass RawCdFastPathEquivalenceTests(unittest.TestCase):\n",
        '''

class ScnInventoryEquivalenceTests(unittest.TestCase):
    """Require contract inference to inventory each SCN only once."""

    def test_contracts_share_one_display_inventory(self) -> None:
        """Build role/layout/row contracts from one structural inventory."""
        scn = bytes((0x21, 0x00, 0x01, 0x00, 0x02))
        with patch.object(
            scn_layout,
            "display_occurrences",
            wraps=scn_layout.display_occurrences,
        ) as inventory:
            contracts = scn_layout.infer_contracts(
                scn,
                2,
                {0, 1},
                {},
                retail_records=(b"\\0", b"\\0"),
            )
        self.assertEqual(inventory.call_count, 1)
        self.assertIn(scn_layout.ROLE_SPEAKER, contracts[0].roles)
        self.assertEqual(
            contracts[1].layout.text_box,
            scn_layout.TEXT_BOX_LOWER_DIALOGUE,
        )


class ComparisonExporterFastPathTests(unittest.TestCase):
    """Check deterministic glyph and checksum fast paths directly."""

    def test_scaled_glyph_offsets_are_cached(self) -> None:
        """Reuse decoded/scaled raster work for repeated immutable glyphs."""
        glyph = bytes(range(export_bilingual_comparison.GLYPH_BYTES))
        export_bilingual_comparison._glyph_matrix.cache_clear()
        export_bilingual_comparison._scaled_black_offsets.cache_clear()
        first = export_bilingual_comparison._scaled_black_offsets(glyph, 2)
        second = export_bilingual_comparison._scaled_black_offsets(glyph, 2)
        self.assertEqual(first, second)
        self.assertEqual(
            export_bilingual_comparison._scaled_black_offsets.cache_info().hits,
            1,
        )

    def test_native_adler32_matches_standard_result(self) -> None:
        """Keep deterministic PNG zlib checksums byte-identical."""
        payload = bytes(range(256)) * 41
        self.assertEqual(
            export_bilingual_comparison._adler32(payload),
            zlib.adler32(payload) & 0xFFFFFFFF,
        )


class RawCdFastPathEquivalenceTests(unittest.TestCase):
''',
    )


def _update_docs() -> None:
    """Document the new performance architecture and standards contract."""
    _replace_once(
        "docs/PERFORMANCE.md",
        "`stored_cell()` is deterministic for an immutable `(style, unit)` pair, so its\n"
        "rendered 12x12 bitmap is now memoized. The row-phase optimizer also returns\n"
        "immediately when no row has an alternate phase, which is the current normal\n"
        "compiler path. Tests explicitly cover both shortcuts.\n\n"
        "These were accepted as low-risk reductions in repeated work. They are not\n"
        "presented as major end-to-end wins because the retail benchmark identified LZ\n"
        "compression and raw-sector parity generation as the dominant costs.\n",
        "`stored_cell()` remains memoized for immutable `(style, unit)` pairs. The MES\n"
        "compiler now materializes each row's glyph bitmaps once and reuses that bitmap\n"
        "plan for frequency ordering, first-use ordering, and final record encoding. It\n"
        "also avoids tuple joins used only to count cells, duplicate retained-glyph\n"
        "sorting, constant dictionary scans, and a redundant pointer-range pass.\n\n"
        "These are low-risk reductions in repeated Python work. They are not presented\n"
        "as dominant end-to-end wins because LZ compression and raw-sector parity\n"
        "generation remain the principal binary-processing costs.\n",
    )
    performance_path = _path("docs/PERFORMANCE.md")
    performance = performance_path.read_text(encoding="utf-8")
    marker = "## Investigated non-hotspots\n"
    addition = """## September 6, 2026 follow-up efficiency pass

The follow-up pass removes repeated work that remained after the major codec and
raw-disc optimizations:

- SCN role, geometry, and row-limit inference now share one structural display
  inventory per contract build instead of independently rescanning commands.
- Long LZ copy matches are represented as intervals. A range-minimum DP query
  selects the best legal long-copy predecessor without allocating every length
  from 5 through the maximum match. Legacy-byte equivalence remains mandatory.
- The bilingual exporter caches decoded and 2x-scaled immutable glyph rasters,
  uses the native Adler-32 implementation, and reuses each retail MES digest.
- Source-health validation decodes each text source once before both hygiene and
  parser checks.
- Whole-game planning reuses canonical chapter objects inside the plan build and
  streams large CUE/Track 1 identity hashes instead of loading Track 1 whole.
- Translation auditing avoids duplicate semantic normalization, shares an
  already-parsed retail MES with renderer-contract inference, and classifies the
  final audit report in one pass.

The regression suite preserves the older compressor as a reference algorithm
and compares emitted compressed bytes, including a long repetitive corpus that
exercises the new range-minimum path.

"""
    if marker not in performance:
        raise RuntimeError("docs/PERFORMANCE.md: insertion marker is missing")
    performance_path.write_text(
        performance.replace(marker, addition + marker),
        encoding="utf-8",
        newline="\n",
    )
    _replace_once(
        "docs/DOCSTRING_STANDARD.md",
        "Python 3.12 is the minimum supported interpreter. Ruff owns generic linting and\n"
        "modernization checks with the repository's 88-column target. Source text uses\n"
        "UTF-8, LF line endings, a final newline, and no trailing whitespace.\n",
        "Python 3.12 is the minimum supported interpreter. Ruff format is the canonical\n"
        "layout engine with a 79-column target. Ruff's pycodestyle rules enforce the\n"
        "PEP 8 lint contract, while its pydocstyle `pep257` convention enforces PEP 257\n"
        "for maintained public APIs. `E501` is excluded because Ruff's formatter may\n"
        "retain intrinsically unbreakable strings; ordinary code is still formatted to\n"
        "the 79-column target. Source text uses UTF-8, LF line endings, a final newline,\n"
        "and no trailing whitespace.\n",
    )


def main() -> None:
    """Apply every deterministic transformation in the efficiency campaign."""
    _configure_standards()
    _optimize_lz()
    _optimize_scn_contracts()
    _optimize_compiler()
    _optimize_formatter()
    _optimize_source_health()
    _optimize_exporter()
    _optimize_whole_game()
    _extend_regressions()
    _update_docs()


if __name__ == "__main__":
    main()

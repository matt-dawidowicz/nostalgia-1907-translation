#!/usr/bin/env python3
"""Apply benchmark-proven performance edits on the dedicated perf branch."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    begin = text.index(start)
    finish = text.index(end, begin)
    path.write_text(text[:begin] + replacement + text[finish:], encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected exactly one match for {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


lz = ROOT / "work" / "clean_rebuild" / "lz_format.py"
replace_once(lz, "import bisect\nfrom dataclasses import dataclass\n", "import bisect\nfrom collections import deque\nfrom dataclasses import dataclass\n")
replace_between(
    lz,
    "def _copy_candidates(\n",
    "def _choose_operations(data: bytes) -> list[tuple[int, Op]]:\n",
    '''def _copy_candidates(\n    data: bytes, positions: dict[int, list[int]], position: int\n) -> list[Op]:\n    """Enumerate encodable copies ending at ``position``.\n\n    Copy commands require at least two bytes, so candidates are indexed by the\n    two-byte sequence ending at each possible source position.  This preserves\n    the original ascending source order and therefore deterministic tie\n    breaking, while avoiding the much larger set of one-byte false matches.\n    """\n    max_distance = min(0xFFF, len(data) - position)\n    if position < 2 or max_distance <= 0:\n        return []\n    key = (data[position - 2] << 8) | data[position - 1]\n    matching = positions.get(key, [])\n    first = bisect.bisect_left(matching, position)\n    last = bisect.bisect_right(matching, position - 1 + max_distance)\n    operations: list[Op] = []\n    for source in matching[first:last]:\n        distance = source - (position - 1)\n        length = _match_length(data, position, distance, min(256, position))\n        if length >= 2 and distance <= 0xFF:\n            operations.append(("copy2", 2, distance))\n        if length >= 3 and distance <= 0x1FF:\n            operations.append(("copy3", 3, distance))\n        if length >= 4 and distance <= 0x3FF:\n            operations.append(("copy4", 4, distance))\n        operations.extend(\n            ("copylong", candidate_length, distance)\n            for candidate_length in range(5, length + 1)\n        )\n    return operations\n\n\n''',
)
replace_between(
    lz,
    "def _choose_operations(data: bytes) -> list[tuple[int, Op]]:\n",
    "def _pack_stream(bits: list[int], unpacked_size: int) -> bytes:\n",
    '''def _choose_operations(data: bytes) -> list[tuple[int, Op]]:\n    """Find the minimum-bit backward parse with deterministic tie breaking.\n\n    Literal costs are affine in run length, so the long-literal range can use\n    a monotonic sliding minimum instead of rescanning up to 256 predecessors at\n    every byte.  Equal-cost minima retain the shortest literal, exactly matching\n    the previous ascending-length loop.\n    """\n    positions: dict[int, list[int]] = {}\n    for endpoint in range(1, len(data)):\n        key = (data[endpoint - 1] << 8) | data[endpoint]\n        positions.setdefault(key, []).append(endpoint)\n    infinity = 10**18\n    costs = [infinity] * (len(data) + 1)\n    choices: list[Op | None] = [None] * (len(data) + 1)\n    costs[0] = 0\n    long_literals: deque[tuple[int, int]] = deque()\n    for position in range(1, len(data) + 1):\n        # Lengths 1..8 have a five-bit command overhead.  There are only eight\n        # candidates, so evaluating them directly is cheaper and preserves the\n        # original shortest-length tie preference.\n        for length in range(1, min(8, position) + 1):\n            cost = costs[position - length] + 5 + length * 8\n            if cost < costs[position]:\n                costs[position] = cost\n                choices[position] = ("literal", length, 0)\n\n        # Lengths 9..264 cost costs[j] + 11 + 8*(position-j).\n        # Maintain the minimum of costs[j] - 8*j over the legal predecessor\n        # window.  Newer equal minima replace older ones so ties choose the\n        # larger j, i.e. the shorter literal, matching the legacy loop.\n        eligible = position - 9\n        if eligible >= 0:\n            value = costs[eligible] - 8 * eligible\n            while long_literals and value <= long_literals[-1][1]:\n                long_literals.pop()\n            long_literals.append((eligible, value))\n        minimum_index = position - 264\n        while long_literals and long_literals[0][0] < minimum_index:\n            long_literals.popleft()\n        if long_literals:\n            predecessor = long_literals[0][0]\n            length = position - predecessor\n            cost = costs[predecessor] + 11 + length * 8\n            if cost < costs[position]:\n                costs[position] = cost\n                choices[position] = ("literal", length, 0)\n\n        for operation in _copy_candidates(data, positions, position):\n            cost = costs[position - operation[1]] + _op_cost(operation)\n            if cost < costs[position]:\n                costs[position] = cost\n                choices[position] = operation\n\n    selected: list[tuple[int, Op]] = []\n    position = len(data)\n    while position:\n        operation = choices[position]\n        if operation is None:\n            raise LzError(f"compressor could not cover byte {position}")\n        selected.append((position, operation))\n        position -= operation[1]\n    return selected\n\n\n''',
)

raw = ROOT / "work" / "clean_rebuild" / "raw_cd.py"
replace_between(
    raw,
    "def iso_to_raw_fixed(\n",
    "def verify_track(\n",
    '''def iso_to_raw_fixed(\n    template_raw_path: Path,\n    iso_path: Path,\n    output_raw_path: Path,\n    *,\n    trust_template_checksums: bool = False,\n) -> int:\n    """Rebuild Track 1 using retail raw sectors as an exact-size template.\n\n    The logical ISO must contain exactly one user-data payload per template\n    sector. Headers are preserved from retail. Changed user-data sectors receive\n    freshly generated EDC/ECC. When ``trust_template_checksums`` is true, an\n    unchanged user-data sector is copied byte-for-byte instead; callers may use\n    that fast path only after independently authenticating the complete template\n    bytes (the clean rebuild does so with the frozen retail SHA-256).\n\n    Returns:\n        Number of raw sectors written.\n\n    Raises:\n        RawCdError: If sizes, headers, or rebuilt geometry violate the\n            fixed-geometry contract.\n    """\n    raw_size = template_raw_path.stat().st_size\n    iso_size = iso_path.stat().st_size\n    if raw_size % RAW_SECTOR_SIZE:\n        raise RawCdError("template Track 1 has a partial raw sector")\n    if iso_size % ISO_SECTOR_SIZE:\n        raise RawCdError("ISO has a partial user-data sector")\n    raw_sectors = raw_size // RAW_SECTOR_SIZE\n    iso_sectors = iso_size // ISO_SECTOR_SIZE\n    if iso_sectors != raw_sectors:\n        raise RawCdError(\n            "fixed-geometry rebuild requires identical sector counts: "\n            f"retail={raw_sectors}, rebuilt={iso_sectors}"\n        )\n\n    output_raw_path.parent.mkdir(parents=True, exist_ok=True)\n    with (\n        template_raw_path.open("rb") as template,\n        iso_path.open("rb") as iso,\n        output_raw_path.open("wb") as output,\n    ):\n        for sector_index in range(raw_sectors):\n            sector = bytearray(template.read(RAW_SECTOR_SIZE))\n            payload = iso.read(ISO_SECTOR_SIZE)\n            validate_sector_header(sector, sector_index)\n            if len(payload) != ISO_SECTOR_SIZE:\n                raise RawCdError(f"sector {sector_index}: short ISO read")\n            original_payload = sector[\n                USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE\n            ]\n            if trust_template_checksums and payload == original_payload:\n                output.write(sector)\n                continue\n            sector[USER_DATA_OFFSET : USER_DATA_OFFSET + ISO_SECTOR_SIZE] = payload\n            regenerate_checksums(sector)\n            output.write(sector)\n    return raw_sectors\n\n\n''',
)

prepare = ROOT / "work" / "clean_rebuild" / "prepare_retail.py"
replace_once(
    prepare,
    "    sector_count = raw_to_iso(track1, retail_iso, verify=True)\n",
    "    # The complete Track 1 bytes were authenticated against the frozen retail\n    # SHA-256 immediately above, so recomputing every sector's EDC/ECC here adds\n    # CPU cost without increasing confidence in this exact accepted input.\n    sector_count = raw_to_iso(track1, retail_iso, verify=False)\n",
)

rebuild = ROOT / "work" / "clean_rebuild" / "rebuild.py"
replace_once(
    rebuild,
    "    iso_to_raw_fixed(track1, build_root / \"translated.iso\", output_track1)\n",
    "    iso_to_raw_fixed(\n        track1,\n        build_root / \"translated.iso\",\n        output_track1,\n        trust_template_checksums=True,\n    )\n",
)

font = ROOT / "work" / "clean_rebuild" / "font_render.py"
replace_once(font, "from pathlib import Path\n", "from functools import lru_cache\nfrom pathlib import Path\n")
replace_once(
    font,
    "def stored_cell(style: str, unit: str) -> bytes:\n",
    "@lru_cache(maxsize=None)\ndef stored_cell(style: str, unit: str) -> bytes:\n",
)

compiler = ROOT / "work" / "clean_rebuild" / "mes_compiler.py"
replace_once(
    compiler,
    "    \"\"\"Choose row phases that minimize actual record-plus-glyph-tail bytes.\"\"\"\n    retained = set(retained_glyphs)\n",
    "    \"\"\"Choose row phases that minimize actual record-plus-glyph-tail bytes.\"\"\"\n    if not any(row.alternate is not None for row in rows):\n        return\n\n    retained = set(retained_glyphs)\n",
)

print("performance edits applied")

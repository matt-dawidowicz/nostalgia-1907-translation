#!/usr/bin/env python3
"""Export record-aligned retail Japanese glyphs and canonical English text.

The comparison package is regenerated in a fresh run-specific staging tree and
published only after exact-inventory validation. Japanese is rendered directly
from the hash-locked retail fixed and dynamic bitmap glyphs; OCR and invented
Unicode transcription are deliberately excluded. Canonical English, policy,
source tokens, controls, and bytes remain aligned by stable zero-based
``CHAPTER:NNN`` record IDs.

Archive bytes are deterministic for identical input bytes and identical
exporter source under the same CPython major/minor runtime. Text always uses
UTF-8 with LF line endings. PNGs use a metadata-free grayscale encoder with a
specified stored-DEFLATE stream, and the ZIP uses a fully specified stored-entry
writer. Operating-system metadata, Pillow, and compression-library heuristics
therefore cannot change the package bytes. Cross-Python-version byte identity is
not promised because standard-library text serialization is not project-frozen.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import html
import json
import os
import platform
import shutil
import struct
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from mes_format import read_mes
from source_json import load_json_object


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
SOURCES = HERE / "sources"
DEFAULT_RETAIL_ROOT = HERE / "retail_reference"
DEFAULT_OUTPUT = WORKSPACE / "outputs" / "Nostalgia1907_Bilingual_Comparison"
GLYPH_BYTES = 18
GLYPH_WIDTH = 12
GLYPH_HEIGHT = 12
FIXED_FONT_SIZE = 4284
FIXED_FONT_SHA256 = "0204DBCA3D3DC2C1B23CCC3FC10FC61DD2F1054805619B2E953247E61A1C954A"
DYNAMIC_GLYPHS_PER_PREFIX = 0xFF
EXPECTED_CHAPTERS = 19
EXPECTED_RECORDS = 2905
JSON_NAME = "Nostalgia1907_Japanese_English_Comparison.json"
HTML_NAME = "Nostalgia1907_Japanese_English_Comparison.html"
MARKDOWN_NAME = "Nostalgia1907_Japanese_English_Comparison.md"
ZIP_NAME = "Nostalgia1907_Japanese_English_Comparison.zip"
PACKAGE_MANIFEST_NAME = "Nostalgia1907_Japanese_English_Comparison.manifest.json"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ZIP_DOS_DATE = 0x0021
ZIP_DOS_TIME = 0x0000
ZIP_VERSION_NEEDED = 20
ZIP_VERSION_MADE_BY = (3 << 8) | ZIP_VERSION_NEEDED
ZIP_EXTERNAL_FILE_ATTR = 0o100644 << 16


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _sha256_bytes(payload: bytes) -> str:
    """Return an uppercase SHA-256 digest for in-memory bytes."""
    return hashlib.sha256(payload).hexdigest().upper()


def _write_text_lf(path: Path, value: str) -> None:
    """Write UTF-8 text with explicit LF newlines on every platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(value)


def _glyph_matrix(stored: bytes) -> list[list[int]]:
    """Decode and rotate one native stored glyph into upright screen order."""
    if len(stored) != GLYPH_BYTES:
        raise ValueError(f"glyph has {len(stored)} bytes, expected {GLYPH_BYTES}")
    bits = [(byte >> shift) & 1 for byte in stored for shift in range(7, -1, -1)]
    source = [
        bits[row * GLYPH_WIDTH : (row + 1) * GLYPH_WIDTH] for row in range(GLYPH_HEIGHT)
    ]
    # Retail glyphs are stored clockwise relative to the visible screen glyph.
    return [
        [source[x][GLYPH_WIDTH - 1 - y] for x in range(GLYPH_WIDTH)]
        for y in range(GLYPH_HEIGHT)
    ]


def _record_glyphs(
    record: bytes,
    fixed_glyphs: tuple[bytes, ...],
    dynamic_glyphs: tuple[bytes, ...],
) -> tuple[list[bytes], list[str], str]:
    """Resolve visible glyphs, controls, and a lossless token description."""
    glyphs: list[bytes] = []
    controls: list[str] = []
    tokens: list[str] = []
    offset = 0
    while offset < len(record):
        value = record[offset]
        if value == 0:
            tokens.append("<END>")
            offset += 1
        elif value == 0xEE:
            controls.append("EE")
            tokens.append("<EE>")
            offset += 1
        elif value >= 0xF0:
            if offset + 1 >= len(record):
                raise ValueError("truncated dynamic glyph reference")
            low = record[offset + 1]
            if low == 0:
                raise ValueError("forbidden zero dynamic glyph value")
            index = (value - 0xF0) * DYNAMIC_GLYPHS_PER_PREFIX + low - 1
            if index >= len(dynamic_glyphs):
                raise ValueError(f"dynamic glyph {index} exceeds the MES bank")
            glyphs.append(dynamic_glyphs[index])
            tokens.append(f"<DYN:{index:03d}>")
            offset += 2
        elif 1 <= value <= 0xED:
            index = value - 1
            if index >= len(fixed_glyphs):
                raise ValueError(f"fixed glyph 0x{value:02X} exceeds FIX_CODE.FNT")
            glyphs.append(fixed_glyphs[index])
            tokens.append(f"<FIX:{value:02X}>")
            offset += 1
        else:
            raise ValueError(f"unsupported MES byte 0x{value:02X}")
    return glyphs, controls, "".join(tokens)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """Return one PNG chunk with a deterministic CRC."""
    if len(kind) != 4:
        raise ValueError("PNG chunk type must be exactly four bytes")
    crc = binascii.crc32(kind)
    crc = binascii.crc32(payload, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _adler32(payload: bytes) -> int:
    """Return the RFC 1950 Adler-32 checksum without a codec dependency."""
    first = 1
    second = 0
    modulus = 65521
    for offset in range(0, len(payload), 5552):
        for value in payload[offset : offset + 5552]:
            first += value
            second += first
        first %= modulus
        second %= modulus
    return (second << 16) | first


def _stored_zlib_stream(payload: bytes) -> bytes:
    """Encode bytes as a fully specified stored-block zlib stream."""
    output = bytearray(b"\x78\x01")
    if not payload:
        blocks = (b"",)
    else:
        blocks = tuple(
            payload[offset : offset + 65535] for offset in range(0, len(payload), 65535)
        )
    for index, block in enumerate(blocks):
        output.append(0x01 if index == len(blocks) - 1 else 0x00)
        length = len(block)
        output.extend(struct.pack("<HH", length, 0xFFFF - length))
        output.extend(block)
    output.extend(struct.pack(">I", _adler32(payload)))
    return bytes(output)


def _encode_monochrome_png(width: int, height: int, pixels: bytes) -> bytes:
    """Encode a packed one-bit grayscale raster without metadata or heuristics."""
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    row_bytes = (width + 7) // 8
    if len(pixels) != row_bytes * height:
        raise ValueError("monochrome raster length does not match its dimensions")
    scanlines = bytearray((row_bytes + 1) * height)
    for row in range(height):
        source_start = row * row_bytes
        target_start = row * (row_bytes + 1)
        scanlines[target_start] = 0
        scanlines[target_start + 1 : target_start + 1 + row_bytes] = pixels[
            source_start : source_start + row_bytes
        ]
    header = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return b"".join(
        (
            PNG_SIGNATURE,
            _png_chunk(b"IHDR", header),
            _png_chunk(b"IDAT", _stored_zlib_stream(bytes(scanlines))),
            _png_chunk(b"IEND", b""),
        )
    )


def _set_black(pixels: bytearray, row_bytes: int, x: int, y: int) -> None:
    """Clear one packed grayscale bit so the pixel renders black."""
    pixels[y * row_bytes + x // 8] &= ~(0x80 >> (x % 8))


def _blank_placeholder(width: int, height: int) -> bytearray:
    """Return a deterministic control-only placeholder raster."""
    row_bytes = (width + 7) // 8
    pixels = bytearray([0xFF]) * (row_bytes * height)
    left, right = 6, width - 7
    top, bottom = 7, height - 8
    for x in range(left, right + 1):
        _set_black(pixels, row_bytes, x, top)
        _set_black(pixels, row_bytes, x, bottom)
    for y in range(top, bottom + 1):
        _set_black(pixels, row_bytes, left, y)
        _set_black(pixels, row_bytes, right, y)
    center = height // 2
    for x in range(20, width - 20):
        if (x // 8) % 2 == 0:
            _set_black(pixels, row_bytes, x, center)
    return pixels


def _render_record(
    glyphs: list[bytes], output: Path, *, columns: int = 48
) -> tuple[int, int]:
    """Render one record's original Japanese glyphs without OCR or resampling."""
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
            matrix = _glyph_matrix(glyph)
            for y, source_row in enumerate(matrix):
                for x, bit in enumerate(source_row):
                    if not bit:
                        continue
                    target_x = x_base + x * scale
                    target_y = y_base + y * scale
                    for dy in range(scale):
                        for dx in range(scale):
                            _set_black(
                                pixels,
                                row_bytes,
                                target_x + dx,
                                target_y + dy,
                            )
    else:
        width, height = 240, 32
        pixels = _blank_placeholder(width, height)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_encode_monochrome_png(width, height, bytes(pixels)))
    return width, height


def _chapter_markdown(chapter: dict[str, object], *, image_prefix: str = "") -> str:
    """Return one image-and-text comparison chapter."""
    lines = [f"# {chapter['chapter']}", ""]
    for record in chapter["records"]:
        lines.extend(
            [
                f"## {record['id']}",
                "",
                "Japanese (original retail glyphs):",
                "",
                f"![{record['id']} Japanese]({image_prefix}{record['japanese_image']})",
                "",
                "English:",
                "",
            ]
        )
        if record["english"] is None or not record["english"]:
            lines.extend(["_[No canonical English prose / control-only record]_", ""])
        else:
            lines.extend(["```text", record["english"], "```", ""])
        if record["controls"]:
            lines.extend([f"Controls: `{', '.join(record['controls'])}`", ""])
    return "\n".join(lines).rstrip() + "\n"


def _comparison_html(chapters: list[dict[str, object]]) -> str:
    """Return one searchable side-by-side comparison document."""
    sections: list[str] = []
    options = ['<option value="">All chapters</option>']
    for chapter in chapters:
        name = str(chapter["chapter"])
        options.append(
            f'<option value="{html.escape(name)}">{html.escape(name)}</option>'
        )
        records: list[str] = []
        for record in chapter["records"]:
            english = record["english"]
            english_display = (
                html.escape(english)
                if english
                else "<em>No canonical English prose / control-only record</em>"
            )
            search = html.escape(f"{record['id']} {english or ''}".lower(), quote=True)
            controls = (
                f'<div class="controls">Control bytes: {html.escape(", ".join(record["controls"]))}</div>'
                if record["controls"]
                else ""
            )
            records.append(
                f"""<article class="record" data-chapter="{html.escape(name)}" data-search="{search}">
<div class="record-id"><a href="#{html.escape(record['id'])}" id="{html.escape(record['id'])}">{html.escape(record['id'])}</a></div>
<div class="jp"><div class="label">Japanese — original retail bitmap glyphs</div>
<img src="{html.escape(record['japanese_image'])}" alt="Original Japanese glyphs for {html.escape(record['id'])}" loading="lazy"></div>
<div class="en"><div class="label">English — canonical translation</div><pre>{english_display}</pre>{controls}</div>
</article>"""
            )
        sections.append(
            f'<section class="chapter" data-chapter-section="{html.escape(name)}"><h2>{html.escape(name)}</h2>{"".join(records)}</section>'
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nostalgia 1907 Japanese / English Comparison</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
body {{ margin: 0; background: #f3eee2; color: #241b12; }}
header {{ position: sticky; top: 0; z-index: 4; background: #2d2116; color: white; padding: 14px 18px; box-shadow: 0 2px 8px #0005; }}
h1 {{ font-size: 1.25rem; margin: 0 0 7px; }}
.notice {{ font-size: .88rem; color: #eadbc8; margin: 0 0 10px; max-width: 1100px; }}
.tools {{ display: flex; gap: 8px; flex-wrap: wrap; }}
input, select {{ font: inherit; padding: 7px 9px; border-radius: 5px; border: 1px solid #9f8d75; min-width: 210px; }}
main {{ max-width: 1500px; margin: auto; padding: 12px; }}
h2 {{ margin: 24px 0 8px; border-bottom: 2px solid #80633f; padding-bottom: 4px; }}
.record {{ display: grid; grid-template-columns: 108px minmax(400px, 1fr) minmax(340px, .9fr); background: white; margin: 8px 0; border: 1px solid #cbbba5; border-radius: 7px; overflow: hidden; }}
.record-id {{ padding: 12px; background: #e4d5bd; font: 600 .9rem ui-monospace, monospace; }}
.record-id a {{ color: #5d3519; text-decoration: none; }}
.jp, .en {{ padding: 10px 12px; min-width: 0; }}
.jp {{ border-right: 1px solid #ddd0bd; overflow-x: auto; }}
.label {{ font-size: .75rem; font-weight: 700; color: #70583f; text-transform: uppercase; margin-bottom: 7px; }}
.jp img {{ display: block; image-rendering: pixelated; max-width: none; border: 1px solid #ddd; background: white; }}
pre {{ white-space: pre-wrap; margin: 0; font: 1rem/1.4 ui-monospace, Consolas, monospace; }}
.controls {{ margin-top: 8px; font-size: .78rem; color: #8b261e; }}
.hidden {{ display: none !important; }}
@media (max-width: 950px) {{ .record {{ grid-template-columns: 90px 1fr; }} .en {{ grid-column: 2; border-top: 1px solid #ddd0bd; }} .jp {{ border-right: 0; }} }}
</style></head><body>
<header><h1>Nostalgia 1907 — Japanese / English Record Comparison</h1>
<p class="notice">Japanese is rendered losslessly from the original retail 12×12 glyph bitmaps, not OCR. English is the exact canonical rebuild source. Use stable IDs such as PART3C:194 when proposing changes.</p>
<div class="tools"><input id="search" type="search" placeholder="Filter ID or English text"><select id="chapter">{"".join(options)}</select><span id="count"></span></div></header>
<main>{"".join(sections)}</main>
<script>
const q=document.querySelector('#search'), c=document.querySelector('#chapter'), n=document.querySelector('#count');
function filter(){{let shown=0;const query=q.value.trim().toLowerCase(), chapter=c.value;
document.querySelectorAll('.record').forEach(r=>{{const ok=(!query||r.dataset.search.includes(query))&&(!chapter||r.dataset.chapter===chapter);r.classList.toggle('hidden',!ok);if(ok)shown++;}});
document.querySelectorAll('.chapter').forEach(s=>s.classList.toggle('hidden',!s.querySelector('.record:not(.hidden)')));n.textContent=shown+' records';}}
q.addEventListener('input',filter);c.addEventListener('change',filter);filter();
</script></body></html>"""


def _normalized_member_path(value: str) -> str:
    """Validate and normalize one portable archive member path."""
    if "\\" in value:
        raise ValueError(f"archive member uses a backslash: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"archive member is not a normalized relative path: {value!r}")
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError(f"archive member is not normalized: {value!r}")
    return normalized


def _inventory(root: Path) -> set[str]:
    """Return every regular file under a staging or published root."""
    return {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }


def _validate_inventory(root: Path, expected: set[str], phase: str) -> None:
    """Reject missing or unexpected files in one exact package tree."""
    normalized = {_normalized_member_path(path) for path in expected}
    actual = _inventory(root)
    missing = sorted(normalized - actual)
    unexpected = sorted(actual - normalized)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing expected files: {missing}")
        if unexpected:
            details.append(f"unexpected files: {unexpected}")
        raise ValueError(f"{phase} inventory failed: " + "; ".join(details))


def _member_entry(root: Path, relative: str) -> dict[str, object]:
    """Describe one expected archive member by normalized path, size, and hash."""
    relative = _normalized_member_path(relative)
    path = root / relative
    if not path.is_file():
        raise ValueError(f"missing expected package member: {relative}")
    return {
        "path": relative,
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def _write_deterministic_zip(
    output: Path,
    root: Path,
    members: list[dict[str, object]],
) -> None:
    """Write a fully specified stored-entry ZIP without library heuristics."""
    central: list[bytes] = []
    offset = 0
    with output.open("wb") as archive:
        for member in members:
            relative = _normalized_member_path(str(member["path"]))
            name = relative.encode("utf-8")
            payload = (root / relative).read_bytes()
            if (
                len(payload) != member["size"]
                or _sha256_bytes(payload) != member["sha256"]
            ):
                raise ValueError(
                    f"package member changed after manifesting: {relative}"
                )
            crc = binascii.crc32(payload) & 0xFFFFFFFF
            local = struct.pack(
                "<IHHHHHIIIHH",
                0x04034B50,
                ZIP_VERSION_NEEDED,
                0,
                0,
                ZIP_DOS_TIME,
                ZIP_DOS_DATE,
                crc,
                len(payload),
                len(payload),
                len(name),
                0,
            )
            archive.write(local)
            archive.write(name)
            archive.write(payload)
            central.append(
                struct.pack(
                    "<IHHHHHHIIIHHHHHII",
                    0x02014B50,
                    ZIP_VERSION_MADE_BY,
                    ZIP_VERSION_NEEDED,
                    0,
                    0,
                    ZIP_DOS_TIME,
                    ZIP_DOS_DATE,
                    crc,
                    len(payload),
                    len(payload),
                    len(name),
                    0,
                    0,
                    0,
                    0,
                    ZIP_EXTERNAL_FILE_ATTR,
                    offset,
                )
                + name
            )
            offset += len(local) + len(name) + len(payload)
        central_offset = offset
        for entry in central:
            archive.write(entry)
            offset += len(entry)
        central_size = offset - central_offset
        archive.write(
            struct.pack(
                "<IHHHHIIH",
                0x06054B50,
                0,
                0,
                len(central),
                len(central),
                central_size,
                central_offset,
                0,
            )
        )


def _write_package_manifest(
    staging: Path,
    members: list[dict[str, object]],
    *,
    chapter_count: int,
    record_count: int,
) -> dict[str, object]:
    """Write the external exact-inventory manifest after the archive exists."""
    archive = staging / ZIP_NAME
    payload: dict[str, object] = {
        "schema_version": 1,
        "package": ZIP_NAME,
        "archive": {
            "size": archive.stat().st_size,
            "sha256": sha256(archive),
            "format": "ZIP with stored entries",
        },
        "member_count": len(members),
        "members": members,
        "coverage": {
            "chapter_count": chapter_count,
            "record_count": record_count,
        },
        "determinism": {
            "guarantee": (
                "Byte-identical archive for identical input bytes and identical "
                "exporter source under the same CPython major/minor runtime."
            ),
            "text": "UTF-8 with LF newlines",
            "member_order": "lexicographic normalized POSIX paths",
            "png": (
                "1-bit grayscale, filter 0, no ancillary metadata, specified "
                "stored-DEFLATE zlib stream and in-module Adler-32"
            ),
            "zip": (
                "stored entries, fixed DOS timestamp 1980-01-01 00:00:00, "
                "fixed Unix 0644 permissions, no extras or comment"
            ),
            "limits": (
                "The guarantee covers archive bytes generated by this exporter. "
                "Cross-Python-version identity is not promised because CPython's "
                "standard-library JSON and HTML serialization are not frozen by "
                "the project. Filesystem directory metadata and third-party "
                "rewrites are outside the guarantee."
            ),
        },
        "generator": {
            "path": "work/clean_rebuild/export_bilingual_comparison.py",
            "sha256": sha256(Path(__file__).resolve()),
            "runtime": {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
                "cache_tag": sys.implementation.cache_tag,
            },
            "output_affecting_third_party_dependencies": [],
        },
    }
    _write_text_lf(
        staging / PACKAGE_MANIFEST_NAME,
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
    )
    return payload


def validate_comparison_package(output_root: Path) -> dict[str, object]:
    """Validate exact disk and ZIP inventories against the package manifest."""
    failures: list[str] = []
    manifest_path = output_root / PACKAGE_MANIFEST_NAME
    if not manifest_path.is_file():
        return {
            "status": "FAIL",
            "failure_count": 1,
            "failures": [f"missing package manifest: {manifest_path}"],
            "member_count": 0,
        }
    try:
        manifest = load_json_object(manifest_path)
    except (OSError, json.JSONDecodeError) as error:
        return {
            "status": "FAIL",
            "failure_count": 1,
            "failures": [f"cannot read package manifest: {error}"],
            "member_count": 0,
        }
    raw_members = manifest.get("members")
    if not isinstance(raw_members, list):
        failures.append("package manifest has no members list")
        raw_members = []
    members: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_members):
        if not isinstance(item, dict):
            failures.append(f"manifest member {index} is not an object")
            continue
        try:
            relative = _normalized_member_path(str(item.get("path", "")))
        except ValueError as error:
            failures.append(str(error))
            continue
        if relative in seen:
            failures.append(f"manifest repeats member: {relative}")
            continue
        seen.add(relative)
        if not isinstance(item.get("size"), int) or item["size"] < 0:
            failures.append(f"manifest member has invalid size: {relative}")
            continue
        digest = item.get("sha256")
        if not isinstance(digest, str) or not re_full_sha256(digest):
            failures.append(f"manifest member has invalid SHA-256: {relative}")
            continue
        members.append(
            {"path": relative, "size": item["size"], "sha256": digest.upper()}
        )
    paths = [str(item["path"]) for item in members]
    if paths != sorted(paths):
        failures.append("manifest members are not in lexicographic path order")
    if manifest.get("member_count") != len(members):
        failures.append("package manifest member count is stale")

    archive_spec = manifest.get("archive")
    package_name = manifest.get("package")
    if package_name != ZIP_NAME:
        failures.append(f"package manifest names unexpected archive: {package_name!r}")
    archive_path = output_root / ZIP_NAME
    expected_disk = set(paths) | {PACKAGE_MANIFEST_NAME, archive_path.name}
    actual_disk = _inventory(output_root) if output_root.is_dir() else set()
    missing_disk = sorted(expected_disk - actual_disk)
    unexpected_disk = sorted(actual_disk - expected_disk)
    if missing_disk:
        failures.append(f"published package is missing files: {missing_disk}")
    if unexpected_disk:
        failures.append(f"published package has unexpected files: {unexpected_disk}")

    for member in members:
        path = output_root / str(member["path"])
        if not path.is_file():
            continue
        if path.stat().st_size != member["size"]:
            failures.append(f"disk member size mismatch: {member['path']}")
        elif sha256(path) != member["sha256"]:
            failures.append(f"disk member hash mismatch: {member['path']}")

    if not isinstance(archive_spec, dict):
        failures.append("package manifest has no archive object")
    elif archive_path.is_file():
        if archive_path.stat().st_size != archive_spec.get("size"):
            failures.append("archive size differs from the package manifest")
        if sha256(archive_path) != str(archive_spec.get("sha256", "")).upper():
            failures.append("archive SHA-256 differs from the package manifest")
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)):
                    failures.append("archive contains duplicate member names")
                if names != paths:
                    failures.append(
                        "archive member inventory/order differs from manifest"
                    )
                entries = {str(item["path"]): item for item in members}
                for info in infos:
                    entry = entries.get(info.filename)
                    if entry is None:
                        continue
                    if info.compress_type != zipfile.ZIP_STORED:
                        failures.append(
                            f"archive member is compressed: {info.filename}"
                        )
                    if info.date_time != (1980, 1, 1, 0, 0, 0):
                        failures.append(
                            f"archive timestamp is not fixed: {info.filename}"
                        )
                    if (
                        info.create_system != 3
                        or info.external_attr != ZIP_EXTERNAL_FILE_ATTR
                    ):
                        failures.append(
                            f"archive permissions/platform metadata differ: {info.filename}"
                        )
                    if info.extra or info.comment:
                        failures.append(
                            f"archive member has extra metadata: {info.filename}"
                        )
                    payload = archive.read(info)
                    if (
                        len(payload) != entry["size"]
                        or _sha256_bytes(payload) != entry["sha256"]
                    ):
                        failures.append(f"archive member bytes differ: {info.filename}")
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            failures.append(f"archive cannot be validated: {error}")

    comparison_path = output_root / JSON_NAME
    if comparison_path.is_file():
        try:
            comparison = load_json_object(comparison_path)
            image_paths = [
                record["japanese_image"]
                for chapter in comparison["chapters"]
                for record in chapter["records"]
            ]
            expected_images = sorted(
                path for path in paths if path.startswith("images/")
            )
            if len(image_paths) != len(set(image_paths)):
                failures.append("comparison JSON repeats Japanese image references")
            if sorted(image_paths) != expected_images:
                failures.append(
                    "comparison JSON image references differ from exact image inventory"
                )
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            failures.append(f"comparison JSON cannot be cross-checked: {error}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
        "member_count": len(members),
        "archive_sha256": sha256(archive_path) if archive_path.is_file() else None,
        "unexpected_file_count": len(unexpected_disk),
        "missing_file_count": len(missing_disk),
    }


def re_full_sha256(value: str) -> bool:
    """Return whether a string is exactly one hexadecimal SHA-256 digest."""
    return len(value) == 64 and all(
        character in "0123456789abcdefABCDEF" for character in value
    )


def _publish_staging(staging: Path, output_root: Path) -> None:
    """Atomically publish a validated staging tree and remove the prior output."""
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(
            f"comparison output exists but is not a directory: {output_root}"
        )
    previous: Path | None = None
    if output_root.exists():
        previous = Path(
            tempfile.mkdtemp(
                prefix=f".{output_root.name}.previous-",
                dir=output_root.parent,
            )
        )
        previous.rmdir()
        os.replace(output_root, previous)
    try:
        os.replace(staging, output_root)
    except BaseException:
        if previous is not None and previous.exists() and not output_root.exists():
            os.replace(previous, output_root)
        raise
    if previous is not None:
        shutil.rmtree(previous)


def _export_to_staging(retail_root: Path, staging: Path) -> dict[str, object]:
    """Generate and validate one complete comparison package in fresh staging."""
    fixed_path = retail_root / "retail_files" / "FIX_CODE.FNT"
    if (
        fixed_path.stat().st_size != FIXED_FONT_SIZE
        or sha256(fixed_path) != FIXED_FONT_SHA256
    ):
        raise ValueError("retail fixed font failed its frozen size/hash guard")
    fixed_data = fixed_path.read_bytes()
    fixed_glyphs = tuple(
        fixed_data[offset : offset + GLYPH_BYTES]
        for offset in range(0, len(fixed_data), GLYPH_BYTES)
    )
    index = load_json_object(SOURCES / "index.json")
    chapters: list[dict[str, object]] = []
    expected_members = {"README.md", HTML_NAME, MARKDOWN_NAME, JSON_NAME}
    total = 0
    visible_glyphs = 0
    control_records = 0
    for item in index["chapters"]:
        name = item["chapter"]
        canonical = load_json_object(SOURCES / item["source"])
        mes_path = retail_root / "retail_unpacked" / name / f"{name}.MES"
        if (
            mes_path.stat().st_size != canonical["retail_mes"]["size"]
            or sha256(mes_path) != canonical["retail_mes"]["sha256"]
        ):
            raise ValueError(f"{name}: retail MES failed its canonical guard")
        mes = read_mes(mes_path)
        if (
            mes.record_count != canonical["record_count"]
            or len(canonical["records"]) != mes.record_count
        ):
            raise ValueError(f"{name}: Japanese/English record counts disagree")
        chapter_markdown_path = f"chapters/{name}.md"
        expected_members.add(chapter_markdown_path)
        records: list[dict[str, object]] = []
        for record_index, (raw, english_record) in enumerate(
            zip(mes.records, canonical["records"], strict=True)
        ):
            if english_record["index"] != record_index:
                raise ValueError(f"{name}: canonical indexes are not aligned")
            glyphs, controls, tokens = _record_glyphs(raw, fixed_glyphs, mes.glyphs)
            relative_image = Path("images") / name / f"{record_index:03d}.png"
            relative_image_string = relative_image.as_posix()
            expected_members.add(relative_image_string)
            width, height = _render_record(glyphs, staging / relative_image)
            record_id = f"{name}:{record_index:03d}"
            records.append(
                {
                    "id": record_id,
                    "index": record_index,
                    "japanese_representation": "original-retail-bitmap-glyphs",
                    "japanese_image": relative_image_string,
                    "japanese_visible_glyphs": len(glyphs),
                    "japanese_image_width": width,
                    "japanese_image_height": height,
                    "source_tokens": tokens,
                    "source_record_hex": raw.hex().upper(),
                    "controls": controls,
                    "english_policy": english_record["policy"],
                    "english": english_record["text"],
                }
            )
            total += 1
            visible_glyphs += len(glyphs)
            control_records += bool(controls)
        chapters.append(
            {
                "chapter": name,
                "record_count": mes.record_count,
                "retail_mes_sha256": sha256(mes_path),
                "records": records,
            }
        )
    if len(chapters) != EXPECTED_CHAPTERS or total != EXPECTED_RECORDS:
        raise ValueError("bilingual comparison coverage is incomplete")

    payload = {
        "schema_version": 1,
        "title": "Nostalgia 1907 Japanese / English Record Comparison",
        "alignment": "Exact MES record index alignment",
        "japanese_source": (
            "Lossless visual rendering of original retail bitmap glyphs. No OCR or "
            "invented Unicode transcription is used."
        ),
        "english_source": "Canonical English translation used by the clean rebuild.",
        "chapter_count": len(chapters),
        "record_count": total,
        "japanese_visible_glyphs": visible_glyphs,
        "records_with_ee_control": control_records,
        "chapters": chapters,
    }
    json_path = staging / JSON_NAME
    html_path = staging / HTML_NAME
    markdown_path = staging / MARKDOWN_NAME
    _write_text_lf(json_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    _write_text_lf(html_path, _comparison_html(chapters))
    markdown_parts = [
        "# Nostalgia 1907 Japanese / English Record Comparison\n\n"
        "Japanese entries are exact visual renderings of the original retail glyphs, "
        "not OCR. English entries are canonical rebuild text. Cite edits by `CHAPTER:NNN`.\n"
    ]
    for chapter in chapters:
        chapter_markdown = _chapter_markdown(chapter, image_prefix="../")
        _write_text_lf(
            staging / "chapters" / f"{chapter['chapter']}.md", chapter_markdown
        )
        markdown_parts.append(_chapter_markdown(chapter))
    _write_text_lf(markdown_path, "\n".join(markdown_parts))
    readme = (
        "# Bilingual comparison package\n\n"
        "Open `Nostalgia1907_Japanese_English_Comparison.html` for the searchable, "
        "side-by-side view. Japanese is rendered directly from the original retail "
        "font/MES bitmap data. It is intentionally not OCR text. The JSON contains "
        "record IDs, original source bytes/tokens, image paths, and exact English text.\n\n"
        "The sibling `.manifest.json` file records the exact archive inventory and "
        "hashes. Every export is a full clean regeneration; incremental reuse is not "
        "supported.\n"
    )
    _write_text_lf(staging / "README.md", readme)

    reconstructed = load_json_object(json_path)
    if reconstructed["record_count"] != total:
        raise AssertionError("comparison JSON did not round-trip")
    for chapter in reconstructed["chapters"]:
        if len(chapter["records"]) != chapter["record_count"]:
            raise AssertionError(f"{chapter['chapter']}: comparison JSON lost records")
        for record in chapter["records"]:
            if not (staging / record["japanese_image"]).is_file():
                raise AssertionError(f"missing Japanese image for {record['id']}")

    _validate_inventory(staging, expected_members, "pre-archive staging")
    members = [_member_entry(staging, path) for path in sorted(expected_members)]
    zip_path = staging / ZIP_NAME
    _write_deterministic_zip(zip_path, staging, members)
    manifest = _write_package_manifest(
        staging,
        members,
        chapter_count=len(chapters),
        record_count=total,
    )
    _validate_inventory(
        staging,
        expected_members | {ZIP_NAME, PACKAGE_MANIFEST_NAME},
        "complete staging",
    )
    validation = validate_comparison_package(staging)
    if validation["status"] != "PASS":
        raise ValueError(
            "generated comparison package failed self-validation: "
            + "; ".join(validation["failures"])
        )
    return {
        "status": "PASS",
        "chapter_count": len(chapters),
        "record_count": total,
        "japanese_visible_glyphs": visible_glyphs,
        "image_count": sum(path.startswith("images/") for path in expected_members),
        "member_count": len(members),
        "unexpected_file_count": 0,
        "html_sha256": sha256(html_path),
        "json_sha256": sha256(json_path),
        "zip_sha256": manifest["archive"]["sha256"],
        "package_manifest_sha256": sha256(staging / PACKAGE_MANIFEST_NAME),
        "determinism_guarantee": manifest["determinism"]["guarantee"],
    }


def export_comparison(retail_root: Path, output_root: Path) -> dict[str, object]:
    """Export all 2,905 record pairs through clean run-specific staging.

    Args:
        retail_root: Prepared hash-locked Japanese retail reference.
        output_root: Final comparison-package destination. A prior directory is
            replaced only after the new package passes exact-inventory checks.

    Returns:
        Coverage counts, hashes, exact member count, and determinism scope.

    Raises:
        ValueError: If inputs, staging inventory, package bytes, or publication
            violate the validated contract.
        AssertionError: If generated JSON or image references fail self-checks.

    Side Effects:
        Writes a fresh run-specific staging directory, generates the complete
        package there, atomically publishes it, and removes the prior output.
        No files from prior outputs or abandoned staging trees are reused.
    """
    output_root = output_root.expanduser().resolve()
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(
            f"comparison output exists but is not a directory: {output_root}"
        )
    previous_files = sorted(_inventory(output_root)) if output_root.is_dir() else []
    abandoned_staging = sorted(
        path
        for path in output_root.parent.glob(f".{output_root.name}.staging-*")
        if path.is_dir()
    )
    abandoned_files = sorted(
        f"{path.name}/{relative}"
        for path in abandoned_staging
        for relative in _inventory(path)
    )
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.staging-",
            dir=output_root.parent,
        )
    )
    try:
        result = _export_to_staging(retail_root.resolve(), staging)
        current_files = _inventory(staging)
        _publish_staging(staging, output_root)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    result.update(
        {
            "output_root": str(output_root),
            "previous_output_file_count": len(previous_files),
            "previous_output_reused_file_count": 0,
            "previous_output_unexpected_files_discarded": sorted(
                set(previous_files) - current_files
            ),
            "abandoned_staging_directories_ignored": [
                path.name for path in abandoned_staging
            ],
            "abandoned_staging_files_ignored": abandoned_files,
        }
    )
    return result


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate an existing output root instead of regenerating it",
    )
    args = parser.parse_args()
    if args.validate_only:
        payload = validate_comparison_package(args.output_root)
    else:
        payload = export_comparison(args.retail_root, args.output_root)
    print(json.dumps(payload, indent=2))
    if payload.get("status") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Export record-aligned retail Japanese glyphs and canonical English text.

The comparison package is a deterministic human-review artifact. Japanese is
rendered directly from the hash-locked retail fixed and dynamic bitmap glyphs;
OCR and invented Unicode transcription are deliberately excluded. Canonical
English, policy, source tokens, controls, and bytes remain aligned by stable
zero-based ``CHAPTER:NNN`` record IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from mes_format import read_mes


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


def sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def _glyph_matrix(stored: bytes) -> list[list[int]]:
    """Decode and rotate one native stored glyph into upright screen order."""
    if len(stored) != GLYPH_BYTES:
        raise ValueError(f"glyph has {len(stored)} bytes, expected {GLYPH_BYTES}")
    bits = [
        (byte >> shift) & 1
        for byte in stored
        for shift in range(7, -1, -1)
    ]
    source = [
        bits[row * GLYPH_WIDTH : (row + 1) * GLYPH_WIDTH]
        for row in range(GLYPH_HEIGHT)
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


def _render_record(glyphs: list[bytes], output: Path, *, columns: int = 48) -> tuple[int, int]:
    """Render one record's original Japanese glyphs without OCR or resampling."""
    scale = 2
    padding = 4
    cell = GLYPH_WIDTH * scale
    if glyphs:
        used_columns = min(columns, len(glyphs))
        rows = (len(glyphs) + columns - 1) // columns
        width = padding * 2 + used_columns * cell
        height = padding * 2 + rows * cell
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        for index, glyph in enumerate(glyphs):
            row, column = divmod(index, columns)
            x_base = padding + column * cell
            y_base = padding + row * cell
            matrix = _glyph_matrix(glyph)
            for y, pixels in enumerate(matrix):
                for x, bit in enumerate(pixels):
                    if bit:
                        draw.rectangle(
                            (
                                x_base + x * scale,
                                y_base + y * scale,
                                x_base + x * scale + scale - 1,
                                y_base + y * scale + scale - 1,
                            ),
                            fill="black",
                        )
    else:
        width, height = 240, 32
        image = Image.new("RGB", (width, height), "white")
        ImageDraw.Draw(image).text((6, 9), "[control-only / blank]", fill=(90, 90, 90))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)
    return width, height


def _chapter_markdown(
    chapter: dict[str, object], *, image_prefix: str = ""
) -> str:
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
        options.append(f'<option value="{html.escape(name)}">{html.escape(name)}</option>')
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
                f'''<article class="record" data-chapter="{html.escape(name)}" data-search="{search}">
<div class="record-id"><a href="#{html.escape(record['id'])}" id="{html.escape(record['id'])}">{html.escape(record['id'])}</a></div>
<div class="jp"><div class="label">Japanese — original retail bitmap glyphs</div>
<img src="{html.escape(record['japanese_image'])}" alt="Original Japanese glyphs for {html.escape(record['id'])}" loading="lazy"></div>
<div class="en"><div class="label">English — canonical translation</div><pre>{english_display}</pre>{controls}</div>
</article>'''
            )
        sections.append(
            f'<section class="chapter" data-chapter-section="{html.escape(name)}"><h2>{html.escape(name)}</h2>{"".join(records)}</section>'
        )
    return f'''<!doctype html>
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
</script></body></html>'''


def export_comparison(retail_root: Path, output_root: Path) -> dict[str, object]:
    """Export and verify all 2,905 retail/canonical record pairs.

    Args:
        retail_root: Prepared hash-locked Japanese retail reference.
        output_root: Disposable comparison-package destination.

    Returns:
        Coverage counts and hashes for the canonical HTML, JSON, and ZIP.

    Raises:
        ValueError: If fonts, MES guards, record counts, indexes, or complete
            project coverage differ from the validated contract.
        AssertionError: If generated JSON or image references fail self-checks.

    Side Effects:
        Writes 2,905 PNGs, per-chapter and combined Markdown, searchable HTML,
        canonical JSON, package README, and a deterministic ZIP. ZIP timestamps,
        permissions, ordering, and compression settings are fixed.
    """
    fixed_path = retail_root / "retail_files" / "FIX_CODE.FNT"
    if fixed_path.stat().st_size != FIXED_FONT_SIZE or sha256(fixed_path) != FIXED_FONT_SHA256:
        raise ValueError("retail fixed font failed its frozen size/hash guard")
    fixed_data = fixed_path.read_bytes()
    fixed_glyphs = tuple(
        fixed_data[offset : offset + GLYPH_BYTES]
        for offset in range(0, len(fixed_data), GLYPH_BYTES)
    )
    index = json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))
    output_root.mkdir(parents=True, exist_ok=True)
    chapters: list[dict[str, object]] = []
    total = 0
    visible_glyphs = 0
    control_records = 0
    for item in index["chapters"]:
        name = item["chapter"]
        canonical = json.loads((SOURCES / item["source"]).read_text(encoding="utf-8"))
        mes_path = retail_root / "retail_unpacked" / name / f"{name}.MES"
        if mes_path.stat().st_size != canonical["retail_mes"]["size"] or sha256(mes_path) != canonical["retail_mes"]["sha256"]:
            raise ValueError(f"{name}: retail MES failed its canonical guard")
        mes = read_mes(mes_path)
        if mes.record_count != canonical["record_count"] or len(canonical["records"]) != mes.record_count:
            raise ValueError(f"{name}: Japanese/English record counts disagree")
        records: list[dict[str, object]] = []
        for record_index, (raw, english_record) in enumerate(
            zip(mes.records, canonical["records"], strict=True)
        ):
            if english_record["index"] != record_index:
                raise ValueError(f"{name}: canonical indexes are not aligned")
            glyphs, controls, tokens = _record_glyphs(raw, fixed_glyphs, mes.glyphs)
            relative_image = Path("images") / name / f"{record_index:03d}.png"
            width, height = _render_record(glyphs, output_root / relative_image)
            record_id = f"{name}:{record_index:03d}"
            records.append(
                {
                    "id": record_id,
                    "index": record_index,
                    "japanese_representation": "original-retail-bitmap-glyphs",
                    "japanese_image": relative_image.as_posix(),
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
    if len(chapters) != 19 or total != 2905:
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
    json_path = output_root / "Nostalgia1907_Japanese_English_Comparison.json"
    html_path = output_root / "Nostalgia1907_Japanese_English_Comparison.html"
    markdown_path = output_root / "Nostalgia1907_Japanese_English_Comparison.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    html_path.write_text(_comparison_html(chapters), encoding="utf-8")
    markdown_parts = [
        "# Nostalgia 1907 Japanese / English Record Comparison\n\n"
        "Japanese entries are exact visual renderings of the original retail glyphs, "
        "not OCR. English entries are canonical rebuild text. Cite edits by `CHAPTER:NNN`.\n"
    ]
    chapter_root = output_root / "chapters"
    chapter_root.mkdir(parents=True, exist_ok=True)
    for chapter in chapters:
        chapter_markdown = _chapter_markdown(chapter, image_prefix="../")
        (chapter_root / f"{chapter['chapter']}.md").write_text(
            chapter_markdown, encoding="utf-8"
        )
        markdown_parts.append(_chapter_markdown(chapter))
    markdown_path.write_text("\n".join(markdown_parts), encoding="utf-8")
    readme = (
        "# Bilingual comparison package\n\n"
        "Open `Nostalgia1907_Japanese_English_Comparison.html` for the searchable, "
        "side-by-side view. Japanese is rendered directly from the original retail "
        "font/MES bitmap data. It is intentionally not OCR text. The JSON contains "
        "record IDs, original source bytes/tokens, image paths, and exact English text.\n"
    )
    (output_root / "README.md").write_text(readme, encoding="utf-8")

    reconstructed = json.loads(json_path.read_text(encoding="utf-8"))
    if reconstructed["record_count"] != total:
        raise AssertionError("comparison JSON did not round-trip")
    for chapter in reconstructed["chapters"]:
        if len(chapter["records"]) != chapter["record_count"]:
            raise AssertionError(f"{chapter['chapter']}: comparison JSON lost records")
        for record in chapter["records"]:
            if not (output_root / record["japanese_image"]).is_file():
                raise AssertionError(f"missing Japanese image for {record['id']}")

    package_files = [
        output_root / "README.md",
        html_path,
        markdown_path,
        json_path,
        *sorted(chapter_root.glob("*.md")),
        *sorted((output_root / "images").glob("*/*.png")),
    ]
    zip_path = output_root / "Nostalgia1907_Japanese_English_Comparison.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in package_files:
            info = zipfile.ZipInfo(
                path.relative_to(output_root).as_posix(),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return {
        "status": "PASS",
        "chapter_count": len(chapters),
        "record_count": total,
        "japanese_visible_glyphs": visible_glyphs,
        "image_count": len(list((output_root / "images").glob("*/*.png"))),
        "html_sha256": sha256(html_path),
        "json_sha256": sha256(json_path),
        "zip_sha256": sha256(zip_path),
        "output_root": str(output_root),
    }


def main() -> None:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-root", type=Path, default=DEFAULT_RETAIL_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export_comparison(args.retail_root, args.output_root), indent=2))


if __name__ == "__main__":
    main()

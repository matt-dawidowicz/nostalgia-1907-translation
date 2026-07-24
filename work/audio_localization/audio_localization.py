#!/usr/bin/env python3
"""Extract, map, transcribe, dub, and validate Nostalgia 1907 Track 1 audio.

This tool is intentionally separate from the clean rebuild pipeline.  It reads
the hash-locked Japanese retail ISO and canonical translation sources, and
writes only to a caller-selected review directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ISOLATED_RUNTIME = Path(__file__).resolve().parent / ".runtime"
if ISOLATED_RUNTIME.is_dir():
    sys.path.insert(0, str(ISOLATED_RUNTIME))
ISOLATED_TTS_RUNTIME = Path(__file__).resolve().parent / ".kokoro_runtime"
ISOLATED_CUDA = Path(__file__).resolve().parent / ".cuda"
_DLL_DIRECTORY_HANDLES: list[Any] = []
if os.name == "nt" and ISOLATED_CUDA.is_dir():
    _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(ISOLATED_CUDA)))
    os.environ["PATH"] = f"{ISOLATED_CUDA}{os.pathsep}{os.environ.get('PATH', '')}"

SCHEMA_VERSION = 1
RETAIL_ISO_SHA256 = "7944AF20FD802A43BEFBFA97734993EB63A3803F76D4AFBCEF315E41D4459ECC"
RF5C164_CLOCK_HZ = 12_500_000
RF5C164_CLOCK_DIVISOR = 384
RF5C164_FD = 0x0400
RF5C164_UNITY_FD = 0x0800
SAMPLE_RATE_NUMERATOR = RF5C164_CLOCK_HZ * RF5C164_FD
SAMPLE_RATE_DENOMINATOR = RF5C164_CLOCK_DIVISOR * RF5C164_UNITY_FD
WAV_SAMPLE_RATE = round(SAMPLE_RATE_NUMERATOR / SAMPLE_RATE_DENOMINATOR)
PCM_COMMAND = re.compile(rb"r([A-Za-z0-9_]+[.]pcm)\x00", re.IGNORECASE)
PCM_NAMES_EXPECTED = {f"{index:04d}.PCM" for index in range(1824)} | {
    "0014A.PCM",
    "0014B.PCM",
    "0671A.PCM",
    "BAKUHATU.PCM",
}


class AudioLocalizationError(RuntimeError):
    """Raised when an input or generated artifact is not safe to use."""


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def clean_text(text: str | None) -> str:
    """Convert render-ready text into a natural single-line speech prompt."""
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"[\x00-\x1f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_clean_rebuild(clean_rebuild: Path) -> tuple[Any, Any]:
    """Load only the validated ISO/MES helpers from the active clean rebuild."""
    resolved = clean_rebuild.resolve()
    if not (resolved / "iso9660.py").is_file() or not (resolved / "mes_format.py").is_file():
        raise AudioLocalizationError(
            f"{resolved} is not a Nostalgia 1907 clean_rebuild directory"
        )
    sys.path.insert(0, str(resolved))
    try:
        import iso9660  # type: ignore
        import mes_format  # type: ignore
    finally:
        sys.path.pop(0)
    return iso9660, mes_format


def load_sources(sources_dir: Path) -> list[dict[str, Any]]:
    index = json.loads((sources_dir / "index.json").read_text(encoding="utf-8"))
    chapters: list[dict[str, Any]] = []
    for item in index["chapters"]:
        source_path = sources_dir / item["source"]
        source = json.loads(source_path.read_text(encoding="utf-8"))
        if source["chapter"] != item["chapter"]:
            raise AudioLocalizationError(f"chapter mismatch in {source_path}")
        if len(source["records"]) != source["record_count"]:
            raise AudioLocalizationError(f"record count mismatch in {source_path}")
        chapters.append(source)
    return chapters


def extract_entry(iso_stream: Any, entry: Any, sector_size: int) -> bytes:
    iso_stream.seek(entry.extent * sector_size)
    data = iso_stream.read(entry.size)
    if len(data) != entry.size:
        raise AudioLocalizationError(f"short ISO read for {entry.path}")
    return data


def decode_sign_magnitude(raw: bytes) -> bytes:
    """Decode RF5C164 8-bit sign-magnitude samples to little-endian PCM16."""
    output = bytearray(len(raw) * 2)
    cursor = 0
    for value in raw:
        magnitude = value & 0x7F
        sample = -magnitude if value & 0x80 else magnitude
        struct.pack_into("<h", output, cursor, sample << 8)
        cursor += 2
    return bytes(output)


def encode_sign_magnitude(samples: Iterable[int]) -> bytes:
    """Encode signed PCM values in the RF5C164's 8-bit sign-magnitude format."""
    output = bytearray()
    for sample in samples:
        scaled = max(-127, min(127, round(int(sample) / 256)))
        output.append((0x80 | -scaled) if scaled < 0 else scaled)
    return bytes(output)


def write_wav(path: Path, pcm16: bytes, sample_rate: int = WAV_SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm16)


def read_wav(path: Path) -> tuple[int, int, int, bytes]:
    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        width = stream.getsampwidth()
        rate = stream.getframerate()
        data = stream.readframes(stream.getnframes())
    return channels, width, rate, data


def zero_run(raw: bytes, *, from_end: bool = False) -> int:
    values = reversed(raw) if from_end else raw
    count = 0
    for value in values:
        if value != 0:
            break
        count += 1
    return count


def valid_dialogue_command(
    scn: bytes, offset: int, record_count: int
) -> dict[str, Any] | None:
    if offset + 5 > len(scn) or scn[offset] != 0x21:
        return None
    first_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
    second_id = int.from_bytes(scn[offset + 3 : offset + 5], "big")
    if 1 <= second_id <= record_count:
        return {
            "offset": offset,
            "command": "0x21_dialogue",
            "record_index": second_id - 1,
            "speaker_index": first_id - 1 if 1 <= first_id <= record_count else None,
        }
    if second_id == 0 and 1 <= first_id <= record_count:
        return {
            "offset": offset,
            "command": "0x21_continuation",
            "record_index": first_id - 1,
            "speaker_index": None,
        }
    return None


def valid_window_command(
    scn: bytes,
    offset: int,
    record_count: int,
    window_subtypes: set[int],
) -> dict[str, Any] | None:
    if (
        offset + 8 > len(scn)
        or scn[offset] != 0x24
        or scn[offset + 5] not in window_subtypes
    ):
        return None
    text_id = int.from_bytes(scn[offset + 6 : offset + 8], "big")
    if not 1 <= text_id <= record_count:
        return None
    return {
        "offset": offset,
        "command": "0x24_window",
        "record_index": text_id - 1,
        "speaker_index": None,
    }


def valid_inline_command(
    scn: bytes, offset: int, record_count: int
) -> dict[str, Any] | None:
    """Return a valid speakerless 0x20 MES display command.

    PART4C's closing exchange uses these commands and starts each voice asset
    after the associated record rather than immediately before a 0x21 command.
    """
    if offset + 3 > len(scn) or scn[offset] != 0x20:
        return None
    text_id = int.from_bytes(scn[offset + 1 : offset + 3], "big")
    if not 1 <= text_id <= record_count:
        return None
    return {
        "offset": offset,
        "command": "0x20_inline",
        "record_index": text_id - 1,
        "speaker_index": None,
    }


def text_commands(
    scn: bytes, record_count: int, profile: dict[str, Any] | None
) -> list[dict[str, Any]]:
    profile = profile or {}
    window_subtypes = set(profile.get("scn_window_text_subtypes", [0x27]))
    commands: dict[tuple[int, str], dict[str, Any]] = {}
    for offset in range(len(scn)):
        dialogue = valid_dialogue_command(scn, offset, record_count)
        if dialogue:
            commands[(offset, dialogue["command"])] = dialogue
        window = valid_window_command(scn, offset, record_count, window_subtypes)
        if window:
            commands[(offset, window["command"])] = window
        inline = valid_inline_command(scn, offset, record_count)
        if inline:
            commands[(offset, inline["command"])] = inline
    return sorted(commands.values(), key=lambda item: (item["offset"], item["command"]))


def audio_commands(scn: bytes, valid_names: set[str]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for match in PCM_COMMAND.finditer(scn):
        name = match.group(1).decode("ascii").upper()
        if name not in valid_names:
            continue
        commands.append(
            {
                "offset": match.start(),
                "end_offset": match.end(),
                "pcm": name,
            }
        )
    return commands


def record_metadata(
    chapter: str,
    records: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    relation: str,
) -> dict[str, Any]:
    primary = commands[0]
    index = primary["record_index"]
    speaker_index = primary["speaker_index"]
    speaker = records[speaker_index] if speaker_index is not None else None
    line_records = [
        {
            "record_index": command["record_index"],
            "record_id": f"{chapter}:{command['record_index']:03d}",
            "canonical_english": clean_text(records[command["record_index"]].get("text")),
            "record_policy": records[command["record_index"]].get("policy"),
            "scn_text_offset": command["offset"],
            "text_command": command["command"],
        }
        for command in commands
    ]
    canonical_lines = [
        item["canonical_english"]
        for item in line_records
        if item["canonical_english"]
    ]
    return {
        "chapter": chapter,
        "scn_audio_offset": primary["audio_offset"],
        "scn_text_offset": primary["offset"],
        "mapping_relation": relation,
        "text_command": primary["command"],
        "record_index": index,
        "record_id": f"{chapter}:{index:03d}",
        "record_ids": [item["record_id"] for item in line_records],
        "records": line_records,
        "canonical_english_lines": canonical_lines,
        "canonical_english": clean_text(" ".join(canonical_lines)),
        "record_policy": line_records[0]["record_policy"],
        "speaker_index": speaker_index,
        "speaker_record_id": (
            f"{chapter}:{speaker_index:03d}" if speaker_index is not None else None
        ),
        "speaker": clean_text(speaker.get("text")) if speaker else None,
    }


def map_chapter_audio(
    chapter_source: dict[str, Any],
    scn: bytes,
    valid_names: set[str],
) -> list[dict[str, Any]]:
    """Map each SCN audio occurrence to the nearest structural text command."""
    chapter = chapter_source["chapter"]
    records = chapter_source["records"]
    audios = audio_commands(scn, valid_names)
    texts = text_commands(scn, len(records), chapter_source.get("profile", {}))
    mappings: list[dict[str, Any]] = []
    for position, audio in enumerate(audios):
        if audio["pcm"] == "BAKUHATU.PCM":
            mappings.append(
                {
                    "chapter": chapter,
                    "scn_audio_offset": audio["offset"],
                    "pcm": audio["pcm"],
                    "mapping_relation": "sfx",
                }
            )
            continue
        previous_end = audios[position - 1]["end_offset"] if position else 0
        next_start = audios[position + 1]["offset"] if position + 1 < len(audios) else len(scn)
        following = [
            item for item in texts if audio["end_offset"] <= item["offset"] < next_start
        ]
        preceding = [
            item for item in texts if previous_end <= item["offset"] < audio["offset"]
        ]
        selected: list[dict[str, Any]] = []
        relation = "unmapped"
        preceding_inline: list[dict[str, Any]] = []
        if preceding and preceding[-1]["command"] == "0x20_inline":
            for item in reversed(preceding):
                if item["command"] != "0x20_inline":
                    break
                preceding_inline.append(item)
            preceding_inline.reverse()
        following_inline = [
            item for item in following if item["command"] == "0x20_inline"
        ]
        if preceding_inline:
            # Speakerless ending exchanges queue one or more 0x20 records and
            # then start the voice asset.  If this is the last asset in the
            # scene, the same voice can continue over later 0x20 records.
            selected = preceding_inline
            if position + 1 == len(audios):
                selected = [*selected, *following_inline]
            relation = "inline_span"
        elif following:
            primary = min(following, key=lambda item: item["offset"])
            selected = [primary]
            if primary["command"].startswith("0x21_"):
                # A voice asset can cover one dialogue command followed by
                # several 0x21 continuation records before the next asset.
                for item in following:
                    if item["offset"] <= primary["offset"]:
                        continue
                    if item["command"] == "0x21_continuation":
                        selected.append(item)
                    elif item["command"] == "0x21_dialogue":
                        break
                    elif item["command"] == "0x24_window":
                        break
                # Some announcement clips begin after the initial 0x21 and
                # continue over one or more following continuation commands.
                previous = preceding[-1] if preceding else None
                if (
                    primary["command"] == "0x21_continuation"
                    and previous is not None
                    and previous["command"].startswith("0x21_")
                    and audio["offset"] - (previous["offset"] + 5) <= 2
                ):
                    selected.insert(0, previous)
            relation = "following"
        elif preceding:
            selected = [max(preceding, key=lambda item: item["offset"])]
            relation = "preceding"
        occurrence: dict[str, Any] = {
            "chapter": chapter,
            "scn_audio_offset": audio["offset"],
            "pcm": audio["pcm"],
            "mapping_relation": relation,
        }
        if selected:
            selected = [
                {**command, "audio_offset": audio["offset"]} for command in selected
            ]
            occurrence = {
                "pcm": audio["pcm"],
                **record_metadata(chapter, records, selected, relation),
            }
        mappings.append(occurrence)
    return mappings


def build_manifest(
    clean_rebuild: Path,
    output_dir: Path,
    *,
    write_audio: bool,
) -> dict[str, Any]:
    iso9660, _mes_format = load_clean_rebuild(clean_rebuild)
    iso_path = clean_rebuild / "retail_reference" / "retail.iso"
    sources_dir = clean_rebuild / "sources"
    unpacked_dir = clean_rebuild / "retail_reference" / "retail_unpacked"
    if sha256_path(iso_path) != RETAIL_ISO_SHA256:
        raise AudioLocalizationError(
            f"retail ISO hash mismatch: expected {RETAIL_ISO_SHA256}"
        )
    entries = iso9660.read_entries(iso_path)
    pcm_entries = sorted(
        (
            entry
            for entry in entries
            if not entry.is_directory and Path(entry.path).suffix.upper() == ".PCM"
        ),
        key=lambda entry: Path(entry.path).name.upper(),
    )
    names = {Path(entry.path).name.upper() for entry in pcm_entries}
    if names != PCM_NAMES_EXPECTED:
        missing = sorted(PCM_NAMES_EXPECTED - names)
        extra = sorted(names - PCM_NAMES_EXPECTED)
        raise AudioLocalizationError(
            f"unexpected retail PCM inventory; missing={missing}, extra={extra}"
        )

    all_mappings: list[dict[str, Any]] = []
    chapter_stats: list[dict[str, Any]] = []
    for chapter_source in load_sources(sources_dir):
        chapter = chapter_source["chapter"]
        scn_path = unpacked_dir / chapter / f"{chapter}.SCN"
        scn = scn_path.read_bytes()
        mappings = map_chapter_audio(chapter_source, scn, names)
        all_mappings.extend(mappings)
        chapter_stats.append(
            {
                "chapter": chapter,
                "scn_sha256": sha256_bytes(scn),
                "audio_command_occurrences": len(mappings),
                "mapped_occurrences": sum(
                    1
                    for item in mappings
                    if item["mapping_relation"] not in {"unmapped", "sfx"}
                ),
            }
        )
    occurrences_by_pcm: dict[str, list[dict[str, Any]]] = {}
    for mapping in all_mappings:
        occurrences_by_pcm.setdefault(mapping["pcm"], []).append(mapping)

    raw_dir = output_dir / "original_pcm"
    wav_dir = output_dir / "japanese_wav"
    if write_audio:
        raw_dir.mkdir(parents=True, exist_ok=True)
        wav_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    with iso_path.open("rb") as iso_stream:
        for entry in pcm_entries:
            name = Path(entry.path).name.upper()
            raw = extract_entry(iso_stream, entry, iso9660.SECTOR_SIZE)
            if write_audio:
                (raw_dir / name).write_bytes(raw)
                write_wav(wav_dir / f"{Path(name).stem}.wav", decode_sign_magnitude(raw))
            occurrences = sorted(
                occurrences_by_pcm.get(name, []),
                key=lambda item: (item["chapter"], item["scn_audio_offset"]),
            )
            mapped = [
                item
                for item in occurrences
                if item["mapping_relation"] not in {"unmapped", "sfx"}
            ]
            canonical_values = sorted(
                {
                    item["canonical_english"]
                    for item in mapped
                    if item.get("canonical_english")
                }
            )
            speaker_values = sorted(
                {item["speaker"] for item in mapped if item.get("speaker")}
            )
            assets.append(
                {
                    "pcm": name,
                    "iso_path": entry.path,
                    "iso_extent": entry.extent,
                    "iso_size": entry.size,
                    "iso_allocated_size": entry.allocated_size,
                    "raw_sha256": sha256_bytes(raw),
                    "samples": len(raw),
                    "duration_seconds": round(
                        len(raw) * SAMPLE_RATE_DENOMINATOR / SAMPLE_RATE_NUMERATOR,
                        6,
                    ),
                    "leading_silence_samples": zero_run(raw),
                    "trailing_silence_samples": zero_run(raw, from_end=True),
                    "raw_path": f"original_pcm/{name}",
                    "japanese_wav_path": f"japanese_wav/{Path(name).stem}.wav",
                    "occurrences": occurrences,
                    "canonical_english_variants": canonical_values,
                    "speaker_variants": speaker_values,
                    "japanese_transcript": None,
                    "japanese_transcript_segments": [],
                    "asr_english_translation": None,
                    "asr_english_segments": [],
                    "asr_model": None,
                    "asr_status": "pending" if name != "BAKUHATU.PCM" else "skipped_sfx",
                    "voice": None,
                    "english_voice_path": None,
                    "game_rate_voice_path": None,
                    "voice_status": "pending" if canonical_values else "no_canonical_text",
                }
            )

    referenced_pcm = {item["pcm"] for item in all_mappings}
    mapped_pcm = {
        item["pcm"]
        for item in all_mappings
        if item["mapping_relation"] not in {"unmapped", "sfx"}
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "review-only audio localization; no game data modified",
        "retail_iso": {
            "path": str(iso_path.resolve()),
            "size": iso_path.stat().st_size,
            "sha256": RETAIL_ISO_SHA256,
        },
        "audio_format": {
            "source_codec": "RF5C164 8-bit sign-magnitude mono PCM",
            "source_clock_hz": RF5C164_CLOCK_HZ,
            "source_clock_divisor": RF5C164_CLOCK_DIVISOR,
            "frequency_delta_hex": f"0x{RF5C164_FD:04X}",
            "unity_frequency_delta_hex": f"0x{RF5C164_UNITY_FD:04X}",
            "exact_sample_rate_numerator": SAMPLE_RATE_NUMERATOR,
            "exact_sample_rate_denominator": SAMPLE_RATE_DENOMINATOR,
            "exact_sample_rate_hz": SAMPLE_RATE_NUMERATOR / SAMPLE_RATE_DENOMINATOR,
            "wav_sample_rate_hz": WAV_SAMPLE_RATE,
            "source_bits_per_sample": 8,
            "decoded_bits_per_sample": 16,
            "channels": 1,
            "source_bitrate_bps": round(
                SAMPLE_RATE_NUMERATOR / SAMPLE_RATE_DENOMINATOR * 8
            ),
            "decoded_wav_bitrate_bps": WAV_SAMPLE_RATE * 16,
        },
        "summary": {
            "pcm_assets": len(assets),
            "pcm_bytes": sum(item["iso_size"] for item in assets),
            "duration_seconds": round(
                sum(item["duration_seconds"] for item in assets), 6
            ),
            "scn_audio_command_occurrences": len(all_mappings),
            "mapped_occurrences": sum(
                1
                for item in all_mappings
                if item["mapping_relation"] not in {"unmapped", "sfx"}
            ),
            "mapped_unique_pcm": len(mapped_pcm),
            "unreferenced_pcm": sorted(names - referenced_pcm),
        },
        "chapters": chapter_stats,
        "assets": assets,
    }
    return manifest


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "audio_manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_transcript_exports(output_dir, manifest)
    return path


def transcript_row(asset: dict[str, Any]) -> dict[str, Any]:
    record_ids: list[str] = []
    for occurrence in asset["occurrences"]:
        for record_id in occurrence.get("record_ids", []):
            if record_id not in record_ids:
                record_ids.append(record_id)
    return {
        "pcm": asset["pcm"],
        "duration_seconds": asset["duration_seconds"],
        "record_ids": " | ".join(record_ids),
        "speakers": " | ".join(asset["speaker_variants"]),
        "japanese_transcript": asset.get("japanese_transcript") or "",
        "asr_english_translation": asset.get("asr_english_translation") or "",
        "canonical_english": " | ".join(asset["canonical_english_variants"]),
        "asr_model": asset.get("asr_model") or "",
        "asr_status": asset.get("asr_status") or "",
        "english_voice_script": asset.get("voice_text") or "",
        "english_voice_script_source": asset.get("voice_text_source") or "",
        "voice": asset.get("voice") or "",
        "voice_tempo_factor": asset.get("voice_tempo_factor") or "",
        "voice_fit_warning": asset.get("voice_fit_warning") or "",
        "voice_status": asset.get("voice_status") or "",
    }


def write_transcript_exports(output_dir: Path, manifest: dict[str, Any]) -> None:
    rows = [transcript_row(asset) for asset in manifest["assets"]]
    csv_path = output_dir / "transcripts.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    jsonl_path = output_dir / "transcripts.jsonl"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    warning_rows = [row for row in rows if row["voice_fit_warning"]]
    warning_path = output_dir / "voice_fit_warnings.csv"
    with warning_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(warning_rows)


def load_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "audio_manifest.json"
    if not path.is_file():
        raise AudioLocalizationError(f"manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise AudioLocalizationError("unsupported audio manifest schema")
    return manifest


GENERATED_FIELDS = (
    "japanese_transcript",
    "japanese_transcript_segments",
    "asr_english_translation",
    "asr_english_segments",
    "asr_model",
    "asr_language_probability",
    "asr_status",
    "voice",
    "voice_rate",
    "voice_pitch",
    "voice_speed",
    "voice_language",
    "voice_backend",
    "voice_model_sha256",
    "voice_voices_sha256",
    "voice_text",
    "voice_text_source",
    "voice_natural_duration_seconds",
    "voice_tempo_factor",
    "voice_time_fit_backend",
    "voice_fit_warning",
    "english_voice_source_path",
    "english_voice_path",
    "game_rate_voice_path",
    "voice_status",
)


def run_refresh(args: argparse.Namespace) -> None:
    previous = load_manifest(args.output)
    generated = {
        asset["pcm"]: {
            key: asset[key] for key in GENERATED_FIELDS if key in asset
        }
        for asset in previous["assets"]
    }
    manifest = build_manifest(args.clean_rebuild, args.output, write_audio=False)
    for asset in manifest["assets"]:
        asset.update(generated.get(asset["pcm"], {}))
    path = write_manifest(args.output, manifest)
    write_review(args.output, manifest)
    print(f"Refreshed extraction/mapping metadata without rewriting audio: {path}")


def run_extract(args: argparse.Namespace) -> None:
    manifest = build_manifest(args.clean_rebuild, args.output, write_audio=True)
    path = write_manifest(args.output, manifest)
    write_review(args.output, manifest)
    summary = manifest["summary"]
    print(
        f"Extracted {summary['pcm_assets']} PCM assets "
        f"({summary['duration_seconds'] / 3600:.2f} hours) to {args.output}"
    )
    print(
        f"Mapped {summary['mapped_occurrences']}/"
        f"{summary['scn_audio_command_occurrences']} SCN audio occurrences"
    )
    print(f"Manifest: {path}")


def segments_to_dicts(segments: Iterable[Any]) -> list[dict[str, Any]]:
    return [
        {
            "start": round(float(segment.start), 3),
            "end": round(float(segment.end), 3),
            "text": segment.text.strip(),
            "avg_logprob": round(float(segment.avg_logprob), 6),
            "no_speech_prob": round(float(segment.no_speech_prob), 6),
        }
        for segment in segments
    ]


def run_transcribe(args: argparse.Namespace) -> None:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise AudioLocalizationError(
            "faster-whisper is not installed; install requirements-asr.txt "
            "into an isolated environment first"
        ) from exc
    manifest = load_manifest(args.output)
    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
        download_root=str(args.model_cache) if args.model_cache else None,
        cpu_threads=args.cpu_threads,
    )
    selected = manifest["assets"]
    if args.only:
        only = {item.upper() for item in args.only}
        selected = [item for item in selected if item["pcm"].upper() in only]
    for number, asset in enumerate(selected, 1):
        if asset["asr_status"] == "skipped_sfx":
            continue
        if asset["asr_status"] == "complete" and not args.force:
            continue
        wav_path = args.output / asset["japanese_wav_path"]
        print(f"[{number}/{len(selected)}] {asset['pcm']}", flush=True)
        ja_segments, ja_info = model.transcribe(
            str(wav_path),
            language="ja",
            task="transcribe",
            beam_size=args.beam_size,
            vad_filter=args.vad_filter,
            condition_on_previous_text=False,
        )
        ja = segments_to_dicts(ja_segments)
        en_segments, _en_info = model.transcribe(
            str(wav_path),
            language="ja",
            task="translate",
            beam_size=args.beam_size,
            vad_filter=args.vad_filter,
            condition_on_previous_text=False,
        )
        en = segments_to_dicts(en_segments)
        asset["japanese_transcript_segments"] = ja
        asset["japanese_transcript"] = clean_text(
            " ".join(segment["text"] for segment in ja)
        )
        asset["asr_english_segments"] = en
        asset["asr_english_translation"] = clean_text(
            " ".join(segment["text"] for segment in en)
        )
        asset["asr_model"] = args.model
        asset["asr_language_probability"] = round(
            float(ja_info.language_probability), 6
        )
        asset["asr_status"] = "complete" if ja else "no_speech"
        if number % args.checkpoint_every == 0:
            write_manifest(args.output, manifest)
    write_manifest(args.output, manifest)
    write_review(args.output, manifest)


def choose_canonical_text(asset: dict[str, Any]) -> str:
    sequences = {
        tuple(occurrence.get("canonical_english_lines", []))
        for occurrence in asset.get("occurrences", [])
        if occurrence.get("canonical_english_lines")
    }
    if len(sequences) != 1:
        return ""
    return speech_text_from_lines(next(iter(sequences)))


def speech_text_from_lines(lines: Iterable[str]) -> str:
    """Join renderer-split canonical records into one natural speech prompt."""
    values = [clean_text(line) for line in lines if clean_text(line)]
    output: list[str] = []
    index = 0
    while index < len(values):
        bare = values[index].rstrip(".!?")
        if len(bare) == 1 and bare.isalpha() and bare.isupper():
            pieces: list[str] = []
            punctuation = ""
            while index < len(values):
                candidate = values[index]
                candidate_bare = candidate.rstrip(".!?")
                if not candidate_bare.isalpha() or not candidate_bare.isupper():
                    break
                pieces.append(candidate_bare)
                punctuation = candidate[len(candidate_bare) :]
                index += 1
            output.append("".join(pieces) + punctuation)
            continue
        output.append(values[index])
        index += 1
    return clean_text(" ".join(output))


def choose_english_text(
    asset: dict[str, Any], cast: dict[str, Any]
) -> tuple[str, str]:
    override = cast.get("assets", {}).get(asset["pcm"], {})
    if clean_text(override.get("text")):
        return clean_text(override["text"]), "cast_override"
    translated = clean_text(asset.get("asr_english_translation"))
    if translated and asset.get("asr_status") == "complete":
        for before, after in cast.get("voice_text_replacements", {}).items():
            translated = re.sub(
                rf"\b{re.escape(before)}\b",
                after,
                translated,
                flags=re.IGNORECASE,
            )
        return translated, "actual_audio_asr_translation"
    canonical = choose_canonical_text(asset)
    if canonical:
        return canonical, "canonical_translation_fallback"
    return "", "unavailable"


def load_cast(path: Path) -> dict[str, Any]:
    cast = json.loads(path.read_text(encoding="utf-8"))
    if cast.get("schema_version") != 1 or not isinstance(cast.get("speakers"), dict):
        raise AudioLocalizationError(f"invalid voice cast file: {path}")
    if cast.get("backend") != "kokoro-onnx":
        raise AudioLocalizationError(
            f"unsupported or nonlocal voice backend in {path}: "
            f"{cast.get('backend')!r}; expected 'kokoro-onnx'"
        )
    if not isinstance(cast.get("assets", {}), dict):
        raise AudioLocalizationError(f"invalid per-asset overrides in: {path}")
    if not isinstance(cast.get("voice_text_replacements", {}), dict):
        raise AudioLocalizationError(f"invalid voice text replacements in: {path}")
    return cast


def voice_for_asset(asset: dict[str, Any], cast: dict[str, Any]) -> str | None:
    override = cast.get("assets", {}).get(asset["pcm"], {})
    if override.get("voice"):
        return override["voice"]
    speakers = asset.get("speaker_variants", [])
    if len(speakers) == 1 and speakers[0] in cast["speakers"]:
        return cast["speakers"][speakers[0]]["voice"]
    return cast.get("default_voice")


def settings_for_asset(asset: dict[str, Any], cast: dict[str, Any]) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    speakers = asset.get("speaker_variants", [])
    if len(speakers) == 1:
        settings.update(cast["speakers"].get(speakers[0], {}))
    settings.update(cast.get("assets", {}).get(asset["pcm"], {}))
    return settings


def ffmpeg_convert(
    ffmpeg: Path,
    source: Path,
    destination: Path,
    *,
    sample_rate: int | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
    ]
    if sample_rate:
        command.extend(["-ar", str(sample_rate)])
    command.extend(["-c:a", "pcm_s16le", str(destination)])
    subprocess.run(command, check=True)


def atempo_filter(factor: float) -> str:
    """Build an atempo chain for an arbitrary positive duration ratio."""
    if not math.isfinite(factor) or factor <= 0:
        raise AudioLocalizationError(f"invalid tempo factor: {factor}")
    values: list[float] = []
    while factor < 0.5:
        values.append(0.5)
        factor /= 0.5
    while factor > 100.0:
        values.append(100.0)
        factor /= 100.0
    values.append(factor)
    return ",".join(f"atempo={value:.10f}" for value in values)


def ffmpeg_time_fit(
    ffmpeg: Path,
    source: Path,
    destination: Path,
    *,
    tempo_factor: float,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if math.isclose(tempo_factor, 1.0, rel_tol=0.0, abs_tol=1e-9):
        ffmpeg_convert(
            ffmpeg,
            source,
            destination,
            sample_rate=WAV_SAMPLE_RATE,
        )
        return "resample_only"
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-af",
        atempo_filter(tempo_factor),
        "-ac",
        "1",
        "-ar",
        str(WAV_SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(destination),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        return "atempo"
    except subprocess.CalledProcessError:
        subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-af",
                f"rubberband=tempo={tempo_factor:.10f}",
                "-ac",
                "1",
                "-ar",
                str(WAV_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
            check=True,
        )
        return "rubberband_fallback"


def force_wav_samples(
    path: Path,
    target_samples: int,
    *,
    leading_silence_samples: int = 0,
) -> None:
    channels, width, rate, data = read_wav(path)
    if (channels, width, rate) != (1, 2, WAV_SAMPLE_RATE):
        raise AudioLocalizationError(f"cannot fit unexpected WAV format: {path}")
    target_bytes = target_samples * 2
    prefix = b"\0" * min(leading_silence_samples, target_samples) * 2
    data = (prefix + data)[:target_bytes].ljust(target_bytes, b"\0")
    temporary = path.with_suffix(".fitted.wav")
    write_wav(temporary, data)
    temporary.replace(path)


def write_float_wav(path: Path, samples: Any, sample_rate: int) -> None:
    """Write model float samples as deterministic mono PCM16 WAV."""
    try:
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise AudioLocalizationError(
            "numpy is unavailable; install requirements-tts.txt first"
        ) from exc
    values = np.asarray(samples, dtype=np.float32).reshape(-1)
    pcm16 = np.rint(np.clip(values, -1.0, 1.0) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm16.tobytes())


def synthesize_kokoro_asset(
    engine: Any,
    asset: dict[str, Any],
    output_dir: Path,
    voice: str,
    text: str,
    speed: float,
    language: str,
) -> Path:
    destination = output_dir / "english_voice_source" / f"{Path(asset['pcm']).stem}.wav"
    samples, sample_rate = engine.create(
        text,
        voice=voice,
        speed=speed,
        lang=language,
        trim=True,
    )
    write_float_wav(destination, samples, sample_rate)
    return destination


def synthesize_all(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.output)
    cast = load_cast(args.cast)
    if not args.model.is_file():
        raise AudioLocalizationError(f"Kokoro model not found: {args.model}")
    if not args.voices.is_file():
        raise AudioLocalizationError(f"Kokoro voices not found: {args.voices}")
    if ISOLATED_TTS_RUNTIME.is_dir():
        sys.path.insert(0, str(ISOLATED_TTS_RUNTIME))
    try:
        from kokoro_onnx import Kokoro  # type: ignore
    except ImportError as exc:
        raise AudioLocalizationError(
            "kokoro-onnx is not installed; install requirements-tts.txt into "
            ".kokoro_runtime first"
        ) from exc
    engine = Kokoro(str(args.model), str(args.voices))
    available_voices = set(engine.get_voices())
    model_sha256 = sha256_path(args.model)
    voices_sha256 = sha256_path(args.voices)
    selected = manifest["assets"]
    if args.only:
        only = {item.upper() for item in args.only}
        selected = [item for item in selected if item["pcm"].upper() in only]
    for number, asset in enumerate(selected, 1):
        if asset.get("voice_status") == "complete" and not args.force:
            if not asset.get("voice_time_fit_backend"):
                asset["voice_time_fit_backend"] = "atempo_pre_fallback"
            continue
        if asset["occurrences"] and all(
            occurrence.get("mapping_relation") == "sfx"
            for occurrence in asset["occurrences"]
        ):
            asset["voice_status"] = "skipped_sfx"
            continue
        text, text_source = choose_english_text(asset, cast)
        if not text:
            asset["voice_status"] = "awaiting_reviewed_english_text"
            continue
        voice = voice_for_asset(asset, cast)
        if not voice:
            asset["voice_status"] = "unassigned_voice"
            continue
        if voice not in available_voices:
            asset["voice_status"] = f"unavailable_voice: {voice}"
            write_manifest(args.output, manifest)
            continue
        settings = settings_for_asset(asset, cast)
        speed = float(settings.get("speed", cast.get("default_speed", 1.0)))
        language = settings.get("language", cast.get("default_language", "en-us"))
        if not 0.5 <= speed <= 2.0:
            asset["voice_status"] = f"invalid_speed: {speed}"
            write_manifest(args.output, manifest)
            continue
        print(
            f"[{number}/{len(selected)}] {asset['pcm']} {voice}: {text}",
            flush=True,
        )
        for attempt in range(1, args.retries + 1):
            try:
                source = synthesize_kokoro_asset(
                    engine,
                    asset,
                    args.output,
                    voice,
                    text,
                    speed,
                    language,
                )
                review_wav = (
                    args.output
                    / "english_voice_wav"
                    / f"{Path(asset['pcm']).stem}.wav"
                )
                game_wav = (
                    args.output
                    / "english_voice_game_rate"
                    / f"{Path(asset['pcm']).stem}.wav"
                )
                ffmpeg_convert(args.ffmpeg, source, review_wav)
                channels, width, natural_rate, natural_data = read_wav(review_wav)
                if channels != 1 or width != 2:
                    raise AudioLocalizationError(
                        f"unexpected synthesized WAV format for {asset['pcm']}"
                    )
                natural_duration = len(natural_data) / 2 / natural_rate
                target_duration = asset["duration_seconds"]
                leading_seconds = (
                    asset["leading_silence_samples"] / WAV_SAMPLE_RATE
                )
                available_speech_seconds = max(
                    target_duration - leading_seconds,
                    1 / WAV_SAMPLE_RATE,
                )
                tempo_factor = max(
                    1.0,
                    natural_duration / available_speech_seconds,
                )
                time_fit_backend = ffmpeg_time_fit(
                    args.ffmpeg,
                    source,
                    game_wav,
                    tempo_factor=tempo_factor,
                )
                force_wav_samples(
                    game_wav,
                    asset["samples"],
                    leading_silence_samples=asset["leading_silence_samples"],
                )
                asset["voice"] = voice
                asset.pop("voice_rate", None)
                asset.pop("voice_pitch", None)
                asset["voice_speed"] = speed
                asset["voice_language"] = language
                asset["voice_backend"] = cast["backend"]
                asset["voice_model_sha256"] = model_sha256
                asset["voice_voices_sha256"] = voices_sha256
                asset["voice_text"] = text
                asset["voice_text_source"] = text_source
                asset["voice_natural_duration_seconds"] = round(
                    natural_duration, 6
                )
                asset["voice_tempo_factor"] = round(tempo_factor, 8)
                asset["voice_time_fit_backend"] = time_fit_backend
                asset["voice_fit_warning"] = (
                    "extreme speed-up; review delivery or wording"
                    if tempo_factor > 1.75
                    else None
                )
                asset["english_voice_source_path"] = source.relative_to(
                    args.output
                ).as_posix()
                asset["english_voice_path"] = review_wav.relative_to(
                    args.output
                ).as_posix()
                asset["game_rate_voice_path"] = game_wav.relative_to(
                    args.output
                ).as_posix()
                asset["voice_status"] = "complete"
                break
            except Exception as exc:
                asset["voice_status"] = (
                    f"error attempt {attempt}/{args.retries}: "
                    f"{type(exc).__name__}: {exc}"
                )
                write_manifest(args.output, manifest)
        if number % args.checkpoint_every == 0:
            write_manifest(args.output, manifest)
    write_manifest(args.output, manifest)
    write_review(args.output, manifest)


def run_synthesize(args: argparse.Namespace) -> None:
    synthesize_all(args)


def media_cell(path: str | None) -> str:
    if not path:
        return ""
    escaped = html.escape(path, quote=True)
    return f'<audio controls preload="none" src="{escaped}"></audio>'


def write_review(output_dir: Path, manifest: dict[str, Any]) -> Path:
    rows: list[str] = []
    for asset in manifest["assets"]:
        occurrence = next(
            (
                item
                for item in asset["occurrences"]
                if item["mapping_relation"] != "unmapped"
            ),
            {},
        )
        canonical = " / ".join(asset["canonical_english_variants"])
        rows.append(
            "<tr>"
            f"<td>{html.escape(asset['pcm'])}</td>"
            f"<td>{html.escape(occurrence.get('record_id', ''))}</td>"
            f"<td>{html.escape(' / '.join(asset['speaker_variants']))}</td>"
            f"<td>{media_cell(asset['japanese_wav_path'])}</td>"
            f"<td lang=\"ja\">{html.escape(asset.get('japanese_transcript') or '')}</td>"
            f"<td>{html.escape(asset.get('asr_english_translation') or '')}</td>"
            f"<td>{html.escape(canonical)}</td>"
            f"<td>{html.escape(asset.get('voice_text') or '')}"
            f"<br><small>{html.escape(asset.get('voice_text_source') or '')}</small></td>"
            f"<td>{media_cell(asset.get('english_voice_path'))}</td>"
            f"<td>{media_cell(asset.get('game_rate_voice_path'))}</td>"
            f"<td>{html.escape(asset.get('voice_status') or '')}"
            f"{'<br>' + html.escape(asset['voice_fit_warning']) if asset.get('voice_fit_warning') else ''}</td>"
            "</tr>"
        )
    summary = manifest["summary"]
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nostalgia 1907 Audio Localization Review</title>
<style>
body {{ font: 14px system-ui,sans-serif; margin: 1.5rem; color: #222; }}
h1 {{ margin-bottom: .25rem; }}
.note {{ max-width: 80rem; line-height: 1.45; }}
table {{ border-collapse: collapse; width: 100%; }}
th,td {{ border: 1px solid #bbb; padding: .35rem; vertical-align: top; }}
th {{ position: sticky; top: 0; background: #eee; z-index: 1; }}
tr:nth-child(even) {{ background: #f8f8f8; }}
audio {{ width: 220px; }}
</style>
</head>
<body>
<h1>Nostalgia 1907 Audio Localization Review</h1>
<p class="note">Review-only package from the hash-locked Japanese retail ISO.
Decoded audio is mono 16-bit PCM at {WAV_SAMPLE_RATE} Hz (the integer WAV
representation of the exact {manifest['audio_format']['exact_sample_rate_hz']:.6f}
Hz game rate). No files in the game build are changed.</p>
<p>{summary['pcm_assets']} PCM assets; {summary['duration_seconds']/3600:.2f}
hours; {summary['mapped_occurrences']} of
{summary['scn_audio_command_occurrences']} SCN occurrences mapped.</p>
<table>
<thead><tr><th>PCM</th><th>Record</th><th>Speaker</th><th>Japanese audio</th>
<th>Japanese ASR</th><th>ASR English</th><th>Canonical English</th>
<th>English voice script</th><th>Natural English voice</th>
<th>Game-slot English voice</th><th>Status</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body></html>
"""
    path = output_dir / "review.html"
    path.write_text(document, encoding="utf-8")
    return path


def validate_manifest(output_dir: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    assets = manifest.get("assets", [])
    if len(assets) != len(PCM_NAMES_EXPECTED):
        errors.append(f"expected 1828 assets, found {len(assets)}")
    names = {asset.get("pcm") for asset in assets}
    if names != PCM_NAMES_EXPECTED:
        errors.append("manifest PCM filename inventory differs from retail contract")
    for asset in assets:
        name = asset["pcm"]
        raw_path = output_dir / asset["raw_path"]
        wav_path = output_dir / asset["japanese_wav_path"]
        if not raw_path.is_file():
            errors.append(f"{name}: missing raw PCM")
            continue
        raw = raw_path.read_bytes()
        if len(raw) != asset["iso_size"]:
            errors.append(f"{name}: raw size mismatch")
        if sha256_bytes(raw) != asset["raw_sha256"]:
            errors.append(f"{name}: raw hash mismatch")
        if not wav_path.is_file():
            errors.append(f"{name}: missing decoded WAV")
            continue
        try:
            channels, width, rate, frames = read_wav(wav_path)
        except (wave.Error, EOFError) as exc:
            errors.append(f"{name}: invalid WAV: {exc}")
            continue
        if (channels, width, rate) != (1, 2, WAV_SAMPLE_RATE):
            errors.append(
                f"{name}: WAV format {(channels, width, rate)} != "
                f"{(1, 2, WAV_SAMPLE_RATE)}"
            )
        if len(frames) != len(raw) * 2:
            errors.append(f"{name}: decoded sample count mismatch")
        if frames != decode_sign_magnitude(raw):
            errors.append(f"{name}: decoded PCM content mismatch")
        if asset.get("voice_status") == "complete":
            if not clean_text(asset.get("voice_text")):
                errors.append(f"{name}: completed voice has no English script")
            if asset.get("voice_backend") != "kokoro-onnx":
                errors.append(f"{name}: completed voice has wrong local backend")
            if not asset.get("voice_model_sha256") or not asset.get(
                "voice_voices_sha256"
            ):
                errors.append(f"{name}: completed voice lacks model provenance")
            if not asset.get("voice_time_fit_backend"):
                errors.append(f"{name}: completed voice lacks timing provenance")
            for key in ("english_voice_source_path", "english_voice_path"):
                value = asset.get(key)
                if not value:
                    errors.append(f"{name}: completed voice lacks {key}")
                    continue
                candidate = output_dir / value
                if not candidate.is_file():
                    errors.append(f"{name}: missing {key}")
                    continue
                try:
                    c, w, r, voice_data = read_wav(candidate)
                except (wave.Error, EOFError) as exc:
                    errors.append(f"{name}: invalid {key}: {exc}")
                    continue
                if c != 1 or w != 2 or r <= 0 or not voice_data:
                    errors.append(f"{name}: invalid {key} audio contract")
        voice_path = asset.get("game_rate_voice_path")
        if voice_path:
            candidate = output_dir / voice_path
            if not candidate.is_file():
                errors.append(f"{name}: missing game-rate voice WAV")
            else:
                c, w, r, _data = read_wav(candidate)
                if (c, w, r) != (1, 2, WAV_SAMPLE_RATE):
                    errors.append(f"{name}: invalid game-rate voice WAV format")
                elif len(_data) != asset["samples"] * 2:
                    errors.append(f"{name}: game-rate voice sample count mismatch")
    return errors


def run_validate(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.output)
    errors = validate_manifest(args.output, manifest)
    fresh = build_manifest(args.clean_rebuild, args.output, write_audio=False)
    expected = {
        asset["pcm"]: (
            asset["raw_sha256"],
            asset["occurrences"],
            asset["canonical_english_variants"],
        )
        for asset in fresh["assets"]
    }
    actual = {
        asset["pcm"]: (
            asset["raw_sha256"],
            asset["occurrences"],
            asset["canonical_english_variants"],
        )
        for asset in manifest["assets"]
    }
    if expected != actual:
        errors.append("manifest extraction/mapping metadata is stale")
    if errors:
        raise AudioLocalizationError(
            f"validation failed with {len(errors)} error(s):\n- "
            + "\n- ".join(errors[:100])
        )
    complete_voices = sum(
        asset.get("voice_status") == "complete" for asset in manifest["assets"]
    )
    print(
        f"PASS: {len(manifest['assets'])} assets, exact raw hashes, "
        f"{WAV_SAMPLE_RATE} Hz mono PCM16 WAVs, current SCN/source mappings, "
        f"and {complete_voices} complete English voice triplets"
    )


def default_clean_rebuild() -> Path:
    return Path(__file__).resolve().parents[1] / "clean_rebuild"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--clean-rebuild",
        type=Path,
        default=default_clean_rebuild(),
        help="validated work/clean_rebuild directory",
    )
    result.add_argument(
        "--output",
        type=Path,
        required=True,
        help="isolated review output directory",
    )
    commands = result.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="extract/map all retail PCM")
    extract.set_defaults(function=run_extract)

    transcribe = commands.add_parser(
        "transcribe", help="transcribe Japanese and make an ASR English translation"
    )
    transcribe.add_argument("--model", default="large-v3")
    transcribe.add_argument("--model-cache", type=Path)
    transcribe.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    transcribe.add_argument("--compute-type", default="int8")
    transcribe.add_argument("--cpu-threads", type=int, default=0)
    transcribe.add_argument("--beam-size", type=int, default=5)
    transcribe.add_argument(
        "--vad-filter", action=argparse.BooleanOptionalAction, default=False
    )
    transcribe.add_argument("--checkpoint-every", type=int, default=25)
    transcribe.add_argument("--only", nargs="*")
    transcribe.add_argument("--force", action="store_true")
    transcribe.set_defaults(function=run_transcribe)

    synthesize = commands.add_parser(
        "synthesize", help="make review-only English voice files with local Kokoro"
    )
    synthesize.add_argument("--cast", type=Path, required=True)
    synthesize.add_argument("--ffmpeg", type=Path, required=True)
    model_dir = Path(__file__).resolve().parent / ".kokoro_models"
    synthesize.add_argument(
        "--model",
        type=Path,
        default=model_dir / "kokoro-v1.0.onnx",
        help="local Kokoro ONNX model",
    )
    synthesize.add_argument(
        "--voices",
        type=Path,
        default=model_dir / "voices-v1.0.bin",
        help="local Kokoro voice-style file",
    )
    synthesize.add_argument("--checkpoint-every", type=int, default=25)
    synthesize.add_argument("--retries", type=int, default=3)
    synthesize.add_argument("--only", nargs="*")
    synthesize.add_argument("--force", action="store_true")
    synthesize.set_defaults(function=run_synthesize)

    validate = commands.add_parser(
        "validate", help="validate extraction, mapping, and generated audio"
    )
    validate.set_defaults(function=run_validate)

    refresh = commands.add_parser(
        "refresh", help="refresh mappings while preserving ASR/voice results"
    )
    refresh.set_defaults(function=run_refresh)
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parser().parse_args()
    args.clean_rebuild = args.clean_rebuild.resolve()
    args.output = args.output.resolve()
    try:
        args.function(args)
    except (AudioLocalizationError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

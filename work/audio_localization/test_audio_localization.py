#!/usr/bin/env python3
"""Unit tests for the codec and structural SCN audio mapping."""

from __future__ import annotations

import tempfile
import unittest
import wave
import json
from unittest import mock
from pathlib import Path

import audio_localization as audio


class CodecTests(unittest.TestCase):
    """Exercise reversible audio-codec and WAV boundary behavior."""

    def test_decode_sign_magnitude(self) -> None:
        """Decode both sign-magnitude polarities into canonical PCM."""
        raw = bytes((0x00, 0x01, 0x7F, 0x80, 0x81, 0xFF))
        expected = (0, 256, 32512, 0, -256, -32512)
        decoded = audio.decode_sign_magnitude(raw)
        actual = tuple(
            int.from_bytes(decoded[offset : offset + 2], "little", signed=True)
            for offset in range(0, len(decoded), 2)
        )
        self.assertEqual(actual, expected)

    def test_codec_round_trip(self) -> None:
        """Round-trip every non-alternate sign-magnitude byte."""
        # 0x80 is the alternate sign-magnitude encoding of zero.  Decoding
        # intentionally canonicalizes both zero encodings back to 0x00.
        raw = bytes(range(0x80)) + bytes(range(0x81, 0x100))
        decoded = audio.decode_sign_magnitude(raw)
        samples = [
            int.from_bytes(decoded[offset : offset + 2], "little", signed=True)
            for offset in range(0, len(decoded), 2)
        ]
        encoded = audio.encode_sign_magnitude(samples)
        self.assertEqual(encoded, raw)

    def test_wav_contract(self) -> None:
        """Write the required mono PCM WAV contract."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.wav"
            frames = audio.decode_sign_magnitude(bytes((0, 1, 0x81)))
            audio.write_wav(path, frames)
            with wave.open(str(path), "rb") as stream:
                self.assertEqual(stream.getnchannels(), 1)
                self.assertEqual(stream.getsampwidth(), 2)
                self.assertEqual(stream.getframerate(), 16276)
                self.assertEqual(stream.getnframes(), 3)
                self.assertEqual(stream.readframes(3), frames)

    def test_force_wav_samples(self) -> None:
        """Pad a WAV to an exact sample count."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fit.wav"
            audio.write_wav(path, audio.decode_sign_magnitude(bytes((1, 2, 3))))
            audio.force_wav_samples(path, 5)
            channels, width, rate, data = audio.read_wav(path)
            self.assertEqual((channels, width, rate), (1, 2, 16276))
            self.assertEqual(len(data), 10)
            self.assertEqual(data[-4:], b"\0\0\0\0")

    def test_force_wav_samples_preserves_leading_delay(self) -> None:
        """Retain configured leading silence while fitting a WAV."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fit.wav"
            audio.write_wav(path, audio.decode_sign_magnitude(bytes((1, 2, 3))))
            audio.force_wav_samples(path, 6, leading_silence_samples=2)
            _channels, _width, _rate, data = audio.read_wav(path)
            self.assertEqual(data[:4], b"\0\0\0\0")
            self.assertEqual(data[4:10], audio.decode_sign_magnitude(bytes((1, 2, 3))))
            self.assertEqual(data[10:], b"\0\0")

    def test_zero_run_counts_only_boundary_silence(self) -> None:
        """Count only boundary silence in raw sign-magnitude audio."""
        raw = bytes((0, 0, 1, 0, 2, 0, 0, 0))
        self.assertEqual(audio.zero_run(raw), 2)
        self.assertEqual(audio.zero_run(raw, from_end=True), 3)

    def test_atempo_chain(self) -> None:
        """Factor tempo changes into FFmpeg-compatible filters."""
        self.assertEqual(audio.atempo_filter(1.25), "atempo=1.2500000000")
        values = [
            float(item.split("=", 1)[1]) for item in audio.atempo_filter(0.2).split(",")
        ]
        product = 1.0
        for value in values:
            product *= value
        self.assertAlmostEqual(product, 0.2)

    def test_time_fit_one_uses_resample_only(self) -> None:
        """Use resampling only when duration already matches."""
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.wav"
            destination = Path(temporary) / "destination.wav"
            with mock.patch.object(audio, "ffmpeg_convert") as convert:
                backend = audio.ffmpeg_time_fit(
                    Path("ffmpeg"),
                    source,
                    destination,
                    tempo_factor=1.0,
                )
            self.assertEqual(backend, "resample_only")
            convert.assert_called_once_with(
                Path("ffmpeg"),
                source,
                destination,
                sample_rate=audio.WAV_SAMPLE_RATE,
            )

    def test_write_float_wav(self) -> None:
        """Clamp and write normalized floating-point audio."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "float.wav"
            audio.write_float_wav(path, [-1.5, -0.5, 0.0, 0.5, 1.5], 24000)
            channels, width, rate, data = audio.read_wav(path)
            self.assertEqual((channels, width, rate), (1, 2, 24000))
            values = [
                int.from_bytes(data[offset : offset + 2], "little", signed=True)
                for offset in range(0, len(data), 2)
            ]
            self.assertEqual(values, [-32767, -16384, 0, 16384, 32767])

    def test_cast_rejects_external_backend(self) -> None:
        """Reject unsupported external voice backends."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cast.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "backend": "edge-tts",
                        "speakers": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(audio.AudioLocalizationError):
                audio.load_cast(path)

    def test_speech_text_rejoins_renderer_spelling(self) -> None:
        """Rejoin renderer-split spelling for synthesized speech."""
        self.assertEqual(
            audio.speech_text_from_lines(["Come now.", "C", "L", "I", "MAX!"]),
            "Come now. CLIMAX!",
        )
        self.assertEqual(
            audio.speech_text_from_lines(["M", "E", "D", "E", "did."]),
            "MEDE did.",
        )


class MappingTests(unittest.TestCase):
    """Exercise SCN audio-to-dialogue mapping contracts."""

    def setUp(self) -> None:
        """Create a compact canonical chapter fixture for mapping assertions."""
        self.source = {
            "chapter": "TEST",
            "record_count": 4,
            "profile": {},
            "records": [
                {"text": "Room", "policy": "translate"},
                {"text": "Ilyu", "policy": "translate"},
                {"text": "Line one.", "policy": "translate"},
                {"text": "Line two.", "policy": "translate"},
            ],
        }

    def test_following_dialogue(self) -> None:
        """Map dialogue that immediately follows its audio command."""
        scn = b"r0001.pcm\0" + bytes((0x21, 0, 2, 0, 3))
        mapped = audio.map_chapter_audio(self.source, scn, {"0001.PCM"})
        self.assertEqual(mapped[0]["record_id"], "TEST:002")
        self.assertEqual(mapped[0]["speaker"], "Ilyu")
        self.assertEqual(mapped[0]["canonical_english"], "Line one.")
        self.assertEqual(mapped[0]["mapping_relation"], "following")

    def test_dialogue_can_span_following_continuations(self) -> None:
        """Map a following dialogue span across continuation records."""
        scn = b"r0001.pcm\0" + bytes((0x21, 0, 2, 0, 3)) + bytes((0x21, 0, 4, 0, 0))
        mapped = audio.map_chapter_audio(self.source, scn, {"0001.PCM"})
        self.assertEqual(mapped[0]["record_ids"], ["TEST:002", "TEST:003"])

    def test_announcement_can_start_before_audio_command(self) -> None:
        """Map announcements whose dialogue begins before the audio command."""
        scn = (
            bytes((0x21, 0, 2, 0, 3))
            + b"\x3b"
            + b"r0001.pcm\0"
            + bytes((0x21, 0, 4, 0, 0))
        )
        mapped = audio.map_chapter_audio(self.source, scn, {"0001.PCM"})
        self.assertEqual(mapped[0]["record_ids"], ["TEST:002", "TEST:003"])

    def test_preceding_start_style_window(self) -> None:
        """Map dialogue found in the preceding start-style command window."""
        window = bytes((0x24, 0, 0, 0x14, 0, 0x27, 0, 3))
        scn = window + b"r0000.pcm\0"
        mapped = audio.map_chapter_audio(self.source, scn, {"0000.PCM"})
        self.assertEqual(mapped[0]["record_id"], "TEST:002")
        self.assertEqual(mapped[0]["mapping_relation"], "preceding")

    def test_unknown_filename_is_ignored(self) -> None:
        """Ignore PCM filenames absent from the known audio inventory."""
        scn = b"r9999.pcm\0" + bytes((0x21, 0, 2, 0, 3))
        self.assertEqual(audio.map_chapter_audio(self.source, scn, set()), [])

    def test_preceding_inline_dialogue(self) -> None:
        """Map inline dialogue immediately preceding an audio command."""
        scn = bytes((0x20, 0, 4)) + b"r1821.pcm\0"
        mapped = audio.map_chapter_audio(self.source, scn, {"1821.PCM"})
        self.assertEqual(mapped[0]["record_id"], "TEST:003")
        self.assertEqual(mapped[0]["canonical_english"], "Line two.")
        self.assertEqual(mapped[0]["mapping_relation"], "inline_span")

    def test_inline_span_can_cover_multiple_records(self) -> None:
        """Map a preceding inline span that covers multiple records."""
        scn = bytes((0x20, 0, 3)) + bytes((0x20, 0, 4)) + b"r1823.pcm\0"
        mapped = audio.map_chapter_audio(self.source, scn, {"1823.PCM"})
        self.assertEqual(mapped[0]["record_ids"], ["TEST:002", "TEST:003"])
        self.assertEqual(
            mapped[0]["canonical_english_lines"], ["Line one.", "Line two."]
        )

    def test_named_explosion_is_not_mapped_to_dialogue(self) -> None:
        """Keep named sound effects separate from dialogue mappings."""
        scn = bytes((0x21, 0, 2, 0, 3)) + b"rBAKUHATU.pcm\0"
        mapped = audio.map_chapter_audio(self.source, scn, {"BAKUHATU.PCM"})
        self.assertEqual(mapped[0]["mapping_relation"], "sfx")
        self.assertNotIn("record_id", mapped[0])


if __name__ == "__main__":
    unittest.main()

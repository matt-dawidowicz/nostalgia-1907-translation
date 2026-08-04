# Nostalgia 1907 audio-localization review tool

This directory is a review-only companion to `work/clean_rebuild`. It never
patches an ISO, BIN, CUE, SCN, MES, or canonical source file.

## What it does

- Hash-locks the verified Japanese `retail.iso`.
- Extracts all 1,828 Track 1 `.PCM` files byte-for-byte.
- Decodes the RF5C164 8-bit sign-magnitude audio into standard mono PCM16 WAV.
- Uses the playback delta in the retail executable (`FD=0x0400`) to represent
  the exact 16,276.041666... Hz game rate as a 16,276 Hz WAV.
- Maps SCN `r*.pcm` commands to chapter/record/speaker IDs and canonical English.
- Optionally runs local Faster-Whisper for Japanese transcription and a separate
  ASR English translation.
- Optionally produces non-imitative English voice previews locally with
  Kokoro ONNX.
- Builds an HTML page for line-by-line listening and review.

The raw source bitrate is about 130,208 bps (8-bit mono at the exact game
rate). The decoded review WAVs are 260,416 bps (16-bit mono at 16,276 Hz).

## Extract

From this directory:

```powershell
python .\audio_localization.py `
  --output ..\..\outputs\Nostalgia1907_Audio_Localization_Preview `
  extract
```

The output contains:

- `original_pcm/`: exact retail files.
- `japanese_wav/`: game-speed standard WAVs.
- `audio_manifest.json`: hashes, timing, SCN occurrences, records, speakers,
  canonical English, transcription, and voice-preview status.
- `transcripts.csv` and `transcripts.jsonl`: flat Japanese/English transcript
  exports for editing or reuse. They keep raw Japanese ASR, raw ASR English,
  canonical English, and the exact English voice script in separate fields.
- `voice_fit_warnings.csv`: only the English deliveries that required unusually
  strong acceleration and should be reviewed first.
- `review.html`: browser-based A/B review.

## Transcribe

Install `requirements-asr.txt` into the tool's isolated `.runtime` directory:

```powershell
python -m pip install --target .\.runtime -r .\requirements-asr.txt
```

Then:

```powershell
python .\audio_localization.py `
  --output ..\..\outputs\Nostalgia1907_Audio_Localization_Preview `
  transcribe --model large-v3 --device cpu --compute-type int8
```

`large-v3`, rather than Turbo, is the default because the tool requests both
Japanese transcription and Whisper's speech-to-English translation task.
Transcription is checkpointed every 25 files and can be resumed by rerunning.
Completed assets are skipped unless `--force` is supplied. Use
`--only 0000.PCM 0001.PCM` for a pilot.

On Windows, optional CUDA 12/cuDNN 9 DLLs can be kept in `.cuda`. The tool adds
that one directory to its process DLL search path; it does not copy files into
`System32` or modify the system environment. The reviewed CUDA 12.8 archive was
`cuBLAS.and.cuDNN_CUDA12_win_v3.7z`, SHA-256
`EC00119DBEEC2ADFF661302883BECD004028784031A4547EA1749E7683FFB67F`.

The Japanese and machine-translated English fields are automated drafts. The
canonical English field remains the authoritative game translation and is kept
separate so that disagreements are visible.

## Synthesize English review audio

Copy `voice_cast.example.json` to a review-specific cast file and assign generic
voices. Do not use or train imitation/cloned voices of the Japanese performers.
The synthesis command accepts only the local `kokoro-onnx` backend; it does not
send dialogue, transcripts, or audio to an online service.

```powershell
python -m pip install --target .\.kokoro_runtime -r .\requirements-tts.txt
```

Download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the official
`kokoro-onnx` model-files-v1.0 release into `.kokoro_models`. The default model
is the full 32-bit model; a different local ONNX model can be selected with
`--model`.

```powershell
python .\audio_localization.py `
  --output ..\..\outputs\Nostalgia1907_Audio_Localization_Preview `
  synthesize `
  --cast .\voice_cast.review.json `
  --ffmpeg "C:\Program Files\ShareX\ffmpeg.exe"
```

The generated natural-speed source WAV, normalized review WAV, and exact-length
16,276 Hz game-rate WAV remain review assets. They are not inserted into the
disc. The model and voice-style SHA-256 hashes are recorded per completed
asset, and reruns skip completed assets unless `--force` is supplied.

Voice previews prefer the machine translation of the actual audio, with
reviewed per-asset overrides where required. Canonical game text is retained
beside it and is only a fallback for a clip with no usable audio translation.
This avoids speaking unrelated renderer records when one long PCM overlaps
several timed SCN text commands.

Short English deliveries retain their natural pace and are padded to the
retail clip boundary. Overlong deliveries are pitch-preservingly accelerated,
resampled to 16,276 Hz, and padded or truncated to the exact retail sample
count. The manifest flags unusually strong acceleration for human review.
The HTML review shows both the natural English delivery and its exact game-slot
version beside the Japanese source.

## Validate

```powershell
python .\audio_localization.py `
  --output ..\..\outputs\Nostalgia1907_Audio_Localization_Preview `
  validate
```

Validation re-reads the retail ISO and current SCN/canonical sources, verifies
every raw PCM hash, decodes every WAV again, and rejects stale mappings.

If only SCN/source mapping logic changes, `refresh` rebuilds provenance without
rewriting audio or discarding completed ASR/TTS fields:

```powershell
python .\audio_localization.py `
  --output ..\..\outputs\Nostalgia1907_Audio_Localization_Preview `
  refresh
```

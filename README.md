# Nostalgia 1907 English translation

This private repository contains the canonical translation, deterministic
rebuild pipeline, validation code, and review tools for the English
localization of the Japanese Mega-CD game *Nostalgia 1907*.

The current validated baseline is `Nostalgia1907_CleanRebuild_v7`. It is built
only from the original Japanese disc and does not restore or depend on an older
translated build. Manual playtesting remains the final release gate.

The canonical sources also contain the reviewed post-v7 English revision. These
source edits remain a release candidate until the retail-backed validation and
scene/branch playtesting gates are completed; they do not rename or supersede
the already validated v7 binary artifact.

## Contributor documentation

New contributors should begin with [CONTRIBUTING.md](CONTRIBUTING.md). The
detailed references separate translation editing from binary-format work:

- [Architecture and production boundaries](docs/ARCHITECTURE.md)
- [Translation analysis and editing](docs/TRANSLATION_EDITING.md)
- [English glossary and localization style guide](docs/GLOSSARY_STYLE_GUIDE.md)
- [MES, LZ, ISO, raw-CD, font, and SCN formats](docs/BINARY_FORMATS.md)
- [Development, reports, debugging, and validation](docs/DEVELOPMENT.md)

These guides explain which files are authoritative, how stable record IDs map
to the original game, and which invariants must hold before a change can become
a playable build.

## Quick start

From a fresh clone on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Place legally obtained original Japanese tracks at:

```text
work/clean_rebuild/retail_input/Nostalgia 1907 (Japan) (Track 1).bin
work/clean_rebuild/retail_input/Nostalgia 1907 (Japan) (Track 2).bin
```

Then run:

```powershell
python nostalgia1907.py doctor
python nostalgia1907.py prepare
python nostalgia1907.py validate
```

`doctor` verifies Python, Pillow, the canonical source inventory, both original
track hashes, and the prepared retail-reference state. It reports optional BIOS
and FFmpeg readiness separately.

## Machine-specific paths

Instead of copying the original tracks into the checkout, create the ignored
`nostalgia1907.local.json` file:

```json
{
  "track1": "D:/Sega CD Games/Nostalgia 1907 (Japan)/Nostalgia 1907 (Japan) (Track 1).bin",
  "track2": "D:/Sega CD Games/Nostalgia 1907 (Japan)/Nostalgia 1907 (Japan) (Track 2).bin",
  "us_bios": "D:/Emulation/Sega CD (U) - Model 2 v2.00w (1993).bin",
  "ffmpeg": "C:/Program Files/FFmpeg/bin/ffmpeg.exe"
}
```

Command-line paths override local configuration, which overrides the
conventional `retail_input` directory.

## Canonical translation

The canonical script is:

- `work/clean_rebuild/sources/index.json`
- `work/clean_rebuild/sources/<CHAPTER>.json`

Each English entry is keyed by a stable chapter and record ID. Japanese records,
IDs, ordering, control codes, branching, SCN data, and binary boundaries remain
authoritative. The global renderer-aware formatter owns general line wrapping;
chapter-specific binary layout patches are not part of the production workflow.

Preview a wording change without writing:

```powershell
python nostalgia1907.py edit PART1A:003 `
  --text 'How about we switch games and play one more round?'
```

Apply one reviewed change only after its preview passes:

```powershell
python nostalgia1907.py edit PART1A:003 `
  --text 'How about we switch games and play one more round?' `
  --apply
```

For a batch, use an ID-keyed JSON file:

```powershell
python nostalgia1907.py edit --changes reviewed-changes.json
```

See
[`work/clean_rebuild/ADAPTIVE_TRANSLATION_FORMATTING.md`](work/clean_rebuild/ADAPTIVE_TRANSLATION_FORMATTING.md)
for the formatting contract.

## Comparison and validation

Regenerate the deterministic Japanese/English review package:

```powershell
python nostalgia1907.py compare
```

Run the complete normal validation sequence:

```powershell
python nostalgia1907.py validate
```

That command performs Python static compilation, the audio companion's unit
tests, the renderer-aware audit, all script-layout tests, comparison-package
regeneration, and semantic/generated artifact validation.

## Deterministic rebuild

First inspect the resolved plan:

```powershell
python nostalgia1907.py build --name v8 --dry-run
```

The dry run reports whether the run and delivery directories are absent, empty,
or occupied. A real build will never overwrite an occupied path.

Then create two independent builds from the original Japanese tracks:

```powershell
python nostalgia1907.py build --name v8
```

Before either build begins, the tool automatically runs the complete
static/layout/comparison/semantic validation sequence. If any check fails, no
BIN/CUE build starts.

The default result is:

```text
outputs/Nostalgia1907_CleanRebuild_v8/
```

The underlying builder refuses stale non-empty run/output directories and
rejects publication unless both independently built BIN/CUE sets are
byte-identical.

## U.S.-BIOS test derivative

The region tool creates a separate derivative of the hash-locked v7 output. It
does not modify v7, translation sources, SCN data, file extents, or Track 2.

```powershell
python nostalgia1907.py build-us `
  --us-bios '<Sega CD (U) Model 2 v2.00w BIOS.bin>' `
  --dry-run

python nostalgia1907.py build-us `
  --us-bios '<Sega CD (U) Model 2 v2.00w BIOS.bin>'
```

## Optional audio review

The audio-localization companion is review-only and never patches the game.
Optional dependencies are isolated from the normal translation tool:

```powershell
python -m pip install -e '.[audio-asr]'
python -m pip install -e '.[audio-tts]'
```

See [`work/audio_localization/README.md`](work/audio_localization/README.md).

## Production boundary

The deterministic production modules are explicitly enumerated by
`work/clean_rebuild/rebuild.py`, which rejects references to legacy translated
builds. The remaining `part3c_*`, `act4_translation`, and `staff_translation`
directories are retained research history; they are not part of the production
build graph.

The repository intentionally excludes:

- original or rebuilt BIN/CUE/ISO images;
- extracted MES, SCN, font, archive, PCM, and WAV data;
- BIOS files and BIOS-derived security payloads;
- deterministic run directories and generated comparison/output packages;
- local Python runtimes, CUDA libraries, speech models, and voice models.

No playable game image is distributed by this repository.

## License and third-party materials

The original code, tools, tests, documentation, and other contributor-created
materials in this repository are licensed under the [MIT License](LICENSE).

The MIT License does **not** grant rights to the original game or to any
third-party software, story, dialogue, characters, names, logos, graphics,
music, audio, trademarks, or other copyrighted materials. Those materials
remain the property of their respective rights holders. See
[`THIRD_PARTY_NOTICE.md`](THIRD_PARTY_NOTICE.md) for the complete boundary.

This is an unofficial fan-translation and reverse-engineering project. It is
not affiliated with, authorized by, or endorsed by the original publisher or
rights holders. Users must provide their own legally obtained source files.

## Source-only development checks

The checks that do not require copyrighted retail data run locally and in
GitHub Actions:

```powershell
python -m compileall -q nostalgia1907.py work tests
python -m unittest discover -s tests -v
python work/audio_localization/test_audio_localization.py
```

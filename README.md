# Nostalgia 1907 English translation

This private repository contains the translation sources, reverse-engineering
notes, deterministic rebuild tooling, validation code, and review utilities for
the English localization of the Japanese Mega-CD game *Nostalgia 1907*.

The current validated baseline is `Nostalgia1907_CleanRebuild_v7`. It is built
from the original Japanese disc and does not restore or depend on older
translated builds. Manual playtesting is still the final release gate.

## Repository boundary

The repository intentionally excludes:

- original or rebuilt BIN/CUE/ISO images;
- extracted MES, SCN, font, archive, PCM, and WAV data;
- BIOS files and BIOS-derived security payloads;
- deterministic run directories and generated comparison/output packages;
- local Python runtimes, CUDA libraries, speech models, and voice models.

Anyone rebuilding the project must provide their own legally obtained original
Japanese Track 1 and Track 2 images. The expected local input directory is
`work/clean_rebuild/retail_input/`.

## Canonical translation

The canonical script is:

- `work/clean_rebuild/sources/index.json`
- `work/clean_rebuild/sources/<CHAPTER>.json`

Each English entry is keyed by a stable chapter and record ID. Japanese records,
IDs, ordering, control codes, branching, SCN data, and binary boundaries remain
authoritative. The global renderer-aware formatter owns general line wrapping;
chapter-specific binary layout patches are not part of the production workflow.

See
[`work/clean_rebuild/ADAPTIVE_TRANSLATION_FORMATTING.md`](work/clean_rebuild/ADAPTIVE_TRANSLATION_FORMATTING.md)
for the formatting contract.

## Validate

From the repository root:

```powershell
python work\clean_rebuild\translation_formatter.py
python work\clean_rebuild\test_script_layout.py -v
python work\clean_rebuild\translation_validation.py
```

These checks cover canonical record identity, renderer-aware layout policies,
MES and glyph limits, fixed binary boundaries, and semantic translation
requirements.

## Deterministic rebuild

Prepare the retail reference directly from the original Japanese Track 1:

```powershell
python work\clean_rebuild\prepare_retail.py `
  "work\clean_rebuild\retail_input\Nostalgia 1907 (Japan) (Track 1).bin" `
  --build-root work\clean_rebuild\retail_reference
```

Then build twice from the original Japanese tracks:

```powershell
python work\clean_rebuild\rebuild.py `
  "<original Track 1.bin>" `
  "<original Track 2.bin>" `
  --runs-root "<new empty runs directory>" `
  --delivery-root "<new empty output directory>" `
  --basename "Nostalgia1907_CleanRebuild"
```

The builder rejects the release unless both independent products are
byte-identical.

## Companion tools

- `work/region_variant/build_us_bios_test.py` creates a separate deterministic
  U.S.-BIOS testing derivative without modifying v7.
- `work/audio_localization/audio_localization.py` extracts and maps the Japanese
  dialogue for review. Its transcription and synthesized English previews are
  optional review artifacts and are never inserted into the game.

No playable game image is distributed by this repository.

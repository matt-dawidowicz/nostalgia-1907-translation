# Nostalgia 1907 U.S.-BIOS test builder

`build_us_bios_test.py` creates a separate U.S. Sega CD BIOS test derivative
of the hash-locked v7 BIN/CUE. It does not modify v7, translation sources,
archives, ISO files, SCN data, file extents, Track 2, or any older build.

The longer U.S. security program overlaps Nostalgia's Japanese bootstrap and
cannot safely replace it in place. The builder therefore:

1. derives the exact licensed U.S. security program from the verified v2.00w
   U.S. BIOS;
2. changes only the three boot-loader start/length fields required by the
   wrapper;
3. installs the 50-byte restoration loader and deterministic conversion tag;
4. relocates the original used boot payload from `0x0000:0x1884` to
   `0x0800:0x2084` byte-for-byte;
5. regenerates EDC/ECC only for changed raw sectors 0 through 4;
6. copies Track 2 exactly and writes a fixed two-track CUE;
7. performs the conversion twice and rejects any byte difference.

The original `J` country metadata at `0x1F0` is intentionally preserved. Sega
CD BIOS compatibility is supplied by the security program; changing only the
metadata byte does not convert a disc.

## Run

```powershell
$python = 'C:\Users\thema\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$root = 'C:\Users\thema\Documents\Codex\2026-07-21\in-c-users-thema-documents-codex'

& $python "$root\work\region_variant\build_us_bios_test.py" `
  "$root\outputs\Nostalgia1907_CleanRebuild_v7\Nostalgia1907_CleanRebuild_v7_Track1.bin" `
  "$root\outputs\Nostalgia1907_CleanRebuild_v7\Nostalgia1907_CleanRebuild_v7_Track2.bin" `
  'D:\Emulation\Ares\Sega CD (U) - Model 2 v2.00w (1993).bin' `
  --runs-root "$root\work\region_variant\runs_v7" `
  --delivery-root "$root\outputs\Nostalgia1907_CleanRebuild_v7_US_BIOS_Test"
```

Both the v7 Track 1 and supplied U.S. BIOS are SHA-256 guarded. The delivery
contains `final_verification.json` with the two-run proof, mutation boundaries,
raw Track 1 hash, logical ISO hash, Track 2 hash, security hash, and CUE hash.

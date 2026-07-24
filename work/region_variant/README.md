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
python nostalgia1907.py build-us `
  --us-bios '<Sega CD (U) Model 2 v2.00w BIOS.bin>'
```

Both the v7 Track 1 and supplied U.S. BIOS are SHA-256 guarded. The delivery
contains `final_verification.json` with the two-run proof, mutation boundaries,
raw Track 1 hash, logical ISO hash, Track 2 hash, security hash, and CUE hash.

Use `--dry-run` to show and verify every resolved input and output path without
writing a build. The BIOS path can instead be stored in the ignored
`nostalgia1907.local.json` file described in the root README.

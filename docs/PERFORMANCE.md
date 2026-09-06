# Performance benchmarks

This document records the benchmark basis for rebuild optimizations. Performance
changes are accepted only when they preserve the repository's deterministic and
binary-safety contracts; a faster but byte-different compressor or raw-disc
writer is not an acceptable optimization.

## Benchmark environment

The September 2, 2026 measurements were made on a Linux x86-64 runner using
Python 3.13.5, five virtual CPUs, and an AMD EPYC 9V74 host. The runner is shared,
so absolute wall times can vary with host contention. Paired baseline/optimized
ratios on the same runner are the primary comparison.

The benchmark corpus uses the exact supported Japanese retail Track 1
(192,649,968 bytes) and its extracted retail chapter MES payloads. Track 1 and
the extracted logical ISO were checked against the frozen project SHA-256
values before the corpus was used.

## LZ compressor

The compressor benchmark covers all 19 retail MES payloads, totaling 185,595
uncompressed bytes. The baseline is the previous one-byte match index plus the
full literal-length dynamic-programming scan. The optimized implementation uses
an ordered two-byte endpoint index for copy candidates and a monotonic sliding
minimum for long literal runs.

| Metric | Baseline | Optimized | Change |
| --- | ---: | ---: | ---: |
| Wall time, all 19 MES files | 19.979 s | 2.060 s | 9.70x faster |
| CPU time, all 19 MES files | 19.953 s | 2.059 s | 89.7% lower |
| Match probes | 12,927,194 | 1,235,226 | 90.4% fewer |
| Literal DP candidates | 48,337,476 | 1,669,671 | 96.5% fewer |
| Median per-file speedup | - | - | 10.28x |
| Minimum per-file speedup | - | - | 4.11x |
| Maximum per-file speedup | - | - | 12.87x |

Every one of the 19 optimized compressed payloads had the same SHA-256 as the
baseline compressor output. This is stronger than merely proving that both
streams decompress to the same bytes: the compressed representation itself is
unchanged.

A first attempted optimization that only deduplicated equivalent copy
candidates was rejected because it did not materially improve wall time. The
benchmark showed that match probing and literal-DP enumeration were the actual
cost centers.

## MODE1/2352 raw-disc processing

The original path regenerated EDC/ECC for every sector during raw Track 1
reconstruction, including sectors whose 2,048-byte logical payload was
unchanged. The optimized path may copy a complete raw sector byte-for-byte when
the caller has already authenticated the complete template Track 1 and the
logical payload is unchanged. Changed sectors still receive freshly generated
EDC/ECC.

A 4,096-sector slice of the real Track 1 was measured with the same implementation
used by the rebuild:

| Case | Baseline wall | Optimized wall | Speedup | Optimized regenerated sectors |
| --- | ---: | ---: | ---: | ---: |
| No logical changes | 2.455 s | 0.038 s | 64.5x | 0 / 4,096 |
| 128 changed sectors (3.125%) | 2.431 s | 0.113 s | 21.5x | 128 / 4,096 |

For both cases the complete optimized raw output was byte-identical to the
full-regeneration baseline, including sector checksum/parity bytes.

Retail preparation also no longer recomputes every sector's EDC/ECC after the
complete Track 1 has already matched the project's frozen SHA-256. A complete
no-parity extraction of the supported disc took 1.20 seconds in this benchmark
and produced the exact frozen logical-ISO SHA-256. A full parity-verifying
baseline attempt exceeded 90 seconds on the shared runner before completion;
therefore no extrapolated full-run baseline time is reported here.

Release regression now authenticates the complete retail reference by its
frozen SHA-256, proves unchanged output sectors by exact byte identity to that
reference, and recalculates EDC/ECC only for sectors that differ. This retains
complete output-integrity evidence while avoiding another redundant full-disc
parity pass.

### Trusted-reference regression verification

A paired 4,096-sector verification benchmark measures the full legacy
recalculation against authenticated-reference delta verification:

| Case | Baseline wall | Optimized wall | Speedup | Direct EDC/ECC checks |
| --- | ---: | ---: | ---: | ---: |
| No changed sectors | 2.436 s | 0.013 s | 181.1x | 0 / 4,096 |
| 128 changed sectors (3.125%) | 2.499 s | 0.092 s | 27.2x | 128 / 4,096 |

On the complete 81,909-sector retail Track 1, authenticated-reference
verification took 0.216 seconds when all sectors were identical and 0.242
seconds when five sectors were changed and freshly checksummed. The latter
mirrors the region-wrapper mutation count. These full-track optimized timings
include streaming SHA-256 authentication of the reference.

## Compiler micro-optimizations

`stored_cell()` remains memoized for immutable `(style, unit)` pairs. The MES
compiler now materializes each row's glyph bitmaps once and reuses that bitmap
plan for frequency ordering, first-use ordering, and final record encoding. It
also avoids tuple joins used only to count cells, duplicate retained-glyph
sorting, constant dictionary scans, and a redundant pointer-range pass.

These are low-risk reductions in repeated Python work. They are not presented
as dominant end-to-end wins because LZ compression and raw-sector parity
generation remain the principal binary-processing costs.

## September 6, 2026 follow-up efficiency pass

The follow-up pass removes repeated work that remained after the major codec and
raw-disc optimizations:

- SCN role, geometry, and row-limit inference now share one structural display
  inventory per contract build instead of independently rescanning commands.
- Long LZ copy matches are represented as intervals. A range-minimum DP query
  selects the best legal long-copy predecessor without allocating every length
  from 5 through the maximum match. Legacy-byte equivalence remains mandatory.
- The bilingual exporter caches decoded and 2x-scaled immutable glyph rasters,
  uses the native Adler-32 implementation, and reuses each retail MES digest.
- Source-health validation decodes each text source once before both hygiene and
  parser checks.
- Whole-game planning reuses canonical chapter objects inside the plan build and
  streams large CUE/Track 1 identity hashes instead of loading Track 1 whole.
- Translation auditing avoids duplicate semantic normalization, shares an
  already-parsed retail MES with renderer-contract inference, and classifies the
  final audit report in one pass.

The regression suite preserves the older compressor as a reference algorithm
and compares emitted compressed bytes, including a long repetitive corpus that
exercises the new range-minimum path.

## Investigated non-hotspots

The retail ISO contains 1,853 parsed directory entries. Re-reading the complete
entry tree took about 2.4 ms median on the benchmark runner. Streaming SHA-256
of the approximately 193 MB Track 1 and 168 MB ISO took about 0.12 seconds each.
Those operations are therefore not meaningful performance targets relative to
compression and EDC/ECC processing, and this optimization pass deliberately
leaves their verification behavior intact.

## Acceptance and release boundary

The source test suite contains explicit old-versus-new compressor and raw-sector
byte-equivalence tests. Public CI can prove source-level and synthetic binary
invariants, but it does not contain the private retail fixtures needed for the
complete release build.

Before a performance change is promoted into a release branch, the normal
retail-backed release procedure must still run: two independent clean builds,
full regression including final raw-sector validation, byte-identical artifact
comparison, and the project's runtime playtest/certification requirements.

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

The release regression still performs a complete final Track 1 EDC/ECC
verification. The optimization removes redundant work during preparation and
reconstruction; it does not remove the final output-integrity proof.

## Compiler micro-optimizations

`stored_cell()` is deterministic for an immutable `(style, unit)` pair, so its
rendered 12x12 bitmap is now memoized. The row-phase optimizer also returns
immediately when no row has an alternate phase, which is the current normal
compiler path. Tests explicitly cover both shortcuts.

These were accepted as low-risk reductions in repeated work. They are not
presented as major end-to-end wins because the retail benchmark identified LZ
compression and raw-sector parity generation as the dominant costs.

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

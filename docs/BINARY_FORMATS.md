# Binary format reference

This document describes the subset of each game/disc format that the maintained
production pipeline reads or writes. It is not a complete Mega-CD or game-opcode
specification. Executable parsers and validators remain authoritative and reject
structures outside the proven contracts below.

All numeric offsets below are hexadecimal unless stated otherwise.

## Raw Track 1: MODE1/2352

`raw_cd.py` treats Track 1 as fixed-size 2,352-byte sectors. Each raw sector
contains 2,048 bytes of ISO user data.

| Offset | Size | Meaning |
| --- | ---: | --- |
| `0x000` | 12 | Sync pattern `00 FF...FF 00` |
| `0x00C` | 3 | Absolute minute/second/frame address in BCD |
| `0x00F` | 1 | Mode byte; must be `01` |
| `0x010` | 2,048 | ISO user data |
| `0x810` | 4 | Little-endian EDC |
| `0x814` | 8 | Reserved zero bytes |
| `0x81C` | 172 | ECC P plane |
| `0x8C8` | 104 | ECC Q plane |
| `0x930` | - | End of sector |

Sector zero has absolute address `00:02:00`, reflecting the standard 150-frame
lead-in.

### Authenticated-reference reconstruction

Older documentation described the rebuild as regenerating EDC/ECC for every
output sector. That is no longer the maintained algorithm. The rebuild first
authenticates the complete retail Track 1 against its frozen SHA-256. For each
logical sector:

- if the generated 2,048-byte user payload is unchanged, the complete
  authenticated retail raw sector is copied byte-for-byte; and
- if the logical payload changed, the sector is reconstructed with the retail
  geometry/header as its template and fresh EDC/ECC is generated and checked.

Final regression uses the same evidence model: an unchanged raw sector inherits
checksum/parity evidence through exact identity to the already authenticated
retail reference; every changed sector receives direct EDC/ECC verification.
This is a performance optimization, not a relaxation of disc integrity.

Safety invariants include:

- raw and logical sector counts must match retail;
- sector sync/header/mode/address geometry is validated;
- every changed output sector has freshly verified EDC/ECC;
- every unchanged output sector must be byte-identical to its authenticated
  retail counterpart;
- the Mega-CD boot signature and guarded boot/security boundaries are checked;
- the North American wrapper may mutate only its explicitly proven raw-sector
  range; and
- Track 2 is copied exactly rather than decoded, resampled, or regenerated.

See [Performance benchmarks](PERFORMANCE.md) for the measured equivalence and
speedup of the authenticated-reference path.

## ISO 9660 fixed extents

`iso9660.py` reads the primary volume descriptor at logical sector 16 and walks
directory records recursively.

An `IsoEntry` records the normalized path, starting logical extent, logical byte
size, flags, and the absolute location of the directory record that declares the
file. ISO 9660 stores extent and size in little- and big-endian copies; the
parser requires them to agree.

The patcher never allocates a new extent. A replacement may change logical size
only when it fits the complete sector allocation occupied by the retail file:

```text
allocated_size = ceil(retail_size / 2048) * 2048
```

Before installation the allocation is zeroed, the new payload is written at the
original extent, and every duplicate directory record receives the new logical
size in both byte orders. Output ISO length must equal input ISO length.

Writers reject destructive source/output aliasing and malformed or conflicting
extent metadata before a candidate can be published.

## Chapter LZ archive

Each chapter archive such as `PART1A.LZ` contains a fixed member table followed
by member payload slots.

### Header

| Offset | Size | Endian | Meaning |
| --- | ---: | --- | --- |
| `0x00` | 2 | big | member count |
| `0x02` | 2 | big | table entry size; must be `0x001E` |

### Entry (`0x1E` bytes)

| Relative offset | Size | Meaning |
| --- | ---: | --- |
| `0x00` | 14 | NUL-terminated ASCII member name |
| `0x0E` | 4 | payload offset, big-endian |
| `0x12` | 4 | stored/compressed size, big-endian |
| `0x16` | 4 | unpacked size, big-endian |
| `0x1A` | 4 | preserved marker bytes |

When stored size equals unpacked size, the payload is uncompressed. Otherwise
the game's backward LZ codec is used.

The normal replacement strategy compresses a generated MES and writes it inside
the original member slot, zeroing unused slot bytes. If a replacement cannot
fit, guarded reflow may repack member payloads in original order, but only inside
the chapter archive's existing ISO allocation. The overflow path uses a typed
capacity failure rather than parsing an exception message, and capacity reports
identify the tightest relevant headroom.

Non-replaced members remain authoritative retail data except for the single
closed PART1A SCN correction described below.

### Backward LZ stream

The decoder works from the end of the payload toward the beginning of both the
compressed stream and output. The footer contains aligned big-endian words for
unpacked size, XOR checksum, initial bit state, and preceding stream words as
required.

Commands encode literal runs or backward-output copies with several
length/distance widths. `compress()` uses dynamic programming and deterministic
tie-breaking, then immediately round-trips through `decompress()`.

The current implementation keeps the previous compressed representation while
avoiding materialization of every legal long-copy length. A range-minimum data
structure selects the lowest-cost legal predecessor and retains the legacy
tie preference. Regression tests compare optimized output byte-for-byte with the
preserved reference algorithm, including long repetitive inputs.

For analysis, use `parse_archive()` and `member_bytes()` rather than guessed
slices.

## MES script container

MES combines a pointer table, encoded records, and a chapter-local dynamic glyph
bank.

```text
0x0000  u16be split_offset
0x0002  u16be pointer[0]
0x0004  u16be pointer[1]
...     one pointer per record
pointer[0] .. split_offset-1
        encoded record stream
split_offset .. end
        18-byte dynamic glyph bitmaps
```

The first pointer is also the end of the pointer table:

```text
record_count = (first_pointer - 2) / 2
```

Pointers are big-endian, strictly increasing, and bounded before
`split_offset`. Adjacent pointers define a nonempty record; the final record ends
at `split_offset`. Every record ends with `0x00`.

### Record codes

Values below `0xF0` are one-byte fixed-font codes or control/terminator bytes.
Values `0xF0` through `0xFF` begin a two-byte dynamic-glyph reference:

```text
index = (prefix - 0xF0) * 255 + low - 1
```

The low byte may not be zero. Preserved retail records remain semantically
byte-authoritative, although a dynamic reference may be remapped when unused
retail glyphs are compacted; regression therefore verifies their rendered token
identity as well as fixed/control bytes.

The `MAIN.BIN` lower-dialogue reader has a special row-edge lookahead for the
one-byte values `02`, `03`, `04`, `05`, `08`, and `11`. They are legitimate
fixed-font cells elsewhere, but generated lower-dialogue English must not place
them at the guarded row edge. Equivalent glyphs are emitted dynamically there.

The runtime permits at most 1,020 dynamic glyphs. MES pointers must fit 16-bit
offsets. PART3C additionally has a proven hard file boundary at `0x3FFF`.

## Font cells

Fixed and dynamic glyphs are one-bit 12x12 images stored in 18 bytes.
`font_render.py` generates English cells in display orientation and rotates them
into the storage orientation expected by the game.

A normal generated cell contains one or two six-pixel English character slots.
Reviewed punctuation clusters may use a compact bitmap when the visible text is
preserved. Apostrophes deliberately remain on the ordinary six-pixel grid so
contractions cannot switch spacing models according to pair phase.

The compiler deduplicates immutable glyph bitmaps and reuses the resulting row
bitmap plans for frequency ordering, first use, and final encoding. This does
not alter visible output; it removes repeated analysis.

A frozen shared dictionary uses otherwise-unused fixed-font slots for reviewed
English cells. Regression proves those slots are not used by preserved retail
records, that only declared cells change, and that each dictionary cell renders
identically to its dynamic equivalent. The six guarded lower-dialogue row-edge
codes above are excluded.

For `lower_dialogue`, the retail opening quote (`0x10`) occupies a one-cell
left gutter. English replaces that initial cell with the shared blank cell. The
physical contract is one initial 12-cell row followed by an 11-cell
continuation stride; later page clears do not emit a second opening gutter.
`lower_continuation` starts directly on the native continuation stride.

See [Text-box contracts](TEXT_BOX_CONTRACTS.md) for the complete renderer
catalogue.

## SCN renderer references

Retail SCN is the structural authority for renderer inference. Generated
archives preserve it byte-for-byte except for one closed, hash-locked correction
in `PART1A.SCN`: selector-window X bytes at offsets `0x065D` and `0x0666` change
from `0x17` (23) to `0x18` (24).

That aligns the transient Call/Fold selectors with the persistent Game Hall
status panel already relocated by the frozen `MAIN.BIN` patch. Ares testing
confirmed that the retail selector coordinates clipped the relocated panel's top
border. `scn_patch.py` requires exact retail/patched hashes, exact old bytes,
unchanged length, and the exact two-offset mutation set.

The parser interprets only complete, proven command shapes and valid operand
ranges. Relevant structures include:

| Shape | Inferred use |
| --- | --- |
| `0x21 <first-id> <second-id>` | speaker plus lower dialogue; zero second ID means continuation |
| adjacent `0x22` / `0x23` | location and perspective labels |
| `0x24 ... subtype text-id` | floating thought/overlay window |
| immediate `0x27 text-id` | continuation in the preceding floating window |
| `0x31 text-id ... branch` | menu choice with a valid branch target |
| `0x42` / `0x43` table targeting `0x24` | selector-driven display window |

SCN text IDs are one-based; canonical record indexes are zero-based. A record
seen through multiple windows receives the tightest valid contract. Current role,
geometry, and row-limit inference share one structural display-occurrence
inventory rather than independently rescanning the SCN.

## CUE and Track 2

The delivery CUE uses CRLF and describes Track 1 as `MODE1/2352` at index
`00:00:00`, followed by Track 2 audio with pregap index `00:00:00` and program
index `00:02:00`.

CUE and both BIN files must be in one directory. Track 2 size and SHA-256 must
match the original Japanese audio track exactly. The production pipeline never
uses decoded/resampled Track 2 audio as an intermediate.

## Format-analysis rules

When investigating an unknown:

1. begin with hash-locked retail bytes;
2. parse through the strict maintained module instead of guessed offsets;
3. separate observation from a confirmed invariant;
4. create a minimal synthetic fixture or report where possible;
5. add parser, malformed-input, round-trip, or equivalence regression coverage;
6. prove unchanged bytes outside the intended structure;
7. reject source/output aliasing and unbounded writes; and
8. never turn an historical translated build into a build input.

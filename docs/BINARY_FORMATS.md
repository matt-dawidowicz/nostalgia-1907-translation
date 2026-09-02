# Binary format reference

This document describes the subset of each format that the production pipeline
reads or writes. It is not a claim to document every Mega-CD or game opcode.
The executable code remains authoritative and rejects structures outside these
proven contracts.

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

Sector zero has the absolute address `00:02:00`, reflecting the standard
150-frame lead-in. During rebuilding, the retail raw sector is used as a
template, only the 2,048-byte user-data region is replaced, and EDC/ECC are
regenerated.

Safety invariants:

- raw and logical sector counts must match retail;
- every header, mode, and address is validated;
- every output EDC/ECC is verified;
- the Mega-CD boot signature is present;
- the first 16 sectors' boot payload matches retail;
- Track 2 is not decoded or resampled by the production build.

## ISO 9660 fixed extents

`iso9660.py` reads the primary volume descriptor at logical sector 16 and walks
directory records recursively.

An `IsoEntry` records:

- normalized path;
- starting logical extent;
- logical byte size;
- flags;
- absolute location of the directory record that declares the file.

ISO 9660 stores extent and size in both little- and big-endian copies. The
parser requires those copies to agree.

The patcher never allocates a new extent. A replacement may change logical size
only when it fits the full sector allocation already occupied by the retail
file:

```text
allocated_size = ceil(retail_size / 2048) * 2048
```

Before installation, the complete allocation is zeroed. The new payload is
written at the original extent, and every duplicate directory record receives
the new logical size in both byte orders. Output ISO length must equal input ISO
length.

## Chapter LZ archive

Each chapter file such as `PART1A.LZ` contains a fixed member table followed by
member payload slots.

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
the backward LZ codec is used.

The normal replacement strategy compresses a generated MES and writes it into
the original member slot, zeroing unused slot bytes. If it does not fit,
`replace_members_reflow` may repack all member payloads in their original order,
but only up to the chapter archive's existing ISO allocation. Non-replaced
member payload bytes, especially SCN, must remain exact.

### Backward LZ stream

The decoder works from the end of the payload toward the beginning of both the
compressed stream and output. Its footer contains three or more aligned
big-endian words:

1. unpacked size;
2. XOR checksum;
3. initial bit buffer;
4. preceding stream words as required.

Commands encode literal runs or backward-output copies with several
distance/length widths. `compress()` uses dynamic programming to choose a
minimum-bit parse with deterministic tie breaking and immediately
round-trips its result through `decompress()`.

For analysis, use `parse_archive()` and `member_bytes()` rather than slicing at
guessed offsets.

## MES script container

MES combines a pointer table, encoded records, and a chapter-local dynamic
glyph bank.

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
`split_offset`. Adjacent pointers define a nonempty record; the final record
ends at `split_offset`. Every record must end in the `0x00` terminator.

### Record codes

Values below `0xF0` are one-byte fixed-font codes or control/terminator bytes.
Values `0xF0` through `0xFF` begin a two-byte dynamic-glyph reference:

```text
index = (prefix - 0xF0) * 255 + low - 1
```

The low byte may not be zero. Generated English and preserved retail records
must end in `0x00`. Preserved retail records otherwise remain
byte-authoritative except that their dynamic references may be remapped when
unused retail glyphs are removed.

`MAIN.BIN` lower-dialogue code at `$FF1DAA-$FF1DE0` has an additional
row-edge lookahead path for the next one-byte values `02`, `03`, `04`, `05`,
`08`, and `11`. They are valid retail fixed-font values, but are not
interchangeable with arbitrary generated English cells at a full-row boundary.
Generated English must encode bitmaps assigned to those values dynamically
(`F0xx`); preserved retail bytes are not changed. A fixed and a dynamic
reference otherwise each advance the native dialogue cursor by one cell.

The runtime permits at most 1,020 dynamic glyphs. All MES pointers must fit
16-bit offsets. PART3C also has a proven hard file boundary at `0x3FFF`.

## Font cells

Both fixed and dynamic glyphs are one-bit 12x12 images stored in 18 bytes.
`font_render.py` generates English cells in display orientation and rotates
them into the storage orientation expected by the game.

A normal generated cell contains one or two six-pixel English character slots.
Selected three-character punctuation clusters, such as an ellipsis or a numeric
decimal fragment, may use a compact bitmap while preserving the same visible
text. Apostrophes deliberately remain on the ordinary six-pixel character grid
so contractions cannot switch between incompatible spacing algorithms based on
pair phase.

The MES compiler deduplicates identical bitmaps into the chapter's dynamic
glyph bank. This is why text capacity depends on unique rendered cells as well
as encoded record length.

The compiler uses one frozen, shared dictionary of reviewed English cells in
otherwise unused fixed-font slots. Every chapter may reference that dictionary;
it is a storage encoding, not a scene-specific formatting rule. Regression
checks prove the dictionary is unused by all byte-preserved retail records,
changes only its declared fixed-font cells, and produces the same bitmap
sequences as an all-dynamic encoding. The six lower-dialogue row-edge values
listed above are deliberately excluded from that dictionary. This avoids using
a visible leading blank to alter pair phase while retaining PART3C's
hard-boundary safety margin. The
lower-dialogue renderer is separate: its retail main-dialogue records normally
begin with fixed code `0x10`, a Japanese opening-quote cell drawn in the left
gutter. The English compiler replaces that one initial cell with the shared
blank fixed cell. This is the named `lower_dialogue` renderer contract: its
physical geometry is one initial 12-cell row followed by an 11-cell
continuation stride. The initial gutter uses one cell of row zero; later visual
page starts retain the continuation X-coordinate and width. No extra cell is
emitted at a page transition.
The complete contract catalogue and evidence rules are in
[`TEXT_BOX_CONTRACTS.md`](TEXT_BOX_CONTRACTS.md).


## SCN renderer references

Retail SCN remains the read-only structural authority used for renderer
inference. Generated archives preserve it byte-for-byte except for one closed,
hash-locked correction in `PART1A.SCN`: the two Call/Fold selector-window X
bytes at offsets `0x065D` and `0x0666` change from `0x17` (23) to `0x18` (24).
That aligns the transient selectors with the persistent poker status panel
already relocated by the frozen `MAIN.BIN` patch; Ares runtime testing confirmed
that the old coordinates clipped the panel's top border. `scn_patch.py` requires
the exact retail and patched hashes and proves that no other SCN byte changes.

The project otherwise reads only structurally proven command shapes needed to
relate MES records to renderers.

Relevant commands include:

| Shape | Inferred use |
| --- | --- |
| `0x21 <first-id> <second-id>` | speaker plus lower dialogue; zero second ID means continuation |
| adjacent `0x22` / `0x23` | location and perspective labels |
| `0x24 ... subtype text-id` | floating thought/overlay window |
| immediate `0x27 text-id` | continuation in the preceding floating window |
| `0x31 text-id ... branch` | menu choice with a valid target |
| `0x42` / `0x43` table targeting `0x24` | selector-driven display window |

SCN IDs are one-based. Canonical record indexes are zero-based.

Floating width bytes map to visible cell counts through the reviewed
`FLOATING_WIDTHS` table. The window Y position yields a maximum visible row
count. A record referenced by multiple windows receives the tightest valid
contract.

The parser scans for complete command shapes and valid ranges rather than
treating every matching byte as an opcode. Profile overrides exist only for
reviewed structural exceptions.

## CUE and Track 2

The delivery CUE uses CRLF and describes:

- Track 1 as `MODE1/2352`, index `00:00:00`;
- Track 2 as audio with pregap index `00:00:00` and program index `00:02:00`.

CUE and both BIN files must be in one directory. Track 2 size and SHA-256 must
match the original Japanese audio track exactly.

## Format-analysis rules

When investigating an unknown:

1. begin with hash-locked retail bytes;
2. parse through the strict module instead of guessing offsets in a hex editor;
3. separate observation from a confirmed invariant;
4. create a minimal fixture or report;
5. add a parser/round-trip regression before permitting writes;
6. prove unchanged bytes outside the intended structure;
7. never turn an historical translated build into an input.

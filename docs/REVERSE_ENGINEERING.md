# Reverse engineering notes

This document records durable runtime facts needed to maintain the translation.
It is intentionally small. One-off traces, dumps, and experiments should remain
untracked unless they establish a reusable engine rule.

## Scope

The retail game uses a 68000 executable in `MAIN.BIN`, SCN bytecode for scene
control, and MES containers for text. Static parsing is useful for structure,
but visible clearing, timing, transitions, and emulator state remain runtime
questions.

## SCN dispatcher

Retail `MAIN.BIN` contains a 128-entry SCN dispatch table beginning at
`$FF0212`. Unsupported command values fall back to the default handler near
`$FF01F0`. The retail executable implements 58 command handlers.

The interpreter reads its current SCN pointer from RAM at `$FF3CB8`, reads one
opcode byte, doubles it, indexes the signed-word dispatch table, and transfers
control to the selected handler.

Known text/window commands include:

| Opcode | Runtime role |
| --- | --- |
| `0x20` | special one-line MES text |
| `0x21` | main dialogue |
| `0x22`, `0x23` | distinct one-line label renderers |
| `0x24` | set four-byte floating-window descriptor |
| `0x27`, `0x28` | display floating text with distinct runtime modes |
| `0x30`-`0x32` | menu/choice state |
| `0x42`-`0x44` | selector-table state |

`0x21` consumes two 16-bit MES IDs followed by one additional state byte. The
state byte is stored at `$FF3DEE`; it must not be discarded by static SCN
models.

`0x24` and `0x27`/`0x28` are separate VM state transitions. The latter
commands select distinct values at `$FF465C` (`$0001` versus `$0101`).

## Lower-dialogue renderer

The lower-dialogue parser has a native row-edge lookahead path around
`$FF1DAA-$FF1DE0`. Fixed-font byte values `02`, `03`, `04`, `05`,
`08`, and `11` receive special treatment when they are the next byte after a
full physical row.

The maintained compiler therefore avoids emitting those fixed codes at that
specific boundary and uses an equivalent dynamic glyph reference instead.

The opening dialogue row and continuation rows also use different native
geometry. That rule belongs in the shared renderer/compiler contract, not in
record-specific formatting.

## Top scene-label renderer

SCN opcodes `0x22` and `0x23` share the same 12x12 MES-cell rasterizer but
DMA the resulting pattern data into separate reserved VRAM tile ranges.

- `0x22` writes tiles 2 through 33. Every retail `SCREEN0.BS` and
  `SCREEN1.BS` maps those tiles to plane columns 2 through 17 and rows 1
  through 2, a 128x16-pixel rectangle at x=16..143, y=8..23. The rasterizer
  starts two pixels inside that canvas, so text begins at x=18. The remaining
  126 pixels hold exactly 21 six-pixel English character slots.
- `0x23` writes tiles 34 through 55. The screen maps them to columns 19
  through 29 and rows 1 through 2, an 88x16-pixel rectangle at x=152..239,
  y=8..23. Text begins at x=154, leaving 86 pixels; exactly 14 complete
  six-pixel character slots fit.

The 21-character `0x22` limit is intentionally not represented as ten whole
12-pixel cells: its odd final character occupies the first six pixels of the
last cell and ends exactly at x=127 within the local 128-pixel canvas. Treating
all scene labels as the older generic 18-cell strip was therefore both too
permissive and geometrically incorrect.

## Special-line renderer

SCN opcode `0x20` stores its MES record ID at `$FF3DEA` and selects text
mode 3 at `$FF3DE8`. The common text-state machine then renders the record
into the scratch buffer at `$FF3E0C`.

The rasterizer starts each record at local x=2 and advances by 12 pixels per
MES cell. Before drawing it advances the tile-buffer pointer by eight bytes,
which is two 4bpp pixel rows, so the glyph origin is local (2, 2). The scratch
surface is 0x700 bytes = 56 Genesis tiles = a 224x16-pixel strip. Therefore one
line owns exactly 18 complete 12-pixel cells (216 pixels), leaving the expected
edge margin inside the 224-pixel surface.

The line-index byte `$FF3DFA` selects one of three VRAM destinations:

| Index | VRAM bytes | Tiles | Screen canvas | Text origin |
| --- | --- | --- | --- | --- |
| 0 | `$0700-$0DFF` | 56-111 | x=16..239, y=168..183 | (18, 170) |
| 1 | `$0E00-$14FF` | 112-167 | x=16..239, y=184..199 | (18, 186) |
| 2 | `$1500-$1BFF` | 168-223 | x=16..239, y=200..215 | (18, 202) |

Every retail `SCREEN0.BS` and `SCREEN1.BS` in all 19 chapter archives maps
those tile banks to the same plane columns 2 through 29 and row pairs 21-22,
23-24, and 25-26 respectively.

When a new line arrives with the index already at 3, the native scroll routine
copies VRAM `$0E00-$1BFF` upward to `$0700-$14FF`, clears the bottom
`$1500-$1BFF` bank, reduces the index to 2, and draws the new line there.
Opcode `0x55` selects text mode 9, which clears the complete
`$0700-$1BFF` three-strip region and resets the line index to zero. STAFF
uses that reset before each credit group, explaining why its credit pairs
occupy the first two strips. The renderer does not center text: every line
starts at x=18, and STAFF's visual centering comes from literal source padding
that is rendered like any other spaces.

This renderer is fixed-layout even though its geometry is now fully known:
leading and trailing spaces are presentation data for centered credits and
title/card composition rather than semantic prose to reflow automatically.

## Floating-window renderer

SCN opcode `0x24` copies four descriptor bytes into `$FF3D28-$FF3D2B`.
The `0x27` and `0x28` handlers parse that descriptor through the same native
window setup routine before selecting different display-state flags.

The descriptor is:

| Byte | Meaning |
| --- | --- |
| 0 | outer window X in 8-pixel tiles |
| 1 | outer window Y in 8-pixel tiles |
| 2 | outer window width in tiles |
| 3 | initial height field used by the generic window state |

MAIN.BIN computes the plane-A tilemap address as
`$C000 + 2 * (X + 64 * Y)`. For translated text, the usable horizontal
interior excludes the one-tile left/right borders. The native cell loop then
uses exactly:

`floor(((width_tiles - 2) * 8) / 12)`

MES cells per text row. This arithmetic replaces the older hand-maintained
width table, which overestimated widths 0x07, 0x08, 0x09, and 0x0C by one cell
and underestimated width 0x11 by one cell.

The first text row starts one border tile inside the window. The 12x12 glyph
rasterizer itself adds a two-pixel vertical offset, so the screen-space text
origin is `(8*X + 8, 8*Y + 10)`; later rows advance by 16 pixels.

The renderer does not preserve the descriptor's fourth byte as the final
visible height. After consuming the MES record it replaces the active height
with `2*rows + 2` tiles: one top border, two tile rows per 12-pixel text row,
and one bottom border. The corresponding screen-bottom safety bound is
`floor((28 - Y - 2) / 2)` text rows.

Both display opcodes start from the same descriptor and MES path. Their visible
difference is a high-byte mode flag at `$FF465C`:

- `0x27` uses state `$0001`. On completion it computes a point at the
  bottom-center of the final window, stores it in `$FF4670/$FF4672`, and
  enables `$FF466E`. The periodic UI routine then blinks a sprite at that
  anchor every 30 ticks.
- `0x28` uses state `$0101`. It skips that bottom-center indicator setup;
  the window body and text geometry are otherwise shared.

The indicator coordinates before the Mega Drive sprite +128 bias are
`X*8 + width*4 - 4` and `(Y + final_height - 1)*8`.

## Window and renderer state

Important state observed during executable analysis includes:

- `$FF3D28-$FF3D2F`: floating-window descriptor/state;
- `$FF3DE8-$FF3DEE`: dialogue/text state;
- `$FF465C/$FF465E`: floating-text mode and MES record;
- `$FF3CB8`: current SCN instruction pointer.

These addresses are debugging landmarks, not a license to patch RAM or
`MAIN.BIN` speculatively.

## PART3C to PART4A investigation

The reported post-1.0.2 black-screen defect at the end of Action 3 is tracked as
a runtime investigation, not as a proven translation defect.

Static analysis established:

- all observed PART3C ending routes converge before the final transition;
- temporary background/FSD allocations are released before the chapter change;
- the historical 1.0.2 English PART3C MES is larger than retail but remains
  structurally valid;
- no simple `0x3FFF` mask was found in the normal MES lookup paths; and
- English can execute additional native dialogue page-clear/reveal cycles even
  when SCN bytes are unchanged, because translated records occupy more rows.

One notable example is PART3C:218, which occupies two dialogue pages in the
historical English build versus one in retail Japanese.

### Exact transition command sequence

Retail PART3C ends with:

`55 5A 01 10 "part4a" 00`

These are three distinct VM operations, not one filename-bearing `0x5A`
command:

1. `0x55` selects the proven text-clear/reset mode;
2. `0x5A 01` is a flag operation. The handler at `$FF0A2C` reads the
   operand, adds four, and executes a dynamic `BSET` against `$FF4DC0`;
   operand `01` therefore sets bit 5;
3. `0x10 "part4a" 00` performs the actual chapter/archive switch.

The `0x10` handler at `$FF039E` passes the inline basename to the chapter
loader beginning at approximately `$FF0B7E`. The loader:

1. copies the basename into the shared filename buffer at `$FF3D18`;
2. appends `.LZ` and loads the new chapter archive;
3. appends `.SCN`, resolves that member from the new archive, and stores the
   resulting pointer in both `$FF3CB4` and `$FF3CB8`;
4. appends `.MES`, resolves that member, stores its base at `$FF3E08`, then
   derives and stores the MES data/table pointer at `$FF3E04`; and
5. reinitializes the active script-side pointer state before returning to the
   VM dispatcher.

This is direct executable evidence that PART4A begins with newly installed SCN
and MES sources rather than continuing to execute PART3C's text/script buffers.

This weakens a simple persistent-text-state explanation for the black screen:
the chapter switch replaces the script/text data sources after an explicit
`0x55` clear.

### Text-idle gate and resource-allocation invariants

The transition tail is not unique to PART3C. Retail SCN contains the exact
`55 5A 01 10 <next-chapter>` sequence at eight chapter boundaries:
PART1B, PART1C, PART1D, PART2A, PART2B, PART2D, PART3C, and PART4A. This makes
the PART3C tail itself ordinary engine behavior and moves suspicion toward the
state entering that sequence.

The `0x55` handler is also more specific than a synchronous "clear" label
suggests. It first checks the combined lower-text / window-indicator activity
state through the helper at approximately `$FF0314`. When those systems are
idle, it selects lower-text state 9 at `$FF3DE8`. The text state machine then
runs the native clear/reset path around `$FF1D3E-$FF1D88`, which clears the
three lower-screen text strips and resets the active lower-text mode plus its
line/page cursor fields. It is therefore an engine state transition, not a
direct bulk-RAM zero.

Resource commands use the related gate around `$FF0322` before beginning
their work. In particular, both `0x52` (background) and `0x71` (FSD/PSD)
wait for the text systems to be idle and for the sub-CPU resource interface to
be ready before continuing. This substantially weakens a simple race in which
longer English dialogue overlaps an already-running background load.

Word-RAM resource accounting has a separate rollback mechanism:

- `0x5D` clears the four tracked resource pointers at
  `$FF3CBC/$FF3CC0/$FF3CC4/$FF3CC8`;
- it restores the live Word-RAM allocation counter at `$00200000` from the
  chapter baseline saved at `$FF3D12`;
- the chapter loader itself snapshots the current allocation counter into
  `$FF3D12` for the newly loaded chapter.

PART3C does not execute `0x5D` immediately before PART4A. That is legal and
not unique: several successful retail transitions also omit it.

More importantly, the chapter loader has a two-level allocation baseline. At
entry around `$FF0B7E` it first restores the live Word-RAM allocation counter
at `$00200000` from the lower/global baseline at `$FF3D10`. Only after the
new chapter archive and its SCN/MES members are installed does it snapshot the
new live count into the chapter-local baseline at `$FF3D12`. The `0x5D`
rollback restores to `$FF3D12`, not `$FF3D10`.

Therefore an ordinary unbalanced temporary PART3C allocation cannot simply
become PART4A's baseline: the `0x10` chapter switch discards that excess by
restoring `$FF3D10` before loading PART4A.

The high-value PART3C resource paths inspected statically are also balanced in
their normal success paths:

- `0x52` executes resource extraction, BG processing, VDP transfer, and then
  the allocation pop at `$FF1834`;
- `0x71` performs its FSD extraction/processing and then the same allocation
  pop before continuing with the PSD-side resource command;
- retained foreground/resource commands such as PART3C's `0x50 "sea.fg"`
  can intentionally keep an allocation live, but the later `0x5D` in that
  sequence rolls those retained pointers and the chapter-local allocation
  count back before the final scene sequence.

This substantially weakens Word-RAM allocation leakage as the cause of the
reported end-of-Action-3 black screen. A runtime reproduction should still
capture both `$FF3D10` and `$FF3D12` together with `$00200000` so an
abnormal loader/error path can be distinguished from normal rollback.

### Late PART3C background and Word-RAM audit

The reported symptom did not include a screenshot, save state, emulator build,
or exact trigger. Therefore "the end of the third act" cannot be assumed to
mean the PART3C -> PART4A loader boundary. The late PART3C display sequence was
also audited directly: `128.BG`, `129.BG`, `130.BG`, and
`130A.BG`.

The normal `0x52` background path establishes a strict VRAM separation from
the text renderers:

- BG header bytes 2 and 3 are the width and height in 8x8 tiles;
- all of `128.BG`, `129.BG`, `130.BG`, `130A.BG`, and PART4A's
  `131.BG` are 24x16 tiles and unpack to 12,304 bytes;
- the 16-byte header is skipped and exactly 384 * 32 = `0x3000` bytes of
  tile patterns are transferred to VRAM `$3000-$5FFF`;
- the BG tile map is written in the plane region beginning at VRAM `$E000`
  with a 64-tile row stride; and
- header bytes 4-15 are six Genesis color words copied to the CRAM shadow at
  `$FFFBF4`, then the palette-dirty flag at `$FFFE29` is asserted.

The five late BG headers are byte-identical:

`00 00 18 10 00 E0 0E 0E 00 0E 06 66 08 88 0C CC`

Thus those scenes share placement, dimensions, and palette metadata as well as
the same native display path. The exact header is also a common retail BG
format, not a late-game special case.

The translated fixed font cannot directly overwrite this background state.
`FIX_CODE.FNT` is loaded into Word RAM and its pointer is stored at
`$FF3E00`. The glyph rasterizer selects either that fixed-font pointer or the
MES dynamic-font pointer at `$FF3E04`, indexes 18-byte glyph cells, and draws
them into the text scratch surface at `$FF3E0C`. The complete font file is
not DMA-loaded into the BG pattern or BG name-table regions. The established
lower-text VRAM strips at `$0700-$1BFF` are also disjoint from BG pattern
VRAM `$3000-$5FFF`.

The sub-CPU command-3 member extractor was traced as well. It resolves the
member table entry, reads the entry's unpacked-size field at +`0x16`, passes
that exact size to the Word-RAM allocator, then copies/decompresses into the
result. Allocations are rounded upward to eight bytes. The allocator begins at
Word-RAM offset `$0100`; the first `$100` bytes hold allocator metadata.
Consequently the historical English PART3C MES is allocated at its actual
larger unpacked size rather than inside a retail-sized buffer.

A complete PART3C allocation high-water audit includes the persistent fixed
font, PART3C SCN and MES, retained `0x40/0x41` KAS/QES resources, retained
`0x50` foregrounds, temporary `0x52` BG resources, `0x71` FSD work,
and every `0x5D` rollback. The worst cases are the early 114/116 KAS+QES
pairs, not the late backgrounds.

| Build/state | Word-RAM high-water | Headroom to `$40000` |
| --- | ---: | ---: |
| Retail PART3C maximum | `$24B38` (150,328) | 111,816 bytes |
| Historical 1.0.2 PART3C maximum | `$25050` (151,632) | 110,512 bytes |
| Historical 1.0.2 late-BG peak | `$09080` (36,992) | 225,152 bytes |

The historical MES expansion moves the allocation baseline by only `$518`
(1,304 bytes). It therefore cannot explain the reported late black graphics
through Word-RAM exhaustion, allocator wrapping, or a retail-sized MES
allocation.

No late SCN palette-write command occurs between the audited `0x52` loads and
their dialogue/label/audio sequences, so the ordinary script path also does not
immediately overwrite the six BG palette words after installation.

### First PART4A resource boundary

PART4A begins by reinitializing screen state, then requests:

- `0x71 "inbou3"`: load the `INBOU3.FSD/.PSD` resource pair;
- `0x52 "131.bg"`: load the first PART4A background.

`INBOU3.FSD/.PSD` also exist in PART3C. By contrast, `131.BG` is unique to
PART4A. Therefore a stale or malformed chapter-archive switch can appear to
survive the first resource request and fail only when `131.BG` is resolved.
That makes the `131.BG` lookup/display boundary the first high-value runtime
breakpoint for the black-screen investigation.

The current clean rebuild also reduces structural archive risk: it attempts
fixed-slot MES replacement first, preserving member offsets and total archive
size. Guarded reflow is permitted only on typed slot overflow and still
preserves member names/order while remaining inside the original ISO allocation.

### Runtime breakpoint map

The retail executable provides a compact breakpoint set for a differential
trace. Addresses below are MAIN.BIN absolute 68000 addresses with the retail
load base at `$FF0000`.

| Address | Purpose |
| --- | --- |
| `$FF039E` | SCN opcode `0x10` handler; entry to chapter-switch command |
| `$FF0B7E` | chapter-loader entry |
| `$FF0B30` | copy inline SCN filename/basename into `$FF3D18` |
| `$FF0C16` | append/copy extension text used by loader/resource paths |
| `$FF07B0` | SCN opcode `0x52` background handler |
| `$FF0A7E` | SCN opcode `0x71` FSD/PSD handler |
| `$FF184A` | sub-CPU command-3 resource extraction request |
| `$FF1858` | shared sub-CPU completion/result path |
| `$FF1834` | Word-RAM allocation pop (`SUBQ.W #1,$00200000`) |
| `$FF2CB8` | BG-processing setup reached by `0x52` |
| `$FF298E` | BG/VDP setup path reached by `0x52` |
| `$FF330E` | final VDP/DMA-related transfer path reached by `0x52` |

For the PART3C -> PART4A transition, capture at minimum:

- `$FF3CB4/$FF3CB8`: newly installed SCN base/current pointer;
- `$FF3E08/$FF3E04`: newly installed MES base/data pointer;
- `$FF3D18`: current resource filename buffer;
- `$00200000`: Word-RAM allocation count;
- `$FF3DE8-$FF3DEE`: lower-text state;
- `$FF465C/$FF465E`: floating-text state;
- VDP register state and the relevant plane/name-table VRAM around the first
  `131.BG` transfer.

A one-pass differential trace should classify the failure as follows:

1. **loader failure**: PART4A SCN/MES pointers differ or remain PART3C-owned
   immediately after `$FF0B7E` returns;
2. **archive lookup/extraction failure**: the filename buffer reaches
   `131.bg` but the command-3 resource path does not return a valid payload;
3. **BG decode/transfer failure**: extraction succeeds but execution diverges
   in the `$FF2CB8/$FF298E/$FF330E` processing chain;
4. **display-state failure**: the BG transfer completes identically but VDP
   plane-enable/name-table state differs afterward.

The next useful experiment is therefore a differential runtime trace between
retail and the exact affected English candidate at:

1. completion of PART3C's final `0x55`;
2. entry and return of `$FF039E -> $FF0B7E` for `0x10 "part4a"`;
3. verification of the new SCN/MES pointers;
4. PART4A's `$FF0A7E` `0x71 "inbou3"` resource path; and
5. the first unique PART4A `$FF07B0` `0x52 "131.bg"` path through
   extraction, BG processing, and VDP transfer.

Do not add a workaround until that trace identifies the failing subsystem.

### Ares v148 runtime control trace

A controlled retail-derived fast-path disc was executed under Ares v148 using
the original Japanese two-track disc layout and Japanese Mega-CD BIOS. The
diagnostic build changes only the START/PART3C SCN flow needed to reach the
transition immediately:

`START -> PART3C -> 55 -> 5A 01 -> 10 "part4a"`

The chapter archives retain their retail member ordering, offsets, and resource
payloads outside those diagnostic SCN bytes. This is a control experiment for
the native transition path, not a reproduction of the historical English
runtime state.

Runtime result:

- the diagnostic disc passes Mega-CD boot/security and enters the game;
- the transition visibly reaches the `ACTION4` title;
- PART4A proceeds beyond the title and displays its first room/background;
- therefore the controlled transition successfully completes the chapter
  switch, PART4A archive lookup, `INBOU3` setup, unique `131.BG` lookup,
  background processing, and initial display path.

A masked Mega Drive CPU instruction trace independently hit the expected native
routines during the run:

- `$FF039E` — opcode `0x10` handler;
- `$FF0B7E` — chapter-loader entry;
- `$FF0B30` — filename buffer setup;
- `$FF0C16` — extension helper;
- `$FF0A7E` — opcode `0x71` resource handler;
- `$FF07B0` — opcode `0x52` background handler;
- `$FF184A/$FF1858` — resource extraction request/result path;
- `$FF1834` — Word-RAM allocation pop;
- `$FF2CB8/$FF298E/$FF330E` — background processing and VDP-transfer chain.

Because the instruction tracer was address-masked, a routine that executes
multiple times is logged only on its first execution. The visual PART4A result
is therefore the decisive evidence that the second chapter switch and first
PART4A-only background path completed; individual first-hit trace lines are not
used to claim which invocation they represent.

This control result falsifies a broad failure of the generic `0x10` loader or
`131.BG` path. It does **not** reproduce the reported 1.0.2 black screen,
because it intentionally omits the complete preceding English PART3C dialogue,
page-clear, timing, and VDP history. The highest-value remaining experiment is
the same trace against the exact historical English candidate (or a byte-exact
reconstruction of its late PART3C state).

## Maintenance rule

Promote a reverse-engineering discovery only when it produces a reusable rule:

1. record the executable/SCN evidence;
2. express the rule in an existing parser, renderer, or build module;
3. add the smallest regression coverage needed;
4. run affected retail-backed validation; and
5. require runtime evidence for visible behavior.

Temporary disassemblers, traces, save states, screenshots, and exploratory
scripts do not become permanent project infrastructure merely because they were
useful during discovery.

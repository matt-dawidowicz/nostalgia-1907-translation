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

## Generic 0x28 narration and caption paths

Two records previously carried reviewed geometry overrides because their
presentation looked unlike ordinary floating dialogue. Retail SCN and MAIN.BIN
show that both are normal `0x24` descriptor + `0x28` display paths.

- START:000 is encoded as `24 03 0D 1A 08 28 00 01`. Its descriptor is
  `X=3, Y=13, width=26, initial-height=8`. The common formula gives text
  origin `(32, 114)`, 16 native 12-pixel cells per row (32 English character
  slots), and a six-row screen bound.
- PART2A:093 is encoded as `24 10 10 0E 0C 28 00 5E`. Its descriptor is
  `X=16, Y=16, width=14, initial-height=12`. The same formula gives origin
  `(136, 138)`, eight cells per row (16 English character slots), and a
  five-row screen bound.

The apparent full-screen narration and lower-caption presentations therefore do
not identify separate text engines. START retains a semantic `narration` role
for editing/review purposes, but geometry comes entirely from the generic
floating-window renderer. PART2A:093 likewise uses ordinary `0x28` overlay
geometry.

A complete scan of retail visible-text descriptors finds widths from `0x05`
through `0x1A`. MAIN.BIN applies the same border/pixel/cell arithmetic rather
than selecting from a width-specific dispatch table, so the maintained derived
width map covers that complete observed range.

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
- the common transition sequence is also used successfully by other chapters;
- temporary background/FSD allocations are released, and chapter loading resets
  the relevant allocation stack;
- the historical 1.0.2 English PART3C MES is larger than retail but remains
  structurally valid;
- no simple `0x3FFF` mask was found in the normal MES lookup paths; and
- English can execute additional native dialogue page-clear/reveal cycles even
  when SCN bytes are unchanged, because translated records occupy more rows.

One notable example is PART3C:218, which occupies two dialogue pages in the
historical English build versus one in retail Japanese.

The next useful experiment is a differential runtime trace between retail and
the exact affected English candidate around the final PART3C renderer activity,
the last background loads, the `part4a` chapter load, and the first PART4A
background initialization.

Do not add a workaround until such evidence identifies the failing subsystem.

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

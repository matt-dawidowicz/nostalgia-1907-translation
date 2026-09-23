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

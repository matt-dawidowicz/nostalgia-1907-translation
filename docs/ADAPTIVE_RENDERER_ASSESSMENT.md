# Adaptive renderer assessment

## Historical status

This is a historical engineering assessment of the lower-dialogue defects that
led to the maintained parser-safe encoding and continuation-width contracts. It
must not be read as a statement that current source still exhibits the captured
failures.

The hash-identified 1.0.2 North American reference later completed the recorded
full maintainer Ares playthrough with no reported defects. The maintained
post-1.0.2 source line subsequently accumulated translation, renderer, Game
Hall, fixed-layout, STAFF, and production changes and therefore still needs its
own final candidate-bound runtime certification. See
[Current project status](CURRENT_STATUS.md) and [Release policy](RELEASE.md).

## Defects established by the original runtime investigation

Earlier width-only assumptions for ordinary lower dialogue were rejected by
completed Ares pages, not by transient typewriter frames. Examples included
words split across a completed page such as `sh` / `ow`, `Neithe` / `r`, and
`re` / `veal`, with the down-arrow already visible.

Two distinct renderer facts emerged:

1. the lower-dialogue reader has a parser-sensitive one-byte lookahead at a
   physical row edge; and
2. after the opening row, page clear/reveal does not restore the wider opening
   X coordinate. Later rows continue on the native 11-cell stride.

Those facts replaced screenshot-specific rewraps with a shared renderer
contract.

## Encoding model

`mes_compiler.py` transforms canonical semantic English into visible 12-pixel
cells and then into a mixture of fixed one-byte codes and dynamic `F0xx`
references. Adaptive MES records contain no explicit line/page token. The native
renderer establishes row/page behavior while decoding the stream.

Static 68000 analysis of the maintenance-reference-equivalent `MAIN.BIN`
identified the lower-dialogue reader at `$FF1D64`. Both fixed and dynamic glyph
forms advance the same 12-pixel cell cursor. `00` terminates the record.

The opening row begins at X=`$4A`; continuation rows begin at X=`$56`. Retail
code `0x10` is the Japanese opening-quote cell in that one-cell gutter. The
English compiler replaces that first cell with the shared blank fixed cell.

At the full-row path near `$FF1DAA-$FF1DE0`, the reader gives the next one-byte
values `02`, `03`, `04`, `05`, `08`, and `11` special treatment. Those values
were once assigned to common generated English cells. A failing prototype put
fixed `05` at the protected boundary, matching the observed stale/split glyph
behavior.

## Maintained remedy

The selected remedy is shared and data-safe:

- exclude the six protected values from generated fixed-font compression at a
  lower-dialogue row edge, using an equivalent dynamic glyph instead;
- treat opening-row width and continuation width as distinct properties;
- emit the opening gutter once per lower-dialogue stream;
- use one initial 12-cell physical row followed by the native 11-cell
  continuation stride; and
- do not widen later page starts without new runtime evidence.

`lower_continuation` begins directly on the continuation stride and does not
receive the opening gutter.

Apostrophe handling was later simplified further: contractions remain on the
ordinary six-pixel character grid instead of switching to a phase-dependent
compact representation. That later runtime-driven fix is part of the maintained
successor line and is covered by regression tests.

## Whole-game compiler proof

The original investigation discussed a then-current count of adaptive records.
That exact count was a snapshot and is not a durable project invariant. Current
validation instead derives the adaptive/fixed inventory from canonical source
and checks the complete translated corpus every run.

For each adaptive record, the emitted-byte gate decodes the compiled MES back to
native logical cells and verifies:

- physical row cadence;
- one-time opening gutter behavior;
- whole-token/word boundaries;
- protected row-edge bytes;
- row/geometry limits; and
- storage-to-logical-cell consistency.

Fixed-layout records are separately retained in the permanent release gate.
Static proof remains intentionally narrower than emulator proof: it cannot by
itself establish live clears, transitions, timing, branch state, or save/reload
behavior.

## Native-trace status

No native trace is pending to justify the maintained 1.0.2 renderer reference;
that exact artifact already has its recorded Ares playthrough. A deeper trace is
only needed if future runtime evidence contradicts the maintained shared
contract or if an executable renderer replacement is proposed.

A historical attempt to use the Ares v147 TCP listener on `127.0.0.1:9123`
reset ordinary GDB remote packets for the Mega-CD session, so no live-PC claim
was made from that experiment. Any future native trace should use a working Ares
instruction trace or another proven 68000 debugging route.

## Rejected / reserve redesigns

### Width-only or record-specific rewraps

Rejected. They treat symptoms as per-record layout rather than modeling the
native parser and continuation state.

### Shared adaptive renderer shim

Still only a reserve design if future candidate-bound runtime evidence disproves
the selected native-encoding contract. It would require a narrow live trace,
executable patch safety proof, binary-capacity proof, and full regression/runtime
certification before implementation.

### Uniform all-dynamic token encoding

Historical capacity experiments exceeded the PART3C hard boundary, so this is
not a publishable replacement without separately proven relocation or renderer
work. It remains diagnostic evidence rather than a roadmap item.

## Decision gate

Do not reopen this problem because an old screenshot or dated report contains a
failed prototype. Change the renderer only when current candidate-bound evidence
reproduces a defect against the exact current source. Any correction must remain
general, regression-tested, retail-backed, deterministic, and Ares-certified.

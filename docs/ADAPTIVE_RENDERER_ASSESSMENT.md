# Adaptive renderer assessment

## Status

This is a historical engineering assessment. It documents the runtime defects
that led to the shared parser-safe encoding and continuation-width correction;
it is not evidence that the current source release still exhibits those
defects. The hash-identified North American reference later completed the
recorded full maintainer Ares playtest with no reported defects. The later
2026-08-27 translation revision changes playable bytes and does not inherit that
runtime result. See [release policy](RELEASE.md) for the exact reference and
[the revision record](TRANSLATION_REVISION_20260827.md) for current source
status.

Do not publish a new dialogue-layout candidate from a width-only change. Ares
playback rejected the earlier assumptions for ordinary lower dialogue:

- `12/11/11` compiler rows produce stable completed pages containing
  `... you    sh` followed by `ow ...`.
- flat 12-cell compiler rows still produce completed-page splits such as
  `one mor` followed by `e round?`.

The down-arrow was visible in the captures. These are not typewriter-animation
frames.

The parser-safe prototype removed the fixed-byte edge corruption (`o`/`e`),
but completed Ares pages still split `Neithe`/`r`, `si`/`x`, and `re`/`veal`.
Those pages prove a second global contract: after row zero, a three-line page
clear does not restore the wider opening X-coordinate or width.

## What the current compiler actually writes

`mes_compiler.py` performs the following transformation:

```text
canonical semantic English
  -> word-wrapped two-character 12px cells
  -> a mixture of one-byte fixed-font codes and two-byte F0xx dynamic codes
  -> concatenated MES record ending in 00
```

There is no explicit line or page token in an adaptive MES record. The native
renderer must infer every displayed boundary while walking this mixed-width
token stream.

Runtime-test records illustrate why a visual-cell-only model is insufficient:

| Record | Candidate | Visual cells | Encoded data bytes | Result |
| --- | --- | ---: | ---: | --- |
| `PART1A:003` | flat-12 prototype | 36 | 46 | completed page splits `more` |
| `PART1A:010` | flat-12 prototype | 96 | 117 | completed page splits `one`, `show` |
| `PART1A:010` | maintenance-cadence prototypes | 102 | 122 | completed page splits `show`/`ow` |

## Native decoder evidence

Static 68000 disassembly of the maintenance-reference-equivalent `MAIN.BIN` identifies the
lower-dialogue cell reader at `$FF1D64`. It reads one fixed byte or, for an
`F0-FF` prefix, consumes the following byte too. Both forms then call the same
glyph writer and advance the cursor by 12 pixels: they are one decoded display
cell, not one raw byte. `00` ends the record.

The same routine starts the opening row at X=`$4A` and continuation rows at
X=`$56`; the retail leading `10` is the opening-quote cell occupying the
one-cell gutter. Its full-row path at `$FF1DAA-$FF1DE0` peeks at the next byte
and gives `02`, `03`, `04`, `05`, `08`, and `11` special treatment. Those
values are therefore parser-reserved at a lower-dialogue row edge even though
they are ordinary fixed-font slots elsewhere.

The old shared English dictionary assigned those exact values to common cells
such as `on`, `,`, and leading-space pairs. In the failing maintenance-cadence
`PART1A:010` prototype, the first twelve decoded cells are followed by fixed `05` (`on`).
That is the native special path, matching the captured `o` at the right edge
followed by `e` on the next row. This establishes a renderer-wide encoding
contract defect; it is not stale translation wording or an animation frame.

The replacement is data-safe and shared: exclude those six values from
generated fixed-font compression and emit their identical glyphs as dynamic
`F0xx` cells. A no-output compile of all 19 chapters passed with that rule;
`PART3C` is 16,094 bytes, still 289 bytes below its `0x3FFF` boundary. Japanese
records, SCN, IDs, order, English prose, and executable bytes remain unchanged.

The parser-safe prototype captures also establish that `page_rows=3` is vertical state only for
`lower_dialogue`: it clears/reveals a new page but leaves the native reader at
the 11-cell continuation X-coordinate. The compiler now represents page cadence
and first-row repetition as separate properties. `lower_dialogue` and
`lower_continuation` use one initial row and 11-cell continuations thereafter;
no later page is widened without separate runtime proof.

## Whole-game compiler proof

The current source gate applies both contracts to the complete corpus without
requiring a screenshot for each record. It first audits all 2,759 adaptive
records for source-word boundaries and complete layout ownership. It then
compiles all 19 chapters in memory and decodes the resulting MES records into
the same logical cells the lower-dialogue routine reads. The emitted-byte audit
checks 12/11 physical cadence, the one-time gutter, every row-edge byte, and
the equivalence of storage length to logical-cell count. A deliberate test that
restores fixed byte `05` for `on` fails at `PART1A:010` before a build begins.

This eliminates per-line screenshot repair. It is not a claim that static work
can prove every live state. The recorded reference later completed the required
maintainer playtest; any candidate with changed playable bytes must again cover
one route for each text-box type, page clearing, dialogue transitions, and
save/load.

## Remaining native trace

No native trace is pending for the historical 1.0.2 runtime reference. The
post-1.0.2 translation revision has separate candidate-bound runtime work
pending before release. Before changing
executable renderer code or publishing a different candidate, establish the
items below from `MAIN.BIN` or a working GDB trace:

1. The routine and state that perform page advance/clear, and whether it
   restarts a record pointer or continues a flat stream.
2. The safe code/data range and call contract for any executable replacement.

The Ares v147 TCP listener accepts a connection on `127.0.0.1:9123` but resets
standard GDB remote-protocol packets for this Mega-CD session. It is therefore
not a usable Mega-CD CPU debugger in this configuration; no live-PC claim has
been made. The runtime probe must use Ares instruction tracing or an external
68000 debugger, while static work begins with `MAIN.BIN`.

## Redesign options

### 1. Native parser-safe encoding

Retain the stock renderer, prohibit the six parser-reserved fixed bytes in
generated English, and distinguish a vertical page clear from a horizontal
first-row reset. This selected shared remedy changes only compiler contracts,
retains the native renderer, and fits all chapters in the proven binary bounds.

### 2. Shared adaptive renderer shim

Replace the lower-dialogue parser entry point in `MAIN.BIN` with one shared
routine. It would decode a documented English token stream, count visual
six-pixel slots, wrap only at permitted word boundaries, and preserve the
stock speaker/window/page behavior. All chapters would use this one contract;
SCN, record IDs/order, Japanese preserved records, and binary extents would
remain untouched unless a separately proven relocation is required.

This remains a future option only if a new, candidate-bound Ares test disproves
the selected encoder contract. It requires a narrow live trace and
executable-patch safety proof before implementation.

### 3. Uniform-token encoding

Encode every generated cell using one representation rather than the current
fixed/dynamic mixture. A read-only all-dynamic capacity experiment exceeds the
hard `PART3C` limit (`0x5A1C > 0x3FFF`), so this is not publishable without a
separately proven relocation or renderer change. It remains a diagnostic, not
a candidate solution.

## Decision gate

No record-specific rewraps or chapter-specific patches are authorized. If a
future defect justifies a renderer change, rebuild cleanly with the shared
parser-safe and continuation-width contracts, then replay the affected Ares
pages and transitions against that candidate's exact hash.

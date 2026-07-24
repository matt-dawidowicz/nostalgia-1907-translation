# PART3C runtime guards

Run `run_transitionfix10_static_checks.ps1` after any future PART3C text,
font, SCN, LZ, ISO, or disc-image change. The verifier fails hard unless all
of these contracts remain true:

- `PART3C.MES` has 224 strictly increasing pointers, 224 final terminators,
  an 18-byte-aligned fully referenced dynamic tail, size at most `0x3FFF`,
  and text split at most `0x2600`.
- Records 112-123 and 163-223 remain byte-identical to the reviewed complete
  translation source.
- Every intentionally reflowed row preserves exact prose, control bytes,
  cell count, row width, and generated bitmap sequence.
- Record 159 begins with the proven retail `01 01` blank padding and retains
  the translated `Captain Room` suffix byte-for-byte.
- Records 160-163 are exactly 32 cells each. Record 162 is four rows by eight
  cells, preserves its complete sentence, and does not cross the early `F1`
  low-byte boundary.
- `PART3C.SCN`, including the chained commands at `0x0B13`, is byte-identical
  to retail. The record-162 window operand must remain `0x0E`.
- The fixed font is unchanged. Only the ten reviewed one-use dynamic slots may
  change, all ten must be referenced only by record 162, and every one of the
  400 tail slots must remain referenced.
- The 52-member LZ name/order/offset layout and total byte length match retail.
  SCREEN0, SCREEN1, 120.BG, 121.BG, and 122.BG remain byte-identical to retail.
- Only `PART3C.LZ` changes in the ISO; all 82,169 Mode-1 user-data sectors must
  reproduce the ISO, the Sega CD boot system must match the supplied retail
  BIN, Track 2 must remain byte-identical, and the CUE must retain CRLF and the
  two-track MODE1/2352 + AUDIO layout.
- The 564-file/21-MES static regression inventory parses cleanly and all 12
  tooling unit tests pass.

These checks prevent the exact regression that caused the blackout: removing
the title padding, widening the chained window, overfilling record 162,
crossing the guarded dynamic-token boundary early, moving background members,
or silently exceeding the MES runtime ceiling.

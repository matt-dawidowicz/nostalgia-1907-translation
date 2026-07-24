# Track 1 dialogue-audio findings

## Locked inputs

- Verified `retail.iso`: 167,749,632 bytes, SHA-256
  `7944AF20FD802A43BEFBFA97734993EB63A3803F76D4AFBCEF315E41D4459ECC`.
- Original Japanese Track 1 BIN: 192,649,968 bytes, SHA-256
  `EFE9A453849F52DC72B7E72EE98D8644882655536E59991C2C85C5A35A41D0E5`.
- The ISO has 1,828 `.PCM` files totaling 161,939,978 bytes:
  `0000.PCM` through `1823.PCM`, plus `0014A.PCM`, `0014B.PCM`,
  `0671A.PCM`, and the explosion effect `BAKUHATU.PCM`.

Track 2 is Red Book CD audio (music), not the container for spoken dialogue.

## Codec

The `.PCM` assets are headerless RF5C164 8-bit sign-magnitude mono samples.

- `00` is silence/zero.
- `01` through `7F` are positive magnitudes.
- `81` through `FF` are negative magnitudes (`byte & 0x7F`).
- `80` is the alternate negative-zero representation.

For review WAVs, each signed magnitude is shifted left eight bits and written
as little-endian PCM16. No filtering, silence trimming, gain change, or sample
insertion occurs.

## Playback rate

The retail executable's PCM initialization routine begins near ISO file offset
`0x1252`. Its relevant writes are:

```text
move.b #$ff, $3(a5)   ; pan
move.b #$ff, $1(a5)   ; envelope
move.b #$04, $7(a5)   ; FD high byte
move.b #$00, $5(a5)   ; FD low byte
```

The RF5C164 native clock is `12,500,000 / 384` Hz, and frequency delta
`0x0800` is unity. The game's `0x0400` delta is half-speed:

```text
(12,500,000 / 384) * (0x0400 / 0x0800)
= 16,276.041666... Hz
```

Because a WAV header requires an integer rate, the review files use 16,276 Hz.
Their PCM payload has exactly one output sample per retail source byte.

- Retail source bitrate: approximately 130,208 bps.
- Decoded WAV bitrate: 260,416 bps.

## SCN mapping

An SCN audio command is `0x72` (`r`) followed by the ISO filename without that
leading `r`, for example `r0001.pcm\0`.

- `0x21 <speaker-id> <dialogue-id>` maps ordinary voiced dialogue.
- `0x21 <continuation-id> 0000` maps a continuation.
- Valid `0x24` floating-window commands cover narration such as `0000.PCM`.
- Speakerless `0x20 <record-id>` spans cover the closing PART4C exchange.
  Several consecutive records can belong to one long voice asset.

MES IDs in SCN are one-based; canonical source record indexes are zero-based.
Every occurrence is retained because branches can reference the same PCM more
than once. `BAKUHATU.PCM` is classified as SFX and is never assigned a dialogue
record merely because it follows one.

The extractor rejects any retail ISO hash, PCM filename inventory, raw hash,
WAV format, sample count, or current SCN/source mapping that differs from this
contract.

## English review voices

English previews use the local `kokoro-onnx` runtime with generic stock voice
styles. No Japanese performer is cloned or imitated, and no project dialogue
is submitted to a network service. Natural synthesis is retained as mono PCM16
WAV. A second WAV is tempo-fitted with FFmpeg, resampled to 16,276 Hz, and then
padded or truncated to exactly the retail PCM sample count. These files remain
outside the game-build pipeline.

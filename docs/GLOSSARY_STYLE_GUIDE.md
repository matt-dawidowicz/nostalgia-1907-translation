# Nostalgia 1907 English glossary and style guide

## Authority and use

This guide records human-facing localization conventions. It supplements, but
does not silently override, the executable source-fingerprinted rules in
`translation_glossary.json`, `bomb_semantics.json`, chapter profiles, layout
rules, and record-scoped exceptions.

The canonical source has already completed a full-script review. There is no
active first-pass proposal queue. A future wording change needs fresh source
evidence, stable-ID review, normal validation, and candidate-bound runtime
evidence when playable bytes change.

## Translation priority

Use this order when two plausible English renderings compete:

1. retail Japanese meaning and gameplay semantics;
2. established plot/terminology consistency;
3. first-play comprehension;
4. character/register fidelity;
5. natural spoken English and pacing; and
6. layout economy within the proven renderer contract.

Never improve fluency by restoring a known mistranslation or changing a branch,
clue, polarity, number, direction, color, rank, or relationship.

## Core naming and terminology

| Japanese / concept | Canonical English | Notes |
| --- | --- | --- |
| 山田加助 | Yamada Kasuke | Full name in labels; `Kasuke` when familiar address is supported. |
| イリュ | Ilyu | Project spelling; do not silently normalize to Iryu. |
| イリューシャ | Ilyusha | Deliberately distinct from Ilyu. |
| アッシュビー | Ashby | Never `Ashbee`. |
| オイジー | Voysey | Full form where given: Aubrey Voysey. |
| ルーティ | Ruthie | Never Rudy/Lutie. |
| カール老 | Old Karl | Preserve title; never Old Carl. |
| キリーコフ | Kirikov | Full form: Kirikov Kamorovich. |
| デュナン | Dunant | Keep stable. |
| ストラ | Stra | Project nickname. |
| グランセリウス | Grancelius | Never Granzelius. |
| カモルビッチ | Kamorovich | Never Kamolovich. |
| 船長 | Captain | Rank label without punctuation. |
| 機関長 | Chief Engineer | `Chief` in dialogue only when natural/unambiguous. |
| 次長 | Deputy Chief | Formal organizational title. |
| チャーリー・マフィン | Charlie Muffin | Keep full name stable. |
| ベティ | Betty | Charlie's personification/name for the bomb. |
| ロシアの霧 | Russian Fog | Never `Russian Wing`; treat the established referent as a person. |
| メデ | Mede | Code name; deliberately distinct from `Medea`. |
| イギリス・インテリジェンス・アクション | British Intelligence Action | Formal organization name. |
| 大英帝国 | British Empire | Use when the empire itself is invoked. |
| 日本帝国 / 大日本帝国 context | Empire of Japan / Japanese Empire | Prefer `Empire of Japan` in formal geopolitical explanation. |

Names whose external romanization could still be checked against independent
official material include Ilyu, Lumeranka, Sunmin, and Canal Fitz. That is a
provenance opportunity, not an unfinished translation queue or reason to change
current text without stronger evidence.

## Ship and direction terms

| Japanese / concept | Canonical English | Notes |
| --- | --- | --- |
| 船倉 | Cargo Hold | Title case in labels; lowercase in prose. |
| 船長室 | Captain's Cabin | Use straight ASCII apostrophe. |
| 二等客室 | Second-Class Cabin | Hyphenated. |
| 一等客室ブロック | First-Class Cabin Block | Hyphenated. |
| 付き部屋C | Adjoining Room C | Controlled room label. |
| クルー会議室 | Crew Meeting Room | Location-label title case. |
| バー・ホクサイ / バーホクサイ | Bar Hokusai | Shipboard bar; not a port/starboard term. |
| 運航管制室 | Pilot House | Keep distinct from Communications Room. |
| 機関室 | Engine Room | Do not swap with radio/communications spaces. |
| 通信室 | Communications Room | Prefer for the room rather than equipment. |
| 左舷 | port | Never starboard. |
| 右舷 | starboard | Never port. |
| 船尾 / 後部 | aft / aft section | Preserve bomb/location direction exactly. |
| 竜骨部 / keel context | keel section | Do not casually substitute bilge. |
| おもかじ | starboard | Natural helm English; preserve amount of turn. |
| 舵輪軸～本 | wheel spoke(s) | Preserve the historical number of spokes. |

## Bomb and electrical terminology

These terms are gameplay-critical and are additionally covered by machine
validation.

| Japanese / concept | Canonical English | Notes |
| --- | --- | --- |
| ニッパー | Wire Cutters | Inventory title case; lowercase in prose. |
| コード | wire by default | Preserve deliberate source self-correction where tracked. |
| 電線 | electrical wire / wire | Do not flatten a source-authored distinction. |
| 起爆装置 | detonator | Keep separate from timer/counter. |
| 振り子式起爆装置 | pendulum detonator | Motion-triggered; not overcurrent. |
| タイマー | timer | Do not convert `2,000 degrees` into seconds. |
| 接続管 | connector tube | Maintain the reviewed action terminology. |
| バイパス | bypass | Noun/verb only where the source action supports it. |
| 三相電流 | three-phase current | White is neutral; red and blue are the candidate poles in the reviewed explanation. |
| 白 | white | Never cut white in the reviewed three-phase branch. |
| 赤 / 青 | red / blue | Preserve color directions exactly. |
| 上 / 下 | upper/above; lower/below | Preserve relative position exactly. |
| 舞台 | platform / stage | `platform` for hardware; `stage` may support the source metaphor. |
| 防御装置 | defense mechanism | Protective/anti-tamper mechanism. |
| 2,000度 | 2,000 degrees | Temperature, not time. |
| 青二才 | greenhorn / rookie | Idiom, not a blue component. |
| 貞操帯 | chastity belt | Deliberate bomb/woman metaphor; do not sanitize it. |

Do not change a wire instruction, success/failure branch, or bomb clue merely to
make the prose more elegant.

## UI and label style

- Location and inventory labels use title case; running dialogue uses normal
  sentence case.
- Speaker/rank labels use canonical names/titles without terminal punctuation.
- Binary settings are exact `OFF` and `ON`.
- Preserve `Mede` versus `Medea`.
- The tracked English character set is ASCII-constrained. Use straight
  apostrophes/quotation marks; do not introduce smart punctuation or unsupported
  Unicode.
- Action labels and compact UI text must be reviewed against their fixed or
  SCN-derived contract rather than padded by eye.

## Dialogue style

- Write idiomatic American English suitable for a localization of a 1907-set
  mystery/adventure; avoid contemporary internet slang and invented faux-
  Victorian prose.
- Preserve subject, object, tense, polarity, uncertainty, and point of view.
- Preserve source-supported sarcasm, class hostility, prejudice, gallows humor,
  sexism commentary, and other uncomfortable characterization rather than
  sanitizing it.
- Use contractions in conversational speech unless formality is deliberate.
- Render regional Japanese speech as readable social/regional English rather
  than phonetic eye dialect.
- Do not invent Russian, French, German, British, or other phonetic accents when
  the Japanese does not encode one.
- Ellipses use three periods (`...`) under the maintained canonical convention.
- Profanity and threats should match source force; do not intensify them for
  style.

## Character register

- **Chief Engineer:** strong Kansai register becomes noticeable
  Western/California working-class English because the source itself supports
  the East-versus-California joke. No surfer/cowboy eye dialect.
- **Charlie Muffin:** rough Eastern-U.S. engineer/seaman register; blunt and
  contracted, with less joking at the climax. Do not invent a specific city.
- **Ashby / Voysey / Director:** class-conscious British institutional diction,
  not phonetic RP. Preserve source-supported imperial/racist attitudes.
- **Kasuke:** educated conversational professional who becomes blunt under
  pressure.
- **Ilyu / Ilyusha:** educated cosmopolitan woman without an invented Russian
  accent; simpler/direct diction when emotionally candid.

## Source-authored oddities

Historical plausibility is not authority over the script. Reviewed oddities
such as `Mayday`, `Indian poker`, `simulation game`, `fiction`, `Japan's king`,
`satellite states`, Ashby's Queen reference, the salaryman joke, Finland/Suomi
framing, Mede/Medea wordplay, and the bomb/woman/chastity-belt imagery remain
unless stronger Japanese evidence justifies a change.

## Choice, warning, and consequence style

- Choices are concise, parallel, and semantically exact.
- Warnings prefer direct imperatives where that matches the source.
- Preserve yes/no polarity, color, direction, number, and consequence.
- Preserve uncertainty before the player learns the answer.
- A trap choice that explodes must not be rewritten into the action that
  succeeds, or vice versa.

## Layout policy

- `layout_policy: "adaptive"` stores semantic English without hand-inserted row
  breaks/padding. Shared renderer code owns row construction.
- `layout_policy: "fixed"` retains reviewer-owned physical layout and is covered
  by permanent fixed-layout validation.
- Before accepting longer wording, inspect stable-ID preview, roles,
  visible/runtime widths, row limits, whole-chapter capacity, and any affected
  fixed layout.
- The old first-pass proposal/preview campaign is complete and removed. There is
  no separate proposal artifact that substitutes for current validation.
- Formatting defects belong in general renderer/layout rules with tests, not
  chapter-specific binary patches. The two-byte PART1A Game Hall correction is a
  closed runtime-proven exception with exact hash/mutation guards.
- Static layout success never substitutes for candidate-bound Ares evidence when
  playable bytes change.

## Non-blocking provenance questions

A few historical audit questions can still be revisited if stronger source or
official evidence appears, including certain romanizations and obscure dialect,
proper-noun, or technical readings noted in earlier audit material. They are not
an active release-blocking proposal queue. A new conclusion must identify its
stable record, source evidence, and effect on current canonical text before any
change is applied.

# Nostalgia 1907 English Glossary and Style Guide

## Authority and use

This guide supplements, but does not silently override, the tracked `translation_glossary.json`, `bomb_semantics.json`, layout rules, and record-scoped exceptions. Japanese PNGs remain the visible source of truth. Add a source-fingerprinted glossary rule when a term must stay stable; add a record-scoped contextual exception when identical source evidence legitimately needs different English.

## Core naming and terminology

| Japanese / concept | Canonical English | Notes |
|---|---|---|
| 山田加助 | Yamada Kasuke | Use full name in labels; “Kasuke” only when dialogue directly supports familiar address. |
| イリュ | Ilyu | Project spelling; romanization remains flagged for external review. Do not silently normalize to Iryu. |
| イリューシャ | Ilyusha | Distinct from the shorter nickname Ilyu. |
| アッシュビー | Ashby | Never “Ashbee.” |
| オイジー | Voysey | Full name where given: Aubrey Voysey. |
| ルーティ | Ruthie | Never Rudy/Lutie. |
| カール老 | Old Karl | Preserve title; never Old Carl. |
| フィッツ | Fitz | `カナル・フィッツ` is currently Canal Fitz and remains romanization-sensitive. |
| キリーコフ | Kirikov | Full form: Kirikov Kamorovich. |
| ルメランカ | Lumeranka | Project spelling; external romanization review still open. |
| スンミン | Sunmin | Project spelling; external romanization review still open. |
| デュナン | Dunant | Keep consistent. |
| ストラ | Stra | Project nickname. |
| グランセリウス | Grancelius | Never Granzelius. |
| カモルビッチ | Kamorovich | Never Kamolovich. |
| 船長 | Captain | Rank label without punctuation. |
| 機関長 | Chief Engineer | Use “Chief” in direct dialogue only when natural and unambiguous. |
| 次長 | Deputy Chief | Capitalize as a formal organizational title. |
| チャーリー・マフィン | Charlie Muffin | Keep the full name stable; `Muffin` is explicitly discussed as part of his name. |
| ベティ | Betty | Charlie's personification/name for the bomb; preserve the woman/bomb metaphor where the source uses it. |
| ロシアの霧 | Russian Fog | **Never “Russia’s Wing.”** Treat the referent as a person once the deduction establishes that fact; use human pronouns or singular “they” when sex is unknown. |
| メデ | Mede | Code name. Distinct from mythological `メディア` → Medea. |
| イギリス・インテリジェンス・アクション | British Intelligence Action | Formal organization name. “British Intelligence” may be used generically when the source does not give the full title. |
| 大英帝国 | British Empire | Use when the source invokes the empire specifically. |
| 日本帝国 / 大日本帝国 context | Empire of Japan / Japanese Empire | Prefer “Empire of Japan” in formal narration and geopolitical explanation; keep one form consistent within an exchange. |
| ロシア皇帝 | Russian Emperor | “Tsar” is acceptable only if adopted consistently and supported by voice/style policy. |

## Ship and direction terms

| Japanese / concept | Canonical English | Notes |
|---|---|---|
| 船倉 | Cargo Hold | Title case in location labels; lowercase in running prose. |
| 船長室 | Captain’s Cabin | Use apostrophe. |
| 二等客室 | Second-Class Cabin | Hyphenated. |
| 一等客室ブロック | First-Class Cabin Block | Hyphenated. |
| 付き部屋C | Adjoining Room C | Project-controlled room label. |
| クルー会議室 | Crew Meeting Room | Location-label title case. |
| バー・ホクサイ / バーホクサイ | Bar Hokusai | Shipboard bar name. Do not misread it as a port/starboard direction. |
| 運航管制室 | Pilot House | Period-natural shipboard label; keep distinct from communications room. |
| 機関室 | Engine Room | Do not swap with communications/radio spaces. |
| 通信室 | Communications Room | Prefer this when the room, not individual equipment, is meant. |
| 左舷 | port | Never starboard. |
| 右舷 | starboard | Never port. |
| 船尾 / 後部 | aft / aft section | Choose by syntax; keep bomb location exact. |
| 竜骨部 / keel context | keel section | Verify against in-game ship diagram before locking “bilge.” |
| おもかじ | starboard | In helm orders, write natural bridge English and preserve turn amount. |
| 舵輪軸～本 | wheel spoke(s) | Historical helm measure. Preserve the number of spokes; do not convert it into full turns. |
| 客船 | passenger ship | Do not turn a hijacking announcement into first-person boasting by the hijackers. |

## Bomb and electrical terminology

| Japanese / concept | Canonical English | Notes |
|---|---|---|
| ニッパー | Wire Cutters | Title case as inventory/tool label; lowercase “wire cutters” in prose. |
| コード | wire by default | Preserve deliberate source self-correction from `電線` to `コード` where tracked. |
| 電線 | electrical wire / wire | Do not flatten a deliberate distinction in the source-authoritative record. |
| 起爆装置 / detonator context | detonator | Keep separate from timer/counter. |
| 振り子式起爆装置 | pendulum detonator | Motion-triggered; do not describe as overcurrent. |
| タイマー | timer | A countdown device, not a 2,000-second value unless the source explicitly supplies seconds. |
| 接続管 | connector tube | PART2E:199 is reviewed as “Check/examine the connector tube”; canonical gameplay wording uses “Check.” |
| バイパス | bypass | Use as noun or verb only when the source action supports it. |
| 三相電流 | three-phase current / three-phase alternating current | White is neutral; red and blue are the poles in the reviewed explanation. |
| 白 | white | Never cut white in the reviewed three-phase branch. |
| 赤 / 青 | red / blue | Color directions are gameplay-critical. |
| 上 / 下 | upper/above; lower/below | Preserve relative position exactly. |
| 舞台 | platform / stage | Prefer “platform” for the physical bomb assembly; “stage” may support the dancer metaphor in prose. |
| 防御装置 | defense mechanism | Means a protective/anti-tamper mechanism, not a generic safety device. |
| 2,000度 | 2,000 degrees | Temperature, not seconds. Preserve units explicitly. |
| 青二才 | greenhorn / rookie | Idiom for an inexperienced person; never parse it as a blue object or blue screw. |
| 貞操帯 | chastity belt | Deliberate bomb/woman metaphor in PART2E; do not sanitize it into a generic panel or pulse. |
| 犯行声明文 | written claim of responsibility | A communiqué/statement claiming the crime, not a physical trap and not merely a private intention. |

## UI and label style

- Action-select labels visibly use `ACTION <number>: <title>` in the Japanese bitmap. Do not add them until the fixed/menu geometry is previewed, but do not treat the number as semantically absent.
- Binary settings use exact `OFF` and `ON`.
- Location and inventory labels use title case; running dialogue uses normal sentence case.
- Speaker/rank labels contain the canonical name or title without terminal punctuation.
- Preserve `Mede` versus `Medea`; they are intentionally distinct.
- The exact tracked English character set is `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,?!'"-:;()/&`. Use straight ASCII apostrophes and quotation marks only. Em dashes, smart quotes, brackets, and other Unicode punctuation are not encodable.

## Dialogue style

- Write idiomatic American English appropriate to a 1907-set mystery/adventure localization. Avoid contemporary internet slang and avoid fake Victorian archaism not supported by characterization.
- Preserve the speaker’s perspective, subject, object, tense, polarity, and certainty. Do not turn questions into declarations, third person into first person, or “might be a trap” into “is a trap.”
- Preserve characterization: sarcasm, gallows humor, panic, class resentment, sexism commentary, and bomb-as-woman metaphor may be uncomfortable but are part of the scene.
- Render Kansai or other regional speech as natural colloquial English. Do not use eye-dialect spelling. When a joke depends on recognizing the region, solve the entire exchange together and document the localization choice.
- Use contractions in conversational English unless the speaker is deliberately formal. The canonical font supports straight ASCII apostrophes; do not use typographic apostrophes or other Unicode punctuation.
- Ellipses use three periods (`...`) unless fixed-layout evidence requires a different glyph pattern. Do not multiply punctuation merely to imitate Japanese spacing.
- Profanity should match force and character. Do not invent threats, terrorism language, or insults absent from the source.

## Character-register policy from the 2026-08-27 audit

- **Chief Engineer:** strong Kansai speech becomes noticeable Western/California
  working-class English because the source itself makes an East-versus-California
  joke. Do not use surfer, cowboy, or phonetic eye dialect.
- **Charlie Muffin:** rough Eastern-U.S. engineer/seaman voice, blunt and
  contracted, with jokes dropping away during his final high-stakes gamble. Do
  not invent a specific Eastern city.
- **Ashby / Voysey / Director:** express British class and institutional register
  through syntax and diction, not phonetic RP. Preserve Ashby's ugly imperial
  and racist source material rather than sanitizing it.
- **Kasuke:** educated conversational professional who becomes blunt under
  pressure. Rough London influence appears only where the source explicitly
  mentions it.
- **Ilyu / Ilyusha:** educated cosmopolitan woman with no invented Russian
  accent; playful, professional, and then simpler/more direct as emotional
  honesty increases.
- Do not invent Russian, French, German, or other accents for characters whose
  Japanese is standard.

## Source-authored oddities

Do not silently normalize an oddity merely because it is anachronistic or
historically awkward. Reviewed examples to preserve include `Mayday`, `Indian
poker`, `simulation game`, `fiction`, `Japan's king`, `satellite states`,
Ashby's Queen reference, the salaryman joke, the Finland/Suomi framing, the
Mede/Medea wordplay, the hard-baked Muffin joke, and the bomb/woman/chastity-belt
metaphors. A change requires Japanese evidence, not historical preference.

## Choice, warning, and consequence style

- Choices must be concise, parallel, and semantically exact. Preserve yes/no polarity, color, direction, number, and the action’s consequence.
- Warnings should use direct imperatives: “Do not touch the bomb,” “Never cut white,” and similar.
- Never “improve” a branch by changing what succeeds or explodes. A trap wire that explodes when cut must remain distinct from a real wire that must be cut.
- Preserve uncertainty where the player has not yet learned the answer.

## Layout policy

- Adaptive records contain semantic text only. Do not insert manual line breaks or padding; let the renderer-aware formatter wrap them.
- Fixed records preserve exact reviewed spaces and lines. Credits are especially spacing-sensitive.
- Before accepting longer English, inspect roles, visible/runtime cell widths, preview rows, and maximum rows. The first-pass proposal set has a separate embedded-contract preview audit, but that does not replace per-ID preview, whole-chapter compilation, the complete retail-backed validation gate, and scene/branch playtesting.
- Formatting defects belong in a general renderer/layout rule with tests, never in a chapter-specific binary patch.

## Open glossary questions

1. Final external romanization review: Ilyu, Lumeranka, Sunmin, Canal Fitz.
2. PART2E:137–139 dialect pun and regional reference.
3. PART2E:140: East Town Street, `ダダ・スレイマン`, and Sherry.
4. PART2E:195 technical label preceding 2,000 degrees.
5. PART3C:127 shouted proper noun/cry.
6. PART4B:245 contextual choice between “fast” and “early.”

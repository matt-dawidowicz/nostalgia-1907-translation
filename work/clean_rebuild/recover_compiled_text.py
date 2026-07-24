#!/usr/bin/env python3
"""Recover translator-facing text from bitmap-encoded playable MES records."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
OLD_PROJECT = Path(r"C:\Users\thema\Documents\Codex\2026-07-12\i")
PROFILES = OLD_PROJECT / "outputs" / "nostalgia1907_translation_profiles"
DEFAULT_FORENSIC = HERE / "forensic_decode.json"
DEFAULT_OUTPUT = HERE / "recovered_compiled_text.json"
SPACE_RE = re.compile(r"\s+")


def normalized(text: str) -> str:
    """Collapse render padding and line breaks to translator-facing spacing."""
    return SPACE_RE.sub(" ", text).strip()


def texts_from_json(path: Path) -> list[str]:
    """Extract translation strings from one known project JSON shape."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    texts: list[str] = []
    if isinstance(payload, dict):
        exact = payload.get("required_text_exact")
        if isinstance(exact, dict):
            texts.extend(value for value in exact.values() if isinstance(value, str))
        segments = payload.get("segments")
        if isinstance(segments, list):
            texts.extend(
                item["text"]
                for item in segments
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
        for key in ("texts", "records", "replacements"):
            mapping = payload.get(key)
            if isinstance(mapping, dict):
                texts.extend(value for value in mapping.values() if isinstance(value, str))
        if all(isinstance(key, str) and key.isdigit() for key in payload):
            texts.extend(value for value in payload.values() if isinstance(value, str))
    return texts


def project_corpus() -> list[str]:
    """Collect a deterministic, translation-only language corpus."""
    paths: set[Path] = set(PROFILES.glob("PART*.json"))
    paths.update(PROFILES.glob("START.json"))

    provenance_path = HERE / "source_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for chapter in provenance["chapters"].values():
        for match in chapter["matching_generated_mes"]:
            for manifest in match["manifests"]:
                if manifest.get("all_segments_have_text"):
                    paths.add(Path(manifest["path"]))
                    break
            else:
                continue
            break

    paths.update((WORKSPACE / "work" / "act4_translation").glob("*_texts.json"))
    paths.update((WORKSPACE / "work" / "staff_translation").glob("*_texts.json"))
    corpus = [normalized(text) for path in sorted(paths) for text in texts_from_json(path)]
    return [text for text in corpus if text]


class CharacterModel:
    """A compact character n-gram model used to rank bitmap aliases."""

    def __init__(
        self, texts: list[str], order: int = 5, space_bonus: float = 0.0
    ) -> None:
        self.order = order
        self.space_bonus = space_bonus
        self.context_counts: dict[str, Counter[str]] = defaultdict(Counter)
        alphabet = set(" ")
        start = "^" * (order - 1)
        for text in texts:
            alphabet.update(text)
            padded = start + text + "$"
            for index in range(order - 1, len(padded)):
                context = padded[index - order + 1 : index]
                self.context_counts[context][padded[index]] += 1
        alphabet.add("$")
        self.alphabet_size = len(alphabet)

    def transition(self, context: str, char: str) -> float:
        """Return a smoothed log probability for one next character."""
        counts = self.context_counts.get(context)
        alpha = 0.03
        if not counts:
            return -math.log(self.alphabet_size)
        score = math.log(
            (counts[char] + alpha)
            / (sum(counts.values()) + alpha * self.alphabet_size)
        )
        return score + (self.space_bonus if char == " " else 0.0)

    def append(self, text: str, score: float, context: str, unit: str) -> tuple[str, float, str]:
        """Append a cell while collapsing padding whitespace incrementally."""
        output = text
        current = context
        total = score
        for char in unit:
            if char.isspace():
                if not output or output.endswith(" "):
                    continue
                char = " "
            total += self.transition(current, char)
            output += char
            current = (current + char)[-(self.order - 1) :]
        return output, total, current

    def finish(self, score: float, context: str) -> float:
        """Score the end of a candidate record."""
        return score + self.transition(context, "$")


class WordSegmenter:
    """Restore word boundaries that compact glyphs intentionally erase."""

    def __init__(self, texts: list[str]) -> None:
        self.words: Counter[str] = Counter(
            match.group(0).lower()
            for text in texts
            for match in re.finditer(r"[A-Za-z]+", text)
        )

    def split_unknown(self, word: str) -> str:
        """Split an unknown alphabetic run only when every part is known."""
        lower = word.lower()
        if len(word) < 4 or lower in self.words:
            return word
        best: list[tuple[float, tuple[str, ...]] | None] = [None] * (len(word) + 1)
        best[0] = (0.0, ())
        for end in range(1, len(word) + 1):
            choices: list[tuple[float, tuple[str, ...]]] = []
            for start in range(end):
                previous = best[start]
                part = lower[start:end]
                if previous is None or part not in self.words:
                    continue
                if len(part) == 1 and part not in {"a", "i"}:
                    continue
                # Fewer words win unless frequency evidence is materially better.
                score = previous[0] + math.log(self.words[part] + 1) - 50.0
                choices.append((score, previous[1] + (word[start:end],)))
            if choices:
                best[end] = max(choices, key=lambda item: item[0])
        result = best[-1]
        if result is None or len(result[1]) < 2:
            return word
        return " ".join(result[1])

    def restore(self, text: str) -> str:
        """Restore punctuation, case-transition, and dictionary boundaries."""
        text = re.sub(r"(?<=\w)\.\.\.(?=[A-Za-z])", "... ", text)
        text = re.sub(r"([!?,:;])(?=[A-Z])", r"\1 ", text)
        text = re.sub(r"(?<!\.)\.(?!\.)(?=[A-Z][a-z])", ". ", text)
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
        return normalized(
            re.sub(
                r"[A-Za-z]+",
                lambda match: self.split_unknown(match.group(0)),
                text,
            )
        )


def token_options(token: dict[str, object]) -> tuple[str, ...]:
    """Return distinct visible strings for one forensic token."""
    kind = token["kind"]
    if kind == "end":
        return ()
    if kind == "control":
        return ()
    options = token.get("options")
    if isinstance(options, list) and options:
        return tuple(sorted({str(item[1]) for item in options}))
    if kind == "fixed" and token.get("code") in (1, 16):
        return (" ",)
    raise ValueError(f"no visible candidates for token {token}")


def decode_record(
    tokens: list[dict[str, object]],
    model: CharacterModel,
    beam_width: int,
) -> tuple[str, float, int]:
    """Return the highest-scoring normalized text for one compiled record."""
    start_context = "^" * (model.order - 1)
    beam: list[tuple[str, float, str]] = [("", 0.0, start_context)]
    ambiguous_cells = 0
    for token in tokens:
        options = token_options(token)
        if not options:
            continue
        if len(options) > 1:
            ambiguous_cells += 1
        expanded: dict[str, tuple[float, str]] = {}
        for text, score, context in beam:
            for option in options:
                new_text, new_score, new_context = model.append(
                    text, score, context, option
                )
                previous = expanded.get(new_text)
                if previous is None or new_score > previous[0]:
                    expanded[new_text] = (new_score, new_context)
        ranked = sorted(
            (
                (text, score, context)
                for text, (score, context) in expanded.items()
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        beam = ranked[:beam_width]

    finished = [
        (normalized(text), model.finish(score, context))
        for text, score, context in beam
    ]
    text, score = max(finished, key=lambda item: item[1])
    return text, score, ambiguous_cells


def expected_profile(chapter: str) -> dict[int, str]:
    """Return locked expected text for a chapter profile, if available."""
    path = PROFILES / f"{chapter}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        int(index): normalized(text)
        for index, text in payload.get("required_text_exact", {}).items()
    }


def recover_chapter(
    chapter: dict[str, object],
    model: CharacterModel,
    segmenter: WordSegmenter,
    beam_width: int,
) -> dict[str, object]:
    """Decode a chapter and compare all available locked profile strings."""
    name = str(chapter["chapter"])
    expected = expected_profile(name)
    records: list[dict[str, object]] = []
    mismatches: list[dict[str, object]] = []
    for item in chapter["records"]:  # type: ignore[union-attr]
        index = int(item["record"])
        text, score, ambiguous_cells = decode_record(
            item["tokens"], model, beam_width
        )
        text = segmenter.restore(text)
        record = {
            "record": index,
            "text": text,
            "score": score,
            "ambiguous_cells": ambiguous_cells,
        }
        records.append(record)
        if index in expected and text != expected[index]:
            mismatches.append(
                {"record": index, "expected": expected[index], "recovered": text}
            )
    return {
        "chapter": name,
        "record_count": len(records),
        "locked_text_count": len(expected),
        "locked_text_matches": len(expected) - len(mismatches),
        "locked_text_mismatches": mismatches,
        "records": records,
    }


def main() -> None:
    """Recover selected chapters and write validation evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forensic", type=Path, default=DEFAULT_FORENSIC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--beam-width", type=int, default=1500)
    parser.add_argument("--space-bonus", type=float, default=0.0)
    args = parser.parse_args()

    forensic = json.loads(args.forensic.read_text(encoding="utf-8"))
    corpus = project_corpus()
    model = CharacterModel(corpus, space_bonus=args.space_bonus)
    segmenter = WordSegmenter(corpus)
    chapters = [
        recover_chapter(chapter, model, segmenter, args.beam_width)
        for chapter in forensic["chapters"]
    ]
    mismatch_count = sum(len(item["locked_text_mismatches"]) for item in chapters)
    payload = {
        "status": "PASS" if mismatch_count == 0 else "REVIEW",
        "corpus_line_count": len(corpus),
        "beam_width": args.beam_width,
        "space_bonus": args.space_bonus,
        "locked_text_mismatch_count": mismatch_count,
        "chapters": chapters,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "output": str(args.output),
                "corpus_line_count": len(corpus),
                "chapters": [
                    {
                        "chapter": item["chapter"],
                        "record_count": item["record_count"],
                        "locked_text_matches": item["locked_text_matches"],
                        "locked_text_count": item["locked_text_count"],
                    }
                    for item in chapters
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

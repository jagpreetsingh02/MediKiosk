"""The offline backend: a deterministic, rule-based extractor that satisfies the LLM protocol.

This exists because a hackathon demo must not depend on a network, and because it makes the
"does the LLM actually help?" question measurable — `eval/` runs the same 50 scripts through
both backends and reports the delta. If the delta is small, that is a finding worth reporting,
not an embarrassment to hide.

It is a keyword-and-pattern matcher over the ontology's own option labels. It will never
extract something the deterministic path could not, and it never invents a quote: every quote
it emits is a slice of the input string, taken by index.
"""
from __future__ import annotations

import re
import time
from typing import Any

from app.llm.protocol import LLMResponse
from app.modules.dialogue.ontology import Question

#: Phrases that map to an option value, beyond the option's own label words. Content, so it
#: lives in data — see data/ontology/lexicon.yaml. Loaded lazily to keep imports cheap.
_LEXICON: dict[str, dict[str, list[str]]] | None = None


def _lexicon() -> dict[str, dict[str, list[str]]]:
    global _LEXICON
    if _LEXICON is None:
        import yaml

        from app.core.config import settings

        path = settings.path(settings.ontology_dir) / "lexicon.yaml"
        _LEXICON = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _LEXICON


_WORD = re.compile(r"[\wऀ-෿]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _find_quote(text: str, needle: str) -> str | None:
    """Return the exact slice of `text` that matched. Never a reconstruction."""
    lowered = text.casefold()
    index = lowered.find(needle.casefold())
    if index >= 0:
        return text[index : index + len(needle)]
    return None


def match_options(question: Question, utterance: str) -> list[tuple[str, str, float]]:
    """Return (option_value, verbatim_quote, confidence) for every option the text supports."""
    lexicon = _lexicon().get(question.id, {})
    hits: list[tuple[str, str, float]] = []

    for option in question.options:
        phrases: list[str] = list(lexicon.get(option.value, []))
        # The label's own distinctive words are a phrase set for free.
        for label in (option.label_en, option.label_hi or ""):
            if label:
                phrases.append(label)
                phrases.extend(w for w in _tokens(label) if len(w) > 4)

        best: tuple[str, float] | None = None
        for phrase in phrases:
            quote = _find_quote(utterance, phrase)
            if quote is None:
                continue
            # Longer matches are stronger evidence, capped so nothing here reaches certainty.
            score = min(0.55 + 0.03 * len(quote.split()), 0.88)
            if best is None or score > best[1]:
                best = (quote, score)
        if best is not None:
            hits.append((option.value, best[0], best[1]))

    return sorted(hits, key=lambda h: -h[2])


class OfflineLLM:
    """Satisfies `LLMBackend`. Deterministic: same input, same output, forever."""

    name = "medikiosk-offline-extractor"
    version = "1.0.0"
    offline = True

    def complete(self, *, system: str, user: str, schema_hint: str) -> LLMResponse:
        """The offline backend does not do free-form completion.

        `app/llm/extraction.py` calls `extract_offline()` directly when this backend is
        selected, because a rule matcher has no meaningful "complete a prompt" operation.
        This method exists to satisfy the protocol and returns an empty, schema-valid result
        so a caller that goes through the generic path degrades to "extracted nothing"
        rather than crashing.
        """
        started = time.perf_counter()
        return LLMResponse(
            text='{"slots": [], "unplaced": []}',
            model_name=self.name,
            model_version=self.version,
            prompt=f"{system}\n{user}",
            offline=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def extract_offline(question: Question, utterance: str) -> dict[str, Any]:
    """Rule-based slot extraction. Returns an `ExtractionResult`-shaped dict."""
    slots: list[dict[str, Any]] = []

    if question.kind in ("single_choice", "duration"):
        hits = match_options(question, utterance)
        if hits:
            value, quote, confidence = hits[0]
            slots.append(
                {"path": question.path, "value": value, "quote": quote, "confidence": confidence}
            )
    elif question.kind == "multi_choice":
        hits = [h for h in match_options(question, utterance) if h[0] != "none"]
        if hits:
            slots.append(
                {
                    "path": question.path,
                    "value": [h[0] for h in hits],
                    # The quote must cover every value, so it spans from the first match to
                    # the last. A quote that covers only one value would fail verification.
                    "quote": _span_covering(utterance, [h[1] for h in hits]),
                    "confidence": min(h[2] for h in hits),
                }
            )
    elif question.kind == "boolean":
        polarity = _polarity(utterance)
        if polarity is not None:
            value, quote = polarity
            slots.append(
                {"path": question.path, "value": value, "quote": quote, "confidence": 0.8}
            )
    elif question.kind == "scale":
        number = _first_number(utterance)
        if number is not None:
            value, quote = number
            slots.append(
                {"path": question.path, "value": str(value), "quote": quote, "confidence": 0.75}
            )
    else:
        # An open_text question may ALSO render tap options (the chief complaint does).
        # Try to land the narration on one of them first: "mere chhaati mein dard" is more
        # useful to the physician as `pain` than as an unparsed sentence. Fall back to the
        # raw text when nothing matches, so nothing the patient said is ever discarded.
        hits = match_options(question, utterance) if question.options else []
        stripped = utterance.strip()
        if hits:
            value, quote, confidence = hits[0]
            slots.append(
                {"path": question.path, "value": value, "quote": quote, "confidence": confidence}
            )
        elif stripped:
            slots.append(
                {"path": question.path, "value": stripped, "quote": stripped, "confidence": 0.9}
            )

    return {"slots": slots, "unplaced": [] if slots else [utterance.strip()][: 1 if utterance.strip() else 0]}


def _span_covering(text: str, quotes: list[str]) -> str:
    """The smallest slice of `text` containing every quote. Still a real substring."""
    lowered = text.casefold()
    starts, ends = [], []
    for quote in quotes:
        index = lowered.find(quote.casefold())
        if index >= 0:
            starts.append(index)
            ends.append(index + len(quote))
    if not starts:
        return text.strip()
    return text[min(starts) : max(ends)]


#: Affirmation and negation cues. Data, not cleverness — see data/ontology/lexicon.yaml
#: for the language-specific sets this falls back to.
_YES = ("yes", "yeah", "haan", "haa", "ji haan", "ho", "aan", "correct", "true", "sahi")
_NO = ("no", "nahin", "nahi", "never", "kabhi nahin", "not", "illa", "false")


def _polarity(utterance: str) -> tuple[bool, str] | None:
    """Negation first: "no, never" must not read as a yes because "no" contains no vowel cue."""
    for cue in sorted(_NO, key=len, reverse=True):
        quote = _find_quote(utterance, cue)
        if quote is not None and _is_whole_word(utterance, quote):
            return False, quote
    for cue in sorted(_YES, key=len, reverse=True):
        quote = _find_quote(utterance, cue)
        if quote is not None and _is_whole_word(utterance, quote):
            return True, quote
    return None


def _is_whole_word(text: str, quote: str) -> bool:
    pattern = rf"(?<!\w){re.escape(quote)}(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


_NUMBER = re.compile(r"\b(10|[0-9])\b")


def _first_number(utterance: str) -> tuple[int, str] | None:
    match = _NUMBER.search(utterance)
    if match is None:
        return None
    return int(match.group(1)), match.group(0)

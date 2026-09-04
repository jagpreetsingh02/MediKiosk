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

#: Match scores are bucketed before ranking, so a one-word difference in phrase length does
#: not outrank the order the patient narrated in. Within a bucket, earliest mention wins.
#: The scale runs 0.55–0.88, so this gives three meaningful strength bands.
_SCORE_BUCKET = 0.1

#: Option values that themselves assert absence. Negation suppression does not apply to them.
_ABSENCE_OPTIONS = frozenset({"none", "never", "no", "na", "not_applicable", "unsure"})


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _find_quote(text: str, needle: str) -> tuple[str, int] | None:
    """Return the exact slice of `text` that matched, and where. Never a reconstruction."""
    lowered = text.casefold()
    index = lowered.find(needle.casefold())
    if index >= 0:
        return text[index : index + len(needle)], index
    return None


#: Negators. A match immediately preceded by one of these is the patient RULING SOMETHING OUT,
#: and recording it as present is how a system invents a symptom nobody reported.
#: "a heavy feeling, like pressure, not sharp" must not yield `sharp`.
_NEGATORS = (
    "not",
    "no",
    "never",
    "without",
    "denies",
    "denied",
    "isn't",
    "wasn't",
    "doesn't",
    "didn't",
    "dont",
    "don't",
    "nahin",
    "nahi",
    "na",
    "bilkul nahin",
    "koi nahin",
    "illa",
)
#: How far back to look. Long enough for "it is not a sharp pain", short enough that a
#: negator in a previous clause does not suppress an unrelated later symptom.
_NEGATION_WINDOW = 24


def _is_negated(text: str, index: int) -> bool:
    window = text[max(0, index - _NEGATION_WINDOW) : index].casefold()
    # Stop at a clause boundary: "no fever, chest pain present" negates fever, not the pain.
    for boundary in (";", " but ", " however ", " aur ", " and "):
        cut = window.rfind(boundary)
        if cut >= 0:
            window = window[cut + len(boundary) :]
    tokens = re.findall(r"[\w']+", window)
    return any(token in _NEGATORS for token in tokens[-4:])


def match_options(question: Question, utterance: str) -> list[tuple[str, str, float]]:
    """Return (option_value, verbatim_quote, confidence) for every option the text supports."""
    lexicon = _lexicon().get(question.id, {})
    # Carries the match position as a fourth element for ranking; it is dropped on the way out.
    hits: list[tuple[str, str, float, int]] = []

    for option in question.options:
        phrases: list[str] = list(lexicon.get(option.value, []))
        # The label's own distinctive words are a phrase set for free.
        for label in (option.label_en, option.label_hi or ""):
            if label:
                phrases.append(label)
                phrases.extend(w for w in _tokens(label) if len(w) > 4)

        # An option that MEANS absence ("never", "none of these") is not negated by a
        # preceding negator — "no, I never smoke" reinforces `never`, it does not cancel it.
        # Suppressing it here recorded nothing at all and lost a real clinical answer.
        negatable = option.value not in _ABSENCE_OPTIONS

        best: tuple[str, float, int] | None = None
        for phrase in phrases:
            found = _find_quote(utterance, phrase)
            if found is None:
                continue
            quote, index = found
            if negatable and _is_negated(utterance, index):
                continue
            # Longer matches are stronger evidence, capped so nothing here reaches certainty.
            score = min(0.55 + 0.03 * len(quote.split()), 0.88)
            if best is None or score > best[1]:
                best = (quote, score, index)
        if best is not None:
            hits.append((option.value, best[0], best[1], best[2]))

    # Rank by strength, then by what the patient said FIRST. Comparable matches are bucketed
    # so a one-word difference in phrase length does not outrank the order of narration:
    # in "my face swelled up and I could not breathe" both options are real, and the one
    # they led with is the one to record for a single-choice question.
    ranked = sorted(hits, key=lambda h: (-round(h[2] / _SCORE_BUCKET), h[3]))
    return [(value, quote, score) for value, quote, score, _index in ranked]


class OfflineLLM:
    """Satisfies `LLMBackend`. Deterministic: same input, same output, forever."""

    name = "swastra-offline-extractor"
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
    value: str | bool | int | list[str]

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
            slots.append({"path": question.path, "value": value, "quote": quote, "confidence": 0.8})
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

    return {
        "slots": slots,
        "unplaced": [] if slots else [utterance.strip()][: 1 if utterance.strip() else 0],
    }


def _span_covering(text: str, quotes: list[str]) -> str:
    """The smallest slice of `text` containing every quote. Still a real substring."""
    lowered = text.casefold()
    starts: list[int] = []
    ends: list[int] = []
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
        found = _find_quote(utterance, cue)
        if found is not None and _is_whole_word(utterance, found[0]):
            return False, found[0]
    for cue in sorted(_YES, key=len, reverse=True):
        found = _find_quote(utterance, cue)
        if found is not None and _is_whole_word(utterance, found[0]):
            return True, found[0]
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

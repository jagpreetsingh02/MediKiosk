"""Module A's extraction layer — the LLM's first job.

The design in one line: **the model proposes, `record_fact()` disposes.**

The model is asked for a `quote` alongside every value, and that quote is then checked against
the actual transcript by string search — not by asking the model whether it was honest. Three
things are verified before anything is recorded:

1. the quote is a real substring of the utterance (else: dropped, counted as a hallucination);
2. the path is one the ontology defines (else: dropped);
3. for a choice question, the value is one of the rendered options (else: dropped).

Whatever survives goes through `record_fact()`, which independently re-checks provenance. A
fact therefore has to pass two unrelated gates, and the model authored neither of them.

Rule or LLM? For a tapped answer there is no extraction at all — the option value *is* the
answer, and running a model over it would add latency and a failure mode for nothing. The LLM
is used only for free narration, which is the case a rule genuinely cannot cover: an open-ended
"tell me what's wrong" answer in a mix of two languages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.contracts.provenance import Fact, Modality, SourceTier
from app.contracts.record import FactLedger, record_fact, utterance_span
from app.core.errors import LLMContractError, ProvenanceError, ValidationError
from app.core.logging import get_logger
from app.llm.offline import extract_offline
from app.llm.protocol import LLMResponse, parse_or_fail
from app.llm.registry import get_llm
from app.llm.schemas import ExtractionResult
from app.modules.dialogue.ontology import Ontology, Question

log = get_logger(__name__)

EXTRACTION_SYSTEM = """You extract structured clinical slots from what a patient said.

Rules you must follow exactly:
- Extract ONLY what the patient actually said. Never add what usually accompanies a symptom.
- Every slot MUST include `quote`: a VERBATIM substring, copied character-for-character from
  the patient's words. Do not translate, correct, or tidy the quote. If you cannot quote it,
  do not extract it.
- Use only the allowed values listed for the question. If nothing fits, extract nothing.
- You are NOT diagnosing. Never output a disease name that the patient did not say.
- Anything you cannot place goes in `unplaced`, verbatim. Never force it into a slot."""


@dataclass(slots=True)
class ExtractionOutcome:
    """What happened, in enough detail for the eval harness to score it."""

    facts: list[Fact] = field(default_factory=list)
    proposed: int = 0
    accepted: int = 0
    #: Values the model produced whose quote was NOT in the transcript. The hallucination
    #: count. The eval harness requires this to be reported, and requires facts to be 0.
    rejected_unquoted: list[dict[str, Any]] = field(default_factory=list)
    rejected_unknown_path: list[str] = field(default_factory=list)
    rejected_bad_value: list[dict[str, Any]] = field(default_factory=list)
    unplaced: list[str] = field(default_factory=list)
    backend: str = ""
    offline: bool = True
    latency_ms: int = 0
    llm_response: LLMResponse | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposed": self.proposed,
            "accepted": self.accepted,
            "rejectedUnquoted": self.rejected_unquoted,
            "rejectedUnknownPath": self.rejected_unknown_path,
            "rejectedBadValue": self.rejected_bad_value,
            "unplaced": self.unplaced,
            "backend": self.backend,
            "offline": self.offline,
            "latencyMs": self.latency_ms,
        }


def _allowed_values(question: Question) -> str:
    if not question.options:
        return "free text"
    return ", ".join(f"{o.value} ({o.label_en})" for o in question.options)


def _build_prompt(question: Question, utterance: str) -> tuple[str, str]:
    user = (
        f"Question asked: {question.prompt['en']}\n"
        f"Slot path: {question.path}\n"
        f"Question type: {question.kind}\n"
        f"Allowed values: {_allowed_values(question)}\n\n"
        f"What the patient said (verbatim):\n{utterance}"
    )
    schema_hint = (
        '{"slots": [{"path": "<slot path>", "value": "<allowed value or free text>", '
        '"quote": "<verbatim substring of what the patient said>", '
        '"confidence": <0.0-1.0>}], "unplaced": ["<anything you could not place>"]}'
    )
    return user, schema_hint


def extract(
    *,
    question: Question,
    utterance: str,
    ontology: Ontology,
    ledger: FactLedger,
    turn_id: str,
    language: str = "en",
    asr_confidence: float | None = None,
    audio_ref: str | None = None,
    modality: Modality = Modality.SPEECH,
) -> ExtractionOutcome:
    """Extract slots from free narration and record whatever survives verification."""
    backend = get_llm()
    outcome = ExtractionOutcome(backend=backend.name, offline=backend.offline)

    if backend.offline:
        payload = extract_offline(question, utterance)
        result = ExtractionResult.model_validate(payload)
    else:
        user, schema_hint = _build_prompt(question, utterance)
        response = backend.complete(system=EXTRACTION_SYSTEM, user=user, schema_hint=schema_hint)
        outcome.llm_response = response
        outcome.latency_ms = response.latency_ms
        try:
            result = parse_or_fail(response, ExtractionResult)
        except LLMContractError as exc:
            # A hard failure. The deterministic answer stands; nothing is recorded.
            log.warning("extraction.contract_failure", question=question.id, error=str(exc)[:200])
            raise

    outcome.proposed = len(result.slots)
    outcome.unplaced = list(result.unplaced)

    for slot in result.slots:
        # --- gate 1: the quote must really be in the transcript -----------------
        if slot.quote.casefold() not in utterance.casefold():
            outcome.rejected_unquoted.append(
                {"path": slot.path, "value": slot.value, "quote": slot.quote}
            )
            log.warning(
                "extraction.hallucinated_quote",
                question=question.id,
                path=slot.path,
                quote=slot.quote[:80],
            )
            continue

        # --- gate 2: the path must exist ----------------------------------------
        if slot.path not in ontology.known_paths:
            outcome.rejected_unknown_path.append(slot.path)
            continue

        # --- gate 3: the value must be an allowed option -------------------------
        target = ontology.by_path.get(slot.path, question)
        wanted = slot.value if isinstance(slot.value, list) else [slot.value]
        allowed = target.valid_values()
        is_coded = bool(allowed) and all(str(v) in allowed for v in wanted)
        if target.options and target.kind != "open_text" and not is_coded:
            # A choice question admits nothing but its own options.
            outcome.rejected_bad_value.append({"path": slot.path, "value": slot.value})
            continue

        # --- gate 4: record_fact re-checks everything independently --------------
        # The quote, not the whole utterance, is the span. The provenance a physician sees
        # is the six words that actually justify the value, not a paragraph containing them.
        exact_quote = _exact_slice(utterance, slot.quote)
        span = utterance_span(
            verbatim=exact_quote,
            turn_id=turn_id,
            question_id=question.id,
            modality=modality,
            full_text=utterance,
            language=language,
            asr_confidence=asr_confidence,
            audio_ref=audio_ref,
        )
        try:
            fact = record_fact(
                ledger,
                path=slot.path,
                value=slot.value,
                tier=SourceTier.STATED,
                source=span,
                confidence=min(slot.confidence, asr_confidence or 1.0),
                provenance_note=f"extracted:{backend.name}",
                known_paths=ontology.known_paths,
                # Closed-vocabulary proof applies only to a value that IS an option.
                # Free narration on an open_text question proves itself the normal way:
                # by appearing in its own source span.
                coded_value_of=allowed if is_coded else None,
            )
        except (ProvenanceError, ValidationError) as exc:
            outcome.rejected_unquoted.append(
                {
                    "path": slot.path,
                    "value": slot.value,
                    "quote": slot.quote,
                    "recordFactRejection": str(exc)[:160],
                }
            )
            continue

        outcome.facts.append(fact)
        outcome.accepted += 1

    return outcome


def _exact_slice(haystack: str, needle: str) -> str:
    """Return the real casing of the matched region. Never a reconstruction of the quote."""
    index = haystack.casefold().find(needle.casefold())
    return haystack[index : index + len(needle)] if index >= 0 else needle

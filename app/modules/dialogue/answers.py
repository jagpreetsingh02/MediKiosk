"""Turning an answer into facts. The only bridge between the kiosk and the ledger.

Every path out of this module ends in ``record_fact()``. There is no branch that writes a
value any other way, which is why the "tapped" case is interesting: a tap has no utterance,
so what is its source? The answer is that **the label the patient read and pressed is the
source**. We record it verbatim, with ``modality=touch``. That is honestly what happened, it
renders sensibly in click-to-source ("patient selected: *Chest*"), and it means a tapped
answer is exactly as auditable as a spoken one.

Tapping is ``confirmed`` (the patient affirmed a direct, closed question). Free narration is
``stated``. Those are the two utterance tiers and they mean different things clinically: a
patient volunteering chest pain is a stronger signal than a patient agreeing that they have it.
"""
from __future__ import annotations

from typing import Any

from app.contracts.provenance import Fact, Modality, SourceTier
from app.contracts.record import FactLedger, record_fact, utterance_span
from app.core.errors import ValidationError
from app.modules.dialogue.machine import DialogueMachine
from app.modules.dialogue.ontology import Ontology, Question

#: A tap is a direct affirmation of a rendered label: no transcription, no ambiguity.
TOUCH_CONFIDENCE = 1.0
#: A typed answer is the patient's own words with no ASR in the loop.
TYPED_CONFIDENCE = 0.97


def _labels_for(question: Question, values: list[str], language: str) -> str:
    """The verbatim source for a tapped answer: the labels the patient actually saw."""
    labels = []
    for value in values:
        option = question.option(value)
        labels.append(option.label(language) if option else value)
    return ", ".join(labels)


def _validate_choice(question: Question, values: list[str]) -> list[str]:
    valid = question.valid_values()
    unknown = [v for v in values if v not in valid]
    if unknown:
        raise ValidationError(
            f"{question.id}: {unknown!r} are not options of this question. "
            f"Valid: {sorted(valid)}."
        )
    exclusives = [v for v in values if (o := question.option(v)) and o.exclusive]
    if exclusives:
        # "None of these" plus a symptom is a UI bug or a mis-tap. Take the exclusive answer:
        # it is the one the patient pressed most recently in every client we ship.
        return exclusives[:1]
    return values


def record_answer(
    machine: DialogueMachine,
    ledger: FactLedger,
    *,
    turn_id: str,
    question_id: str,
    value: Any,
    modality: Modality,
    transcript: str | None = None,
    asr_confidence: float | None = None,
    audio_ref: str | None = None,
    language: str | None = None,
) -> list[Fact]:
    """Record one answer. Returns the facts written — possibly several, for a multi-select."""
    ontology: Ontology = machine.ontology
    question = ontology.by_id.get(question_id)
    if question is None:
        raise ValidationError(f"{question_id!r} is not a question in the loaded ontology.")

    language = language or machine.state.language
    known = ontology.known_paths

    if modality is Modality.TOUCH:
        return _record_tapped(
            ledger, question, value, turn_id, language, known, machine
        )
    return _record_spoken_or_typed(
        ledger, question, value, turn_id, language, known, machine,
        transcript=transcript, modality=modality,
        asr_confidence=asr_confidence, audio_ref=audio_ref,
    )


def _record_tapped(
    ledger: FactLedger,
    question: Question,
    value: Any,
    turn_id: str,
    language: str,
    known: set[str],
    machine: DialogueMachine,
) -> list[Fact]:
    selected: tuple[str, ...] | None = None

    if question.kind in ("single_choice", "duration"):
        values = _validate_choice(question, [str(value)])
        verbatim = _labels_for(question, values, language)
        recorded = values[0]
        selected = tuple(values)
    elif question.kind == "multi_choice":
        values = _validate_choice(question, [str(v) for v in (value or [])])
        if not values:
            raise ValidationError(f"{question.id}: a multi-select answer cannot be empty.")
        verbatim = _labels_for(question, values, language)
        recorded = values
        selected = tuple(values)
    elif question.kind == "boolean":
        recorded = bool(value)
        verbatim = "Yes" if recorded else "No"
    elif question.kind == "scale":
        assert question.scale is not None
        number = int(value)
        if not question.scale.min <= number <= question.scale.max:
            raise ValidationError(
                f"{question.id}: {number} is outside the scale "
                f"{question.scale.min}–{question.scale.max}."
            )
        anchors = question.scale.anchors_hi if language == "hi" else question.scale.anchors_en
        anchor = anchors[min(number * len(anchors) // (question.scale.max + 1), len(anchors) - 1)] if anchors else ""
        recorded = number
        verbatim = f"{anchor} ({number} of {question.scale.max})".strip()
    elif question.options:
        # An open_text question that also renders tap options (the chief complaint does).
        # A tap on it is still a tap: it must name a rendered option, not free text.
        values = _validate_choice(question, [str(value)])
        verbatim = _labels_for(question, values, language)
        recorded = values[0]
        selected = tuple(values)
    else:
        recorded = str(value)
        verbatim = str(value)

    span = utterance_span(
        verbatim=verbatim, turn_id=turn_id, question_id=question.id,
        modality=Modality.TOUCH, language=language, selected_values=selected,
    )
    fact = record_fact(
        ledger, path=question.path, value=recorded,
        tier=SourceTier.CONFIRMED, source=span, confidence=TOUCH_CONFIDENCE,
        provenance_note="kiosk-tap", known_paths=known,
    )
    machine.mark_answered(turn_id, recorded, Modality.TOUCH.value)
    machine.state.values[question.path] = recorded
    return [fact]


def _record_spoken_or_typed(
    ledger: FactLedger,
    question: Question,
    value: Any,
    turn_id: str,
    language: str,
    known: set[str],
    machine: DialogueMachine,
    *,
    transcript: str | None,
    modality: Modality,
    asr_confidence: float | None,
    audio_ref: str | None,
) -> list[Fact]:
    """Free text. The verbatim IS the answer, so provenance is trivially exact here."""
    text = str(value).strip()
    if not text:
        raise ValidationError(f"{question.id}: an empty answer cannot be recorded.")

    span = utterance_span(
        verbatim=text, turn_id=turn_id, question_id=question.id,
        modality=modality, full_text=transcript or text, language=language,
        asr_confidence=asr_confidence, audio_ref=audio_ref,
    )
    confidence = (
        asr_confidence if (modality is Modality.SPEECH and asr_confidence is not None)
        else TYPED_CONFIDENCE
    )
    # A patient who narrates rather than taps is *stating*, not confirming.
    fact = record_fact(
        ledger, path=question.path, value=text,
        tier=SourceTier.STATED, source=span, confidence=confidence,
        provenance_note=f"kiosk-{modality.value}", known_paths=known,
    )
    machine.mark_answered(turn_id, text, modality.value)
    machine.state.values[question.path] = text
    return [fact]


def record_derived(
    machine: DialogueMachine, ledger: FactLedger, question: Question, value: str
) -> Fact:
    """Record a `derived` answer (e.g. Vaya from date of birth).

    The source span names the input it was computed from, so the physician sees
    "derived from age 64" rather than an unexplained value. It is `confirmed` tier because
    the patient confirmed their identity at ABHA login, which is where the age came from.
    """
    source_value = machine._condition_values().get(question.derive_from or "")
    verbatim = f"{value} (derived from {question.derive_from} = {source_value})"
    span = utterance_span(
        verbatim=verbatim, turn_id=f"derived_{question.id}", question_id=question.id,
        modality=Modality.TOUCH, language=machine.state.language,
    )
    fact = record_fact(
        ledger, path=question.path, value=value, tier=SourceTier.CONFIRMED,
        source=span, confidence=1.0, provenance_note=f"derived:{question.derive_from}",
        known_paths=machine.ontology.known_paths,
    )
    machine.state.values[question.path] = value
    return fact

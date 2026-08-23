"""Spoken answers, end to end — Phase 3.

One function, one decision: is this transcript good enough to record?

* **Reliable** (confidence ≥ threshold) → extract slots and record with the ASR confidence
  carried onto every fact, so a physician can see a value came from a 0.71 transcript.
* **Unreliable** → record nothing, mark the question touch-only, re-present it. The patient
  sees big buttons and a short audio prompt saying we did not catch that.
* **Empty** → the microphone heard nothing. Same as unreliable, but a different prompt,
  because "I didn't hear you" and "I didn't understand you" need different responses from
  the patient.

Barge-in is handled client-side (the kiosk stops TTS the moment the mic detects speech) and
recorded here only as a flag on the turn, because whether the patient interrupted the prompt
is genuinely useful when reviewing an odd answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.contracts.provenance import Fact, Modality
from app.contracts.record import FactLedger
from app.core.config import settings
from app.core.logging import get_logger
from app.llm.extraction import ExtractionOutcome, extract
from app.modules.dialogue.machine import DialogueMachine
from app.speech.protocol import Transcript

log = get_logger(__name__)

DEGRADE_PROMPTS: dict[str, dict[str, str]] = {
    "unclear": {
        "en": "Sorry, I did not catch that clearly. Please tap your answer below.",
        "hi": "माफ़ कीजिए, मैं ठीक से समझ नहीं पाया। कृपया नीचे अपना उत्तर दबाइए।",
        "ta": "மன்னிக்கவும், தெளிவாகக் கேட்கவில்லை. கீழே உங்கள் பதிலைத் தொடவும்.",
    },
    "silence": {
        "en": "I could not hear anything. Please tap your answer, or try speaking again.",
        "hi": "मुझे कुछ सुनाई नहीं दिया। कृपया अपना उत्तर दबाइए, या फिर से बोलिए।",
        "ta": "எதுவும் கேட்கவில்லை. உங்கள் பதிலைத் தொடவும், அல்லது மீண்டும் பேசவும்.",
    },
}


@dataclass(slots=True)
class VoiceOutcome:
    accepted: bool
    degraded_to_touch: bool
    reason: str | None
    transcript: Transcript
    facts: list[Fact]
    extraction: ExtractionOutcome | None
    prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "degradedToTouch": self.degraded_to_touch,
            "reason": self.reason,
            "transcript": self.transcript.to_dict(),
            "factsRecorded": len(self.facts),
            "extraction": self.extraction.to_dict() if self.extraction else None,
            "prompt": self.prompt,
        }


def handle_spoken_answer(
    machine: DialogueMachine,
    ledger: FactLedger,
    *,
    turn_id: str,
    question_id: str,
    transcript: Transcript,
    audio_ref: str | None = None,
    barge_in: bool = False,
) -> VoiceOutcome:
    """Record a spoken answer, or degrade this question to touch. Never guesses."""
    question = machine.ontology.by_id.get(question_id)
    if question is None:
        raise ValueError(f"{question_id!r} is not a question in the loaded ontology.")

    language = machine.state.language

    if transcript.empty:
        return _degrade(machine, question_id, transcript, "silence", language)

    if not transcript.reliable:
        log.info(
            "voice.degraded",
            question=question_id,
            confidence=round(transcript.confidence, 3),
            threshold=settings.asr_confidence_threshold,
        )
        return _degrade(machine, question_id, transcript, "unclear", language)

    outcome = extract(
        question=question,
        utterance=transcript.text,
        ontology=machine.ontology,
        ledger=ledger,
        turn_id=turn_id,
        language=language,
        asr_confidence=transcript.confidence,
        audio_ref=audio_ref,
        modality=Modality.SPEECH,
    )

    if not outcome.facts:
        # Heard clearly, understood nothing. Not the patient's fault and not a reason to
        # guess: fall back to touch with the same prompt as an unclear transcript.
        return _degrade(
            machine, question_id, transcript, "unclear", language, extraction=outcome
        )

    machine.mark_answered(turn_id, transcript.text, Modality.SPEECH.value)
    turn = machine.current_turn(turn_id)
    if turn is not None and barge_in:
        turn.skipped_reason = "barge_in"
    for fact in outcome.facts:
        machine.state.values[fact.path] = fact.value

    return VoiceOutcome(
        accepted=True, degraded_to_touch=False, reason=None,
        transcript=transcript, facts=outcome.facts, extraction=outcome,
    )


def _degrade(
    machine: DialogueMachine,
    question_id: str,
    transcript: Transcript,
    reason: str,
    language: str,
    extraction: ExtractionOutcome | None = None,
) -> VoiceOutcome:
    machine.force_touch(question_id)
    prompts = DEGRADE_PROMPTS[reason]
    return VoiceOutcome(
        accepted=False,
        degraded_to_touch=True,
        reason=reason,
        transcript=transcript,
        facts=[],
        extraction=extraction,
        prompt=prompts.get(language, prompts["en"]),
    )

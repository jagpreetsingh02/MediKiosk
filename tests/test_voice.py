"""Phase 3 — voice, and specifically the refusal to guess at a bad transcript."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from app.core.config import settings
from app.modules.dialogue.voice import handle_spoken_answer
from app.speech.client import ClientSpeechBackend
from app.speech.protocol import Transcript
from app.speech.registry import describe, get_speech


def _transcript(text: str, confidence: float, language: str = "en") -> Transcript:
    return Transcript(
        text=text,
        confidence=confidence,
        language=language,
        backend="test",
        empty=not text.strip(),
    )


def _advance_to(machine, question_id: str):
    while (q := machine.next_question()) is not None:
        if q.question_id == question_id:
            return q
        machine.decline(q.question_id)
    raise AssertionError(f"never reached {question_id}")


def test_reliable_transcript_is_recorded_with_its_confidence(machine, ledger) -> None:
    q = _advance_to(machine, "hpi.site")
    outcome = handle_spoken_answer(
        machine,
        ledger,
        turn_id=q.turn_id,
        question_id="hpi.site",
        transcript=_transcript("mere chhaati mein dard hai", 0.88),
    )
    assert outcome.accepted and not outcome.degraded_to_touch
    assert outcome.facts[0].value == "chest"
    assert outcome.facts[0].confidence <= 0.88
    assert outcome.facts[0].source.asr_confidence == pytest.approx(0.88)


def test_low_confidence_degrades_to_touch_and_records_nothing(machine, ledger) -> None:
    q = _advance_to(machine, "hpi.site")
    outcome = handle_spoken_answer(
        machine,
        ledger,
        turn_id=q.turn_id,
        question_id="hpi.site",
        transcript=_transcript("mere chhaati mein dard hai", 0.31),
    )
    assert not outcome.accepted
    assert outcome.degraded_to_touch and outcome.reason == "unclear"
    assert not ledger.active_facts(), "a low-confidence transcript must record nothing"
    assert outcome.prompt


def test_silence_gets_a_different_prompt_from_a_bad_transcript(machine, ledger) -> None:
    q = _advance_to(machine, "hpi.site")
    silence = handle_spoken_answer(
        machine,
        ledger,
        turn_id=q.turn_id,
        question_id="hpi.site",
        transcript=_transcript("", 0.0),
    )
    assert silence.reason == "silence"
    assert silence.prompt != _degraded_prompt_for_unclear(machine, ledger)


def _degraded_prompt_for_unclear(machine, ledger) -> str:
    from app.modules.dialogue.voice import DEGRADE_PROMPTS

    return DEGRADE_PROMPTS["unclear"]["en"]


def test_degradation_is_per_question_not_sticky(machine, ledger) -> None:
    """A patient misheard once must still be offered the microphone next question."""
    q = _advance_to(machine, "hpi.site")
    handle_spoken_answer(
        machine,
        ledger,
        turn_id=q.turn_id,
        question_id="hpi.site",
        transcript=_transcript("mumble", 0.2),
    )
    assert "hpi.site" in machine.state.forced_touch

    again = machine.next_question()
    assert again is not None and again.question_id == "hpi.site"
    assert again.touch_only, "the failed question re-presents as touch-only"

    from app.contracts.provenance import Modality
    from app.modules.dialogue.answers import record_answer

    record_answer(
        machine,
        ledger,
        turn_id=again.turn_id,
        question_id="hpi.site",
        value="chest",
        modality=Modality.TOUCH,
    )
    following = machine.next_question()
    assert following is not None
    assert not following.touch_only, "degradation must not carry over to the next question"


def test_heard_clearly_but_understood_nothing_also_degrades(machine, ledger) -> None:
    q = _advance_to(machine, "hpi.site")
    outcome = handle_spoken_answer(
        machine,
        ledger,
        turn_id=q.turn_id,
        question_id="hpi.site",
        transcript=_transcript("the weather is nice today", 0.95),
    )
    assert outcome.degraded_to_touch and not ledger.active_facts()


def test_degradation_prompt_is_in_the_session_language(ledger) -> None:
    from app.modules.dialogue.machine import DialogueMachine, DialogueState

    machine = DialogueMachine(DialogueState(session_id="s", language="hi"), ledger)
    q = _advance_to(machine, "hpi.site")
    outcome = handle_spoken_answer(
        machine,
        ledger,
        turn_id=q.turn_id,
        question_id="hpi.site",
        transcript=_transcript("bilkul samajh nahi aaya", 0.1, language="hi"),
    )
    assert outcome.prompt and "कृपया" in outcome.prompt


def test_client_backend_applies_the_same_confidence_policy() -> None:
    backend = ClientSpeechBackend()
    good = backend.accept(text="chest pain", confidence=0.9, language="en")
    bad = backend.accept(text="chest pain", confidence=0.4, language="en")
    assert good.reliable and not bad.reliable


def test_client_backend_rejects_an_out_of_range_confidence() -> None:
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        ClientSpeechBackend().accept(text="x", confidence=1.7, language="en")


def test_threshold_is_configurable_and_reported() -> None:
    described = describe()
    assert described["asrConfidenceThreshold"] == settings.asr_confidence_threshold
    assert "touch" in str(described["degradationPolicy"])


def test_tts_produces_audio_or_says_it_could_not() -> None:
    """Never silence-without-a-flag: a patient who hears nothing cannot use the kiosk."""
    utterance = get_speech().synthesise("What is troubling you today?", language="en")
    assert utterance.audio or utterance.client_fallback


# ------------------------------------------------------------------ audio fixtures

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "audio"


def test_noisy_audio_fixtures_exist_and_are_real_wav() -> None:
    files = sorted(FIXTURES.glob("*.wav"))
    assert len(files) >= 9, "the noisy-audio fixture set is missing"
    for path in files:
        with wave.open(str(path), "rb") as handle:
            assert handle.getnframes() > 0
            assert handle.getsampwidth() == 2


@pytest.mark.parametrize("snr_tag", ["snr15", "snr05", "snr00"])
def test_noise_is_actually_present_and_scales_with_snr(snr_tag: str) -> None:
    """Guards the fixtures themselves: a 'noisy' file identical to the clean one proves nothing."""
    import struct

    def energy(path: Path) -> float:
        with wave.open(str(path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
        samples = struct.unpack(f"<{len(frames) // 2}h", frames)
        return sum(s * s for s in samples) / max(len(samples), 1)

    clean = energy(FIXTURES / "clean_en_chestpain.wav")
    noisy = energy(FIXTURES / f"noisy_en_chestpain_{snr_tag}.wav")
    assert noisy > clean, f"{snr_tag} fixture carries no added noise"


# ------------------------------------------------------------------ model unavailable


def test_unreachable_model_degrades_to_touch_rather_than_erroring(
    machine, ledger, monkeypatch
) -> None:
    """The claim the deterministic spine exists to make, pinned as a test.

    A real Groq rate-limit in the eval harness produced a 503 to the patient instead of a
    fallback. From where the patient is standing, "the model is down" and "I was not heard"
    are the same event: the machine did not understand, and the buttons still work.
    """
    import app.modules.dialogue.voice as voice_module
    from app.core.errors import UpstreamUnavailable

    def unreachable(**_kwargs):
        raise UpstreamUnavailable("Groq call failed after 5 attempts: 429 Too Many Requests")

    monkeypatch.setattr(voice_module, "extract", unreachable)

    q = _advance_to(machine, "hpi.site")
    outcome = handle_spoken_answer(
        machine, ledger, turn_id=q.turn_id, question_id="hpi.site",
        transcript=_transcript("mere chhaati mein dard hai", 0.95),
    )
    assert not outcome.accepted
    assert outcome.degraded_to_touch
    assert outcome.reason == "service"
    assert outcome.prompt
    assert not ledger.active_facts(), "nothing may be recorded when the model is unreachable"


def test_malformed_model_output_also_degrades(machine, ledger, monkeypatch) -> None:
    import app.modules.dialogue.voice as voice_module
    from app.core.errors import LLMContractError

    def garbage(**_kwargs):
        raise LLMContractError("stub-model returned text that is not JSON")

    monkeypatch.setattr(voice_module, "extract", garbage)

    q = _advance_to(machine, "hpi.site")
    outcome = handle_spoken_answer(
        machine, ledger, turn_id=q.turn_id, question_id="hpi.site",
        transcript=_transcript("chest pain", 0.95),
    )
    assert outcome.degraded_to_touch and outcome.reason == "service"


def test_the_interview_completes_with_the_model_dead(monkeypatch) -> None:
    """End to end: unplug the model, answer everything by tap, get a complete history."""
    import app.modules.dialogue.voice as voice_module
    from app.contracts.provenance import Modality
    from app.contracts.record import FactLedger
    from app.core.errors import UpstreamUnavailable
    from app.modules.dialogue.answers import record_answer
    from app.modules.dialogue.machine import DialogueMachine, DialogueState

    monkeypatch.setattr(
        voice_module, "extract",
        lambda **_kwargs: (_ for _ in ()).throw(UpstreamUnavailable("model is down")),
    )

    state = DialogueState(session_id="dead-model", language="en")
    ledger = FactLedger("dead-model")
    machine = DialogueMachine(state, ledger)

    taps = {
        "cc.text": "pain", "cc.duration": "days_1_3", "hpi.site": "chest",
        "hpi.onset": "sudden", "hpi.associated": ["sweating"], "hpi.severity": 8,
    }
    guard = 0
    spoken_attempts = 0
    while (question := machine.next_question()) is not None and guard < 120:
        guard += 1
        if question.question_id in taps:
            # Try speech first on every answerable question; it always fails.
            if not question.touch_only:
                spoken_attempts += 1
                handle_spoken_answer(
                    machine, ledger, turn_id=question.turn_id,
                    question_id=question.question_id,
                    transcript=_transcript("something spoken", 0.95),
                )
                question = machine.next_question()
                assert question is not None
            record_answer(
                machine, ledger, turn_id=question.turn_id,
                question_id=question.question_id,
                value=taps[question.question_id], modality=Modality.TOUCH,
            )
        else:
            machine.decline(question.question_id)

    assert spoken_attempts >= 5, "the test did not actually exercise the failing model"
    assert len(ledger.active_facts()) == len(taps)
    assert state.completed

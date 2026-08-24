"""Groq-hosted Whisper — real server-side ASR, on the same key as the extraction model.

This was not in the original plan. It went in because Groq turned out to host
`whisper-large-v3-turbo`, which gives genuine multilingual recognition for every language the
kiosk offers, with no extra credential and no Vosk model download. That makes it a better
default *server-side* backend than the Vosk path, which needs a 50 MB model per language.

It does **not** displace the client backend. The shipped kiosk still recognises on-device
(browser Web Speech API) because that path works with the network unplugged, which is the
scenario the demo has to survive. This backend is what serves:

  - clients that cannot do on-device recognition (a plain Android WebView, a kiosk browser
    with no speech support);
  - the eval harness, when measuring recognition rather than the degradation policy;
  - any deployment that would rather not do recognition on a shared device.

Whisper returns no per-word confidence and no utterance confidence. That is a real problem for
a system whose whole ASR policy is confidence-driven, and it is handled explicitly rather than
papered over — see `_confidence_from`.
"""
from __future__ import annotations

import io
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.core.logging import get_logger
from app.speech.protocol import Transcript, Utterance

log = get_logger(__name__)

#: Whisper's `avg_logprob` per segment, mapped onto [0, 1]. The mapping is a judgement call
#: and is stated here rather than buried: -0.1 is a confident segment, -1.0 is a poor one.
#: Anything below the kiosk threshold degrades to touch exactly as any other backend would.
_LOGPROB_CONFIDENT = -0.10
_LOGPROB_POOR = -1.00


class GroqWhisperSpeechBackend:
    """Satisfies `SpeechBackend`."""

    name = "groq-whisper"
    offline = False
    languages: tuple[str, ...] = (
        "en", "hi", "bn", "ta", "te", "mr", "kn", "ml", "gu", "pa", "or", "as", "ur",
    )

    def __init__(self) -> None:
        if not settings.groq_api_key:
            raise UpstreamUnavailable(
                "GROQ_API_KEY is not set, so the Whisper backend cannot be used. "
                "The local backend is used instead."
            )
        self.model = settings.groq_asr_model

    # -------------------------------------------------------------- ASR

    def transcribe(self, audio: bytes, *, language: str, media_type: str) -> Transcript:
        if not audio:
            return Transcript(
                text="", confidence=0.0, language=language, backend=self.name, empty=True
            )
        try:
            response = httpx.post(
                f"{settings.groq_base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": ("audio.wav", io.BytesIO(audio), media_type or "audio/wav")},
                data={
                    "model": self.model,
                    "language": language,
                    "response_format": "verbose_json",
                    # Segment granularity is what carries avg_logprob, which is the only
                    # confidence signal Whisper exposes at all.
                    "timestamp_granularities[]": "segment",
                    "temperature": "0",
                },
                timeout=settings.groq_timeout_seconds * 2,
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"Groq Whisper call failed: {exc}") from exc

        text = str(body.get("text", "")).strip()
        segments = body.get("segments") or []
        confidence = _confidence_from(segments)

        log.info(
            "speech.whisper",
            model=self.model, language=language, chars=len(text),
            segments=len(segments),
            confidence=round(confidence, 3) if confidence is not None else "unavailable",
        )
        return Transcript(
            text=text,
            confidence=confidence,
            language=str(body.get("language", language))[:8],
            backend=self.name,
            duration_ms=int(float(body.get("duration", 0.0)) * 1000),
            empty=not text,
        )

    # -------------------------------------------------------------- TTS

    def synthesise(self, text: str, *, language: str) -> Utterance:
        """Whisper is recognition only. Groq hosts no TTS voice for Indian languages, so
        synthesis stays with the client (`speechSynthesis`), which every target device has."""
        return Utterance(
            audio=b"",
            media_type="audio/wav",
            text=text,
            language=language,
            backend=f"{self.name}:client-tts",
            client_fallback=True,
        )


def _confidence_from(segments: list[dict[str, Any]]) -> float | None:
    """Derive an utterance confidence from Whisper's per-segment statistics.

    Whisper does not report a confidence. Inventing a high one would silently disable the
    degradation policy for this backend, which is the single most dangerous thing a speech
    integration can do here — every low-quality transcript would be recorded as fact.

    Two signals are used, and both are real:

    * ``avg_logprob`` — the model's own average token log-probability for the segment.
    * ``no_speech_prob`` — how likely the segment is to be silence or noise.

    They are combined conservatively (the worse of the two governs), so a segment Whisper
    thinks might be noise cannot be rescued by a good logprob.
    """
    if not segments:
        # No segment statistics means no measurement. Returning the threshold would be
        # inventing one; the caller handles `unavailable`.
        return None

    scores: list[float] = []
    for segment in segments:
        logprob = float(segment.get("avg_logprob", _LOGPROB_POOR))
        no_speech = float(segment.get("no_speech_prob", 0.0))

        span = _LOGPROB_CONFIDENT - _LOGPROB_POOR
        from_logprob = (logprob - _LOGPROB_POOR) / span if span else 0.0
        from_logprob = max(0.0, min(1.0, from_logprob))

        scores.append(min(from_logprob, 1.0 - no_speech))

    # Mean over segments, then a mild penalty for a single very poor segment: one badly heard
    # phrase in the middle of a sentence is exactly where a dosage or a duration goes wrong.
    mean = sum(scores) / len(scores)
    worst = min(scores)
    combined = 0.75 * mean + 0.25 * worst
    return round(max(0.0, min(1.0, combined)), 4)


def logprob_to_confidence(avg_logprob: float) -> float:
    """Exposed for tests and for tuning the mapping against real recordings."""
    span = _LOGPROB_CONFIDENT - _LOGPROB_POOR
    return round(max(0.0, min(1.0, (avg_logprob - _LOGPROB_POOR) / span)), 4)

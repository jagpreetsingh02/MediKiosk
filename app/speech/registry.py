"""Speech backend selection. Local first, always — the demo must not need a network."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.speech.client import ClientSpeechBackend
from app.speech.local import LocalSpeechBackend
from app.speech.protocol import SpeechBackend

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_speech() -> SpeechBackend:
    if settings.speech_backend == "bhashini":
        from app.speech.bhashini import BhashiniSpeechBackend

        try:
            return BhashiniSpeechBackend()
        except Exception as exc:
            log.warning("speech.bhashini_unavailable", error=str(exc)[:200])
            return LocalSpeechBackend()
    if settings.speech_backend == "client":
        return ClientSpeechBackend()
    return LocalSpeechBackend()


@lru_cache(maxsize=1)
def get_client_backend() -> ClientSpeechBackend:
    """Always available: the kiosk posts on-device transcripts through this path."""
    return ClientSpeechBackend()


def describe() -> dict[str, object]:
    backend = get_speech()
    return {
        "name": backend.name,
        "offline": backend.offline,
        "languages": list(backend.languages),
        "configured": settings.speech_backend,
        "asrConfidenceThreshold": settings.asr_confidence_threshold,
        "degradationPolicy": (
            "Below the threshold the question falls back to touch and is re-presented. "
            "Degradation is per-question and never sticky."
        ),
    }

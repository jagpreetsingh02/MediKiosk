"""Backend selection. Decided once, at startup, and reported in `/about`."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.offline import OfflineLLM
from app.llm.protocol import LLMBackend

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> LLMBackend:
    """`offline` always works. `groq` requires a key. `auto` prefers Groq, falls back quietly.

    The fallback happens here, at startup, exactly once — never mid-request. A demo that
    starts with no key runs entirely on rules and says so; it does not discover this halfway
    through a patient's interview.
    """
    if settings.llm_backend == "offline":
        return OfflineLLM()

    if settings.llm_backend in ("auto", "groq"):
        if not settings.groq_api_key:
            if settings.llm_backend == "groq":
                log.warning("llm.groq_requested_without_key", falling_back_to="offline")
            return OfflineLLM()
        from app.llm.groq import GroqLLM

        try:
            backend = GroqLLM()
            log.info("llm.backend", name=backend.name, offline=False)
            return backend
        except Exception as exc:
            log.warning("llm.groq_unavailable", error=str(exc)[:200], falling_back_to="offline")
            return OfflineLLM()

    return OfflineLLM()


def describe() -> dict[str, object]:
    backend = get_llm()
    return {
        "name": backend.name,
        "version": backend.version,
        "offline": backend.offline,
        "configured": settings.llm_backend,
        "note": (
            "Deterministic rule-based extractor. No network, no model." if backend.offline
            else "Hosted model. All output is JSON-schema validated; a parse failure discards "
                 "the extraction rather than falling back to free text."
        ),
    }

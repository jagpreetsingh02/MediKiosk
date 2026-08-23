"""Groq backend. JSON mode, temperature 0, and a hard failure on anything unparseable.

Two things worth stating about the configuration, because both are load-bearing:

* **temperature 0.** Extraction is not a creative task. A model that phrases the same
  utterance two ways across two runs makes the eval harness meaningless.
* **`response_format=json_object`.** Combined with `parse_or_fail()` this means there is no
  path from "the model said something odd" to "an odd thing is in the patient's record".

A failed call raises. It never returns a partial result and never silently falls back to the
offline extractor mid-request: a silent backend switch would make the eval numbers a lie about
which backend produced them. The *session* can be configured to use the offline backend; a
single call cannot switch under you.
"""

from __future__ import annotations

import random
import time

import httpx

from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.core.logging import get_logger
from app.llm.protocol import LLMResponse

log = get_logger(__name__)


class GroqLLM:
    """Satisfies `LLMBackend`."""

    offline = False

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.groq_api_key
        self.name = model or settings.groq_model
        self.version = settings.icd_release_id  # stamped; Groq exposes no model build id
        if not self.api_key:
            raise UpstreamUnavailable(
                "GROQ_API_KEY is not set. Set it in .env, or run with LLM_BACKEND=offline."
            )

    def complete(self, *, system: str, user: str, schema_hint: str) -> LLMResponse:
        started = time.perf_counter()
        payload = {
            "model": self.name,
            "temperature": settings.llm_temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": f"{system}\n\nReturn JSON only:\n{schema_hint}"},
                {"role": "user", "content": user},
            ],
        }
        last_error: Exception | None = None
        for attempt in range(settings.groq_max_retries + 1):
            try:
                response = httpx.post(
                    f"{settings.groq_base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=settings.groq_timeout_seconds,
                )
                if response.status_code == 429 and attempt < settings.groq_max_retries:
                    # Rate limited. Honour Retry-After when the API sends one; otherwise back
                    # off exponentially with jitter. Retrying immediately three times, which
                    # is what the first version did, is indistinguishable from not retrying.
                    delay = _retry_after(response) or (
                        settings.groq_retry_base_seconds * (2**attempt)
                        + random.uniform(0, 0.4)
                    )
                    log.warning(
                        "groq.rate_limited", attempt=attempt, sleeping=round(delay, 2)
                    )
                    time.sleep(min(delay, settings.groq_max_backoff_seconds))
                    continue
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
                return LLMResponse(
                    text=text,
                    model_name=self.name,
                    model_version=self.version,
                    prompt=f"{system}\n{user}",
                    offline=False,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_error = exc
                log.warning("groq.retry", attempt=attempt, error=str(exc)[:200])
                if attempt < settings.groq_max_retries:
                    time.sleep(settings.groq_retry_base_seconds * (2**attempt))
        raise UpstreamUnavailable(
            f"Groq call failed after {settings.groq_max_retries + 1} attempts: {last_error}"
        )


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds the API asked us to wait, if it said. Groq sends this on 429."""
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None

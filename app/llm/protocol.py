"""The LLM boundary. Two backends behind one protocol, chosen at startup.

Everything crossing this boundary is JSON validated against a Pydantic model. A parse failure
is a hard failure — :class:`LLMContractError` — and never a silent fallback to free text. If
the model returns prose where a schema was demanded, the correct behaviour is to lose the
extraction and keep the deterministic answer, not to guess at what it meant.

`LLMResponse` carries the model name, version and prompt hash so `record_ai_call()` can write
an audit row for every single call (Invariant 6). There is no code path that calls a model
without producing one of these.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import LLMContractError


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model_name: str
    model_version: str
    prompt: str
    #: True when the deterministic offline backend answered. Surfaced in the API so a
    #: demo audience can see which path is live.
    offline: bool
    latency_ms: int = 0


class LLMBackend(Protocol):
    name: str
    version: str
    offline: bool

    def complete(self, *, system: str, user: str, schema_hint: str) -> LLMResponse: ...


def parse_or_fail[T: BaseModel](response: LLMResponse, model: type[T]) -> T:
    """Validate the model's JSON against `model`. No repair, no retry-with-prose, no fallback."""
    import json

    text = response.text.strip()
    # Models fence JSON even when told not to. Stripping a fence is not repair; it is
    # unwrapping. Anything beyond that is refused.
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.removeprefix("json").strip()
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMContractError(
            f"{response.model_name} returned text that is not JSON: {exc}. "
            "Extraction is discarded; the deterministic answer stands."
        ) from exc
    try:
        return model.model_validate(payload)
    except PydanticValidationError as exc:
        raise LLMContractError(
            f"{response.model_name} returned JSON that does not match {model.__name__}: "
            f"{exc.error_count()} error(s). Extraction is discarded."
        ) from exc

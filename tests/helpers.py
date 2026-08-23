"""Shared test helpers. Kept out of conftest so the eval harness can import them too."""

from __future__ import annotations

from typing import Any

from app.contracts.provenance import Modality, SourceTier
from app.contracts.record import FactLedger, record_fact, utterance_span


def tap(
    ledger: FactLedger, path: str, value: Any, *, question_id: str = "q", turn_id: str = "t"
) -> None:
    """Record a tapped answer the way the kiosk would, with real selection evidence."""
    values = value if isinstance(value, list) else [value]
    if isinstance(value, bool | int | float):
        span = utterance_span(
            verbatim=str(value),
            turn_id=turn_id,
            question_id=question_id,
            modality=Modality.TOUCH,
        )
    else:
        span = utterance_span(
            verbatim=", ".join(str(v) for v in values),
            turn_id=turn_id,
            question_id=question_id,
            modality=Modality.TOUCH,
            selected_values=tuple(str(v) for v in values),
        )
    record_fact(
        ledger,
        path=path,
        value=value,
        tier=SourceTier.CONFIRMED,
        source=span,
        confidence=1.0,
    )


def say(
    ledger: FactLedger,
    path: str,
    value: Any,
    verbatim: str,
    *,
    question_id: str = "q",
    turn_id: str = "t",
    vocabulary: set[str] | None = None,
) -> None:
    """Record a spoken answer with the patient's own words as the span."""
    record_fact(
        ledger,
        path=path,
        value=value,
        tier=SourceTier.STATED,
        source=utterance_span(
            verbatim=verbatim,
            turn_id=turn_id,
            question_id=question_id,
            modality=Modality.SPEECH,
        ),
        confidence=0.85,
        coded_value_of=vocabulary,
    )

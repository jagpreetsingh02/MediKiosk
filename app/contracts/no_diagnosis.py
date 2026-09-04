"""⛔ Invariant 1 — the system never diagnoses.

Two enforcement points:

1. **Shape.** ``ClinicalHistory`` has no assessment-shaped field, and
   ``tests/test_invariant_no_diagnosis.py`` scans the contract module for one.
2. **Wire.** :func:`assert_no_assessment` runs over every outbound clinical payload in
   ``app/api``. A field named ``differential`` cannot reach a client even if someone adds it
   to a dict along the way.

The check is on *field names and shapes*, not on prose: the patient is free to say "the doctor
told me I have diabetes", and that is recorded as reported history under ``past_medical``. The
line is that Swastra never *originates* an assessment of its own.
"""

from __future__ import annotations

from typing import Any

from app.contracts.history import FORBIDDEN_CLINICAL_FIELDS
from app.core.errors import DiagnosisAttempt


def assert_no_assessment(payload: Any, *, where: str = "response") -> None:
    """Walk a JSON-able payload and raise if any key names an assessment."""
    offenders = scan_for_assessment_language(payload)
    if offenders:
        key, trail = offenders[0]
        raise DiagnosisAttempt(
            f"{where} carries a field named {key!r} at {trail}. Swastra produces a "
            "history, never an assessment. The physician diagnoses."
        )


def scan_for_assessment_language(payload: Any) -> list[tuple[str, str]]:
    """The same walk as `assert_no_assessment`, but COLLECTING rather than raising.

    Exists for the auditor screen: a live check that a physician or a judge can watch run
    against a real report, and see either "clean" or exactly which field and path tripped it.
    Raising on the first hit is right for enforcement, where the caller just needs to be
    stopped; a person reviewing a report wants to see all of it, not fix-one-rerun-repeat.

    `assert_no_assessment` is now a wrapper over this, so there is exactly one definition of
    "assessment-shaped" — the auditor's live check and the enforcement path can never drift
    apart and disagree about what counts.
    """
    offenders: list[tuple[str, str]] = []
    _walk(payload, trail="$", offenders=offenders)
    return offenders


def _walk(node: Any, *, trail: str, offenders: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).casefold()
            if lowered in FORBIDDEN_CLINICAL_FIELDS:
                offenders.append((str(key), trail))
            _walk(value, trail=f"{trail}.{key}", offenders=offenders)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk(item, trail=f"{trail}[{index}]", offenders=offenders)

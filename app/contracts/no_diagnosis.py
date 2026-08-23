"""⛔ Invariant 1 — the system never diagnoses.

Two enforcement points:

1. **Shape.** ``ClinicalHistory`` has no assessment-shaped field, and
   ``tests/test_invariant_no_diagnosis.py`` scans the contract module for one.
2. **Wire.** :func:`assert_no_assessment` runs over every outbound clinical payload in
   ``app/api``. A field named ``differential`` cannot reach a client even if someone adds it
   to a dict along the way.

The check is on *field names and shapes*, not on prose: the patient is free to say "the doctor
told me I have diabetes", and that is recorded as reported history under ``past_medical``. The
line is that MediKiosk never *originates* an assessment of its own.
"""

from __future__ import annotations

from typing import Any

from app.contracts.history import FORBIDDEN_CLINICAL_FIELDS
from app.core.errors import DiagnosisAttempt


def assert_no_assessment(payload: Any, *, where: str = "response") -> None:
    """Walk a JSON-able payload and raise if any key names an assessment."""
    _walk(payload, where=where, trail="$")


def _walk(node: Any, *, where: str, trail: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).casefold()
            if lowered in FORBIDDEN_CLINICAL_FIELDS:
                raise DiagnosisAttempt(
                    f"{where} carries a field named {key!r} at {trail}. MediKiosk produces a "
                    "history, never an assessment. The physician diagnoses."
                )
            _walk(value, where=where, trail=f"{trail}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk(item, where=where, trail=f"{trail}[{index}]")

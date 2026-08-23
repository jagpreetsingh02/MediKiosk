"""Invariant 1 — the system never diagnoses."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.contracts.history import FORBIDDEN_CLINICAL_FIELDS, ClinicalHistory
from app.contracts.no_diagnosis import assert_no_assessment
from app.core.errors import DiagnosisAttempt


def _all_field_names(model: type, seen: set[type] | None = None) -> set[str]:
    seen = seen or set()
    if model in seen or not hasattr(model, "model_fields"):
        return set()
    seen.add(model)
    names: set[str] = set()
    for name, field in model.model_fields.items():
        names.add(name)
        annotation = field.annotation
        for candidate in (annotation, *getattr(annotation, "__args__", ())):
            if hasattr(candidate, "model_fields"):
                names |= _all_field_names(candidate, seen)
    return names


def test_clinical_history_has_no_assessment_field() -> None:
    """The contract's *shape* forbids an assessment. Nothing to remember, nothing to forget."""
    offenders = _all_field_names(ClinicalHistory) & FORBIDDEN_CLINICAL_FIELDS
    assert not offenders, (
        f"ClinicalHistory grew assessment-shaped field(s): {sorted(offenders)}. MediKiosk "
        "produces a history, never an assessment."
    )


def test_no_api_route_is_named_for_diagnosis(project_root: Path) -> None:
    """No endpoint may exist whose path suggests it returns a candidate diagnosis."""
    offenders: list[str] = []
    for path in (project_root / "app" / "api").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    route = arg.value.casefold()
                    if any(f"/{bad}" in route for bad in ("diagnos", "differential", "triage-to")):
                        offenders.append(f"{path.name}:{node.lineno} {arg.value}")
    assert not offenders, f"Diagnosis-shaped route(s) found: {offenders}"


def test_outbound_payload_scan_rejects_an_assessment() -> None:
    payload = {
        "sessionId": "s1",
        "hpi": {"site": "chest"},
        "extras": [{"differential": ["angina", "reflux"]}],
    }
    with pytest.raises(DiagnosisAttempt, match="differential"):
        assert_no_assessment(payload)


def test_outbound_payload_scan_allows_reported_history() -> None:
    """A patient reporting what a doctor told them is history, and must pass."""
    payload = {
        "past_medical": {
            "conditions": {
                "value": ["Diabetes (sugar)"],
                "verbatim": "the doctor told me I have sugar",
                "tier": "confirmed",
            }
        }
    }
    assert_no_assessment(payload)

"""OperationOutcome construction. FHIR endpoints never return a bare string error."""
from __future__ import annotations

from typing import Any

from app.core.errors import MediKioskError
from app.fhir.r4 import OperationOutcome, OperationOutcomeIssue


def issue(
    code: str,
    diagnostics: str,
    *,
    severity: str = "error",
    expression: list[str] | None = None,
    details_text: str | None = None,
) -> OperationOutcomeIssue:
    payload: dict[str, Any] = {"severity": severity, "code": code, "diagnostics": diagnostics}
    if expression:
        payload["expression"] = expression
    if details_text:
        payload["details"] = {"text": details_text}
    return OperationOutcomeIssue(**payload)


def outcome(*issues: OperationOutcomeIssue) -> OperationOutcome:
    return OperationOutcome(issue=list(issues))


def outcome_from_error(
    exc: MediKioskError, *, expression: list[str] | None = None
) -> OperationOutcome:
    detail = exc.diagnostics
    if exc.details:
        rendered = ", ".join(f"{k}={v!r}" for k, v in exc.details.items())
        detail = f"{detail} [{rendered}]"
    return outcome(
        issue(exc.issue_code, detail, severity=exc.severity, expression=expression)
    )


def information(text: str) -> OperationOutcomeIssue:
    return issue("informational", text, severity="information")

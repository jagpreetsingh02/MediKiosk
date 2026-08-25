"""Domain errors. Every one of these maps to a FHIR OperationOutcome at the edge.

Ported from SIH 25026 `app/core/errors.py`, extended with the MediKiosk invariant errors.
"""

from __future__ import annotations


class MediKioskError(Exception):
    """Base class. `issue_code` is a FHIR IssueType code."""

    issue_code = "processing"
    severity = "error"
    http_status = 400

    def __init__(
        self,
        message: str,
        *,
        diagnostics: str | None = None,
        reason: str | None = None,
        **details: object,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or message
        #: A STABLE MACHINE CODE, carried separately from the human sentence.
        #:
        #: The UI has to tell "this photo is too small to read" apart from "this file type is
        #: not one we can open" in order to offer the right next step — Retake helps the
        #: first and is useless for the second. Matching on the message text to work that out
        #: would break the moment the wording is improved, which is exactly the sort of
        #: coupling that stops anyone improving it.
        #:
        #: It travels in the OperationOutcome's `details.text`, NOT in `diagnostics`, because
        #: diagnostics is what a patient reads and a code is not a sentence.
        self.reason = reason
        self.details = details


# ---------------------------------------------------------------- invariant violations


class InvariantViolation(MediKioskError):
    """An architectural invariant was breached. Never caught-and-continued anywhere."""

    issue_code = "business-rule"
    http_status = 422


class ProvenanceError(InvariantViolation):
    """Invariant 2 — a fact reached `record_fact()` without a usable source span."""


class DiagnosisAttempt(InvariantViolation):
    """Invariant 1 — something tried to emit an assessment. The physician diagnoses."""

    http_status = 403


class TraceabilityError(InvariantViolation):
    """Invariant 4 / Module C — a summary line does not resolve to a recorded fact."""


class DeEscalationAttempt(InvariantViolation):
    """Invariant 3 — something tried to lower a triage priority. Red flags are additive."""


class ConsentRequired(MediKioskError):
    """Invariant 6 — capture attempted before granular consent was granted."""

    issue_code = "forbidden"
    http_status = 403


class SessionExpired(MediKioskError):
    issue_code = "expired"
    http_status = 410


# ---------------------------------------------------------------- terminology (ported)


class UnknownCodeError(MediKioskError):
    """The guard refused: this code is not in a loaded CodeSystem at the pinned version."""

    issue_code = "code-invalid"


class NotSelectableError(UnknownCodeError):
    issue_code = "business-rule"


class UnknownSystemError(MediKioskError):
    issue_code = "not-supported"


class VersionMismatchError(UnknownCodeError):
    issue_code = "conflict"
    http_status = 409


# ---------------------------------------------------------------- access & transport


class PolicyDenied(MediKioskError):
    issue_code = "forbidden"
    http_status = 403


class AuthError(MediKioskError):
    issue_code = "security"
    http_status = 401


class ValidationError(MediKioskError):
    issue_code = "invalid"
    http_status = 400


class LLMContractError(MediKioskError):
    """LLM output failed Pydantic validation. A hard failure, never a free-text fallback."""

    issue_code = "processing"
    http_status = 502


class UpstreamUnavailable(MediKioskError):
    issue_code = "transient"
    http_status = 503

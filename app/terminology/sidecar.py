"""The coding sidecar. Invariant 5: codes are retrieved, never generated.

"Sidecar" is literal — coding runs *beside* the history and never inside it. A problem entry
is complete and physician-ready with ``coding = None``; the code is decoration on top of a
patient-reported term, not a precondition for recording it. That ordering is what makes
``unmapped`` a first-class 200 rather than a failure: nothing downstream is waiting on a code.

Every Coding this module returns came out of ``emit_coding()``, which reads it from a loaded
CodeSystem at a pinned version. There is no path from a string to a code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DASHAVIDHA_SYSTEM, ICD_MMS_SYSTEM, settings
from app.core.errors import UnknownCodeError, UnknownSystemError
from app.terminology.guard import emit_coding
from app.terminology.store import lookup


@dataclass(frozen=True, slots=True)
class CodingResult:
    """`coding is None` and `unmapped is True` is a valid, complete, successful result."""

    unmapped: bool
    coding: dict[str, Any] | None
    system_searched: str
    candidates_considered: int
    #: Why nothing was returned, in words a reviewer can read. Never a nearest-match code.
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unmapped": self.unmapped,
            "coding": self.coding,
            "systemSearched": self.system_searched,
            "candidatesConsidered": self.candidates_considered,
            "note": self.note,
        }


UNMAPPED_NOTE = (
    "No concept in the pinned CodeSystem matched this term. Recorded as an unmapped "
    "patient-reported term. MediKiosk does not return a nearest match."
)


async def code_reported_term(
    session: AsyncSession, term: str, *, system: str = ICD_MMS_SYSTEM
) -> CodingResult:
    """Attempt to code a patient-reported problem term. Returns unmapped rather than guessing."""
    try:
        candidates = await lookup(session, system, term, limit=5)
    except Exception:  # a missing CodeSystem is unmapped, not a 500
        return CodingResult(True, None, system, 0, "CodeSystem not loaded.")

    if not candidates:
        return CodingResult(True, None, system, 0, UNMAPPED_NOTE)

    # Only an exact normalised match is auto-applied. Anything looser is a candidate for a
    # human, and MediKiosk has no review queue — so it stays unmapped.
    from app.terminology.store import normalize

    key = normalize(term)
    exact = next((c for c in candidates if c.display_normalized == key), None)
    if exact is None:
        return CodingResult(
            True,
            None,
            system,
            len(candidates),
            f"{len(candidates)} near match(es) found but none exact; left unmapped rather "
            "than guessing between them.",
        )
    try:
        coding = await emit_coding(session, system, exact.code)
    except (UnknownCodeError, UnknownSystemError) as exc:
        return CodingResult(True, None, system, len(candidates), str(exc))
    return CodingResult(False, coding.model_dump(exclude_none=True), system, len(candidates))


async def code_dashavidha(session: AsyncSession, code: str) -> CodingResult:
    """Code a Dashavidha parameter value. The code comes from the ontology, never from an LLM."""
    try:
        coding = await emit_coding(session, DASHAVIDHA_SYSTEM, code, settings.dashavidha_version)
    except (UnknownCodeError, UnknownSystemError) as exc:
        return CodingResult(True, None, DASHAVIDHA_SYSTEM, 0, str(exc))
    return CodingResult(False, coding.model_dump(exclude_none=True), DASHAVIDHA_SYSTEM, 1)

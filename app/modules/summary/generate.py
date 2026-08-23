"""The Module C entry point: history → draft summary, with the gate enforced.

`generate()` is the only sanctioned way to produce a summary. It runs assembly, optional
smoothing, and then `enforce()`. If traceability fails, it raises and **no summary is
returned** — a partially-verified summary is worse than none, because the physician cannot
tell which half was checked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.contracts.history import ClinicalHistory
from app.contracts.no_diagnosis import assert_no_assessment
from app.contracts.record import FactLedger
from app.core.logging import get_logger
from app.modules.summary.assemble import Summary, build
from app.modules.summary.prose import SmoothingOutcome, smooth
from app.modules.summary.traceability import TraceabilityReport, enforce, with_sources
from app.redflags.engine import Escalation

log = get_logger(__name__)


@dataclass(slots=True)
class GeneratedSummary:
    summary: Summary
    traceability: TraceabilityReport
    sourced_lines: list[dict[str, Any]]
    smoothing: list[SmoothingOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            **self.summary.to_dict(),
            "traceability": self.traceability.to_dict(),
            "lines": self.sourced_lines,
            "smoothing": [s.to_dict() for s in self.smoothing],
        }
        # Belt and braces: Invariant 1 checked on the way out, every time.
        assert_no_assessment(payload, where="summary")
        return payload


def _retrieved_coding_displays(history: ClinicalHistory) -> set[str]:
    """Display names that came out of the closed-vocabulary guard, and only those."""
    displays: set[str] = set()
    for group in (history.problems, history.medications, history.investigations):
        for entry in group:
            coding = getattr(entry, "coding", None)
            if coding and coding.get("display"):
                displays.add(str(coding["display"]))
                displays.add(str(coding.get("code", "")))
    return displays


def generate(
    history: ClinicalHistory,
    ledger: FactLedger,
    *,
    escalation: Escalation | None = None,
    use_prose: bool = False,
) -> GeneratedSummary:
    """Produce the physician draft, or fail. Never produces a half-verified one."""
    summary = build(history, escalation=escalation)

    smoothing: list[SmoothingOutcome] = []
    if use_prose:
        summary, smoothing = smooth(summary, ledger)

    report = enforce(
        summary, ledger, retrieved_codings=_retrieved_coding_displays(history)
    )  # raises TraceabilityError on any untraceable claim

    log.info(
        "summary.generated",
        session=history.session_id,
        sections=len(summary.sections),
        fact_lines=report.fact_lines,
        completeness=history.overall_completeness,
        smoothed=sum(1 for s in smoothing if s.applied),
    )
    return GeneratedSummary(
        summary=summary,
        traceability=report,
        sourced_lines=with_sources(summary, ledger),
        smoothing=smoothing,
    )

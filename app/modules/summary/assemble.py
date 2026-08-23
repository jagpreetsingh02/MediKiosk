"""Module C — deterministic summary assembly.

The summary is built by **template**, from the projected history, in standard clinical order.
The LLM does not write it. Each line is emitted with the fact ids that justify it, which is
what makes click-to-source work and what the traceability check verifies afterwards.

Why a template and not a model: the summary is the artefact a physician will act on in a
two-minute consultation. A template produces the same structure every time, so a physician
learns where to look; a model produces prose that reads well and moves things around. Reading
speed under time pressure comes from predictable structure, not from good sentences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.contracts.history import ClinicalHistory, Slot, SlotStatus

#: The order a physician reads in. Not configurable: a summary whose sections move around
#: between patients is slower to read, whatever order you prefer.
SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("chief_complaint", "Presenting complaint"),
    ("hpi", "History of presenting illness"),
    ("red_flags", "Escalation"),
    ("past_medical", "Past medical history"),
    ("past_surgical", "Past surgical history"),
    ("drug_allergy", "Medicines and allergies"),
    ("documents", "Prior records"),
    ("family_history", "Family history"),
    ("personal_history", "Personal history"),
    ("review_of_systems", "Review of systems"),
    ("ayush", "Ayurvedic assessment (patient-reported)"),
    ("gaps", "Not covered"),
)


@dataclass(slots=True)
class SummaryLine:
    """One rendered line. `fact_ids` is what click-to-source resolves."""

    text: str
    fact_ids: list[str] = field(default_factory=list)
    #: "fact" lines make a clinical claim and MUST trace. "structural" lines are headings,
    #: counts and explicit statements of absence, which have nothing to trace to.
    kind: str = "fact"
    tier: str | None = None
    confidence: float | None = None
    emphasis: str | None = None  # "immediate" | "urgent" | "unverified" | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "factIds": self.fact_ids,
            "kind": self.kind,
            "tier": self.tier,
            "confidence": self.confidence,
            "emphasis": self.emphasis,
        }


@dataclass(slots=True)
class SummarySection:
    section_id: str
    title: str
    lines: list[SummaryLine] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionId": self.section_id,
            "title": self.title,
            "lines": [line.to_dict() for line in self.lines],
        }


@dataclass(slots=True)
class Summary:
    session_id: str
    generated_at: datetime
    sections: list[SummarySection] = field(default_factory=list)
    #: A draft until a physician commits it (Invariant 4). Never anything else.
    status: str = "draft"
    completeness: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "generatedAt": self.generated_at.isoformat(),
            "status": self.status,
            "completeness": self.completeness,
            "sections": [s.to_dict() for s in self.sections],
            "warnings": self.warnings,
            "notice": (
                "DRAFT — a structured history, not an assessment. No diagnosis, differential "
                "or treatment is offered or implied. Review, edit and confirm before this "
                "reaches the record."
            ),
        }

    def fact_lines(self) -> list[SummaryLine]:
        return [line for s in self.sections for line in s.lines if line.kind == "fact"]


def _render(slot: Slot) -> str:
    value = slot.value
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _line_from_slot(label: str, slot: Slot) -> SummaryLine:
    return SummaryLine(
        text=f"{label}: {_render(slot)}",
        fact_ids=list(slot.fact_ids),
        tier=slot.tier.value if slot.tier else None,
        confidence=slot.confidence,
    )


def _section_lines(
    history: ClinicalHistory, section_id: str, labels: dict[str, str]
) -> list[SummaryLine]:
    section = next((s for s in history.sections() if s.section_id == section_id), None)
    if section is None:
        return []
    lines: list[SummaryLine] = []
    for slot in section.slots.values():
        if not slot.recorded:
            continue
        # The ontology holds TWO registers per question: `prompt` for the patient and
        # `label` for the physician. A kiosk asks "What is troubling you today?"; a summary
        # read in ninety seconds says "Complaint:".
        lines.append(_line_from_slot(labels.get(slot.path, slot.path), slot))
    return lines


def build(
    history: ClinicalHistory, *, escalation: Any = None, ayush: bool | None = None
) -> Summary:
    """Assemble the physician-ready draft. Pure: history in, summary out."""
    from app.modules.dialogue.ontology import load_ontology

    ontology = load_ontology(ayush=history.ayush is not None if ayush is None else ayush)
    labels = {q.path: q.physician_label() for q in ontology.by_id.values()}

    summary = Summary(
        session_id=history.session_id,
        generated_at=datetime.now(UTC),
        completeness=history.overall_completeness,
    )

    demo = history.demographics
    header_bits = [
        b
        for b in (
            f"{demo.age_years} years" if demo.age_years else None,
            demo.gender,
        )
        if b
    ]
    if header_bits:
        summary.sections.append(
            SummarySection(
                "patient",
                "Patient",
                [SummaryLine(", ".join(header_bits), kind="structural")],
            )
        )

    for section_id, title in SECTION_ORDER:
        if section_id == "red_flags":
            lines = _red_flag_lines(history, escalation)
        elif section_id == "documents":
            lines = _document_lines(history)
        elif section_id == "gaps":
            lines = _gap_lines(history)
        else:
            lines = _section_lines(history, section_id, labels)
            if section_id == "drug_allergy":
                lines += _medication_lines(history)
            if section_id == "past_medical":
                lines += _problem_lines(history)
        if lines:
            summary.sections.append(SummarySection(section_id, title, lines))

    if history.overall_completeness < 0.6:
        summary.warnings.append(
            f"Only {history.overall_completeness:.0%} of the applicable history was captured. "
            "Treat the gaps as unknown, not as negative findings."
        )
    return summary


def _red_flag_lines(history: ClinicalHistory, escalation: Any) -> list[SummaryLine]:
    flags = history.red_flags or (list(escalation.flags) if escalation else [])
    if not flags:
        # Explicitly stated, because a blank section reads like "nothing found" and this
        # system does not make that claim (Invariant 3).
        return [
            SummaryLine(
                "No emergency rule fired on the history captured. This is not a statement "
                "that the patient is low-priority.",
                kind="structural",
            )
        ]
    lines: list[SummaryLine] = []
    for flag in sorted(flags, key=lambda f: 0 if f.level == "immediate" else 1):
        lines.append(
            SummaryLine(
                text=f"[{flag.level.upper()}] {flag.label} — {flag.rationale}",
                fact_ids=list(flag.triggering_fact_ids),
                emphasis=flag.level,
            )
        )
    return lines


def _medication_lines(history: ClinicalHistory) -> list[SummaryLine]:
    lines: list[SummaryLine] = []
    for med in history.medications:
        if not med.name.recorded:
            continue
        parts = [str(med.name.value)]
        for slot in (med.dose, med.frequency, med.route):
            if slot.recorded:
                parts.append(str(slot.value))
        coding = med.coding
        suffix = ""
        if coding:
            suffix = f" [{coding.get('code')} {coding.get('display')}]"
        lines.append(
            SummaryLine(
                text=f"Medication: {' '.join(parts)}{suffix}",
                fact_ids=list(med.name.fact_ids)
                + list(med.dose.fact_ids)
                + list(med.frequency.fact_ids),
                tier=med.name.tier.value if med.name.tier else None,
                confidence=med.name.confidence,
            )
        )
    return lines


def _problem_lines(history: ClinicalHistory) -> list[SummaryLine]:
    lines: list[SummaryLine] = []
    for problem in history.problems:
        if not problem.reported_term.recorded:
            continue
        coding = problem.coding
        # `unmapped` is printed, not hidden. A physician seeing "unmapped" knows the term was
        # not codeable; a physician seeing nothing assumes it was never tried.
        suffix = f" [{coding.get('code')} {coding.get('display')}]" if coding else " [unmapped]"
        year = f" ({problem.reported_year.value})" if problem.reported_year.recorded else ""
        lines.append(
            SummaryLine(
                text=f"Reported: {problem.reported_term.value}{year}{suffix}",
                fact_ids=list(problem.reported_term.fact_ids),
                tier=problem.reported_term.tier.value if problem.reported_term.tier else None,
            )
        )
    return lines


def _document_lines(history: ClinicalHistory) -> list[SummaryLine]:
    lines: list[SummaryLine] = []
    for doc in history.documents:
        note = (
            f" — {len(doc.low_confidence_pages)} page(s) need verification"
            if doc.low_confidence_pages
            else ""
        )
        lines.append(
            SummaryLine(
                text=(
                    f"{doc.filename}: {doc.pages} page(s), read by {doc.ocr_backend} at "
                    f"{doc.mean_confidence:.0%} mean confidence{note}"
                ),
                kind="structural",
                emphasis="unverified" if doc.low_confidence_pages else None,
            )
        )
    for event in history.timeline[:12]:
        lines.append(
            SummaryLine(
                text=(
                    f"{event.occurred_on.isoformat() if event.occurred_on else 'undated'} — "
                    f"{event.label}"
                ),
                fact_ids=list(event.fact_ids),
                emphasis="unverified" if event.low_confidence else None,
                kind="fact" if event.fact_ids else "structural",
            )
        )
    return lines


def _gap_lines(history: ClinicalHistory) -> list[SummaryLine]:
    """Absences are printed. A physician must be able to tell a gap from a negative finding."""
    lines: list[SummaryLine] = []
    if history.declined:
        lines.append(
            SummaryLine(
                f"Patient declined to answer: {', '.join(history.declined)}",
                kind="structural",
                emphasis="unverified",
            )
        )
    unasked = [
        path for path, slot in history.all_slots().items() if slot.status is SlotStatus.NOT_ASKED
    ]
    if unasked:
        lines.append(
            SummaryLine(
                f"Not asked ({len(unasked)}): {', '.join(sorted(unasked)[:10])}"
                + ("…" if len(unasked) > 10 else ""),
                kind="structural",
            )
        )
    return lines

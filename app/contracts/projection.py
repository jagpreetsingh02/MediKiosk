"""Building a :class:`ClinicalHistory` from a fact ledger.

The projection is a pure function of (ledger, ontology, demographics). It never invents a
slot, never fills one in, and never carries a value that no fact backs. Run it twice on the
same ledger and you get the same history; run it on an empty ledger and you get a history in
which every slot is honestly `not_asked`.

Contradictions are preserved rather than resolved. If the patient said "three days" and later
"about a week", the slot shows the latest value and lists the earlier one under `superseded`.
Deciding which is true is the physician's job, and they cannot do it if we have thrown one away.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.contracts.history import (
    Allergy,
    ClinicalHistory,
    Demographics,
    InvestigationResult,
    Medication,
    ProblemEntry,
    Section,
    Slot,
    SlotStatus,
    absence_status,
)
from app.contracts.provenance import Fact
from app.contracts.record import FactLedger
from app.modules.dialogue.ontology import Ontology, Question, load_ontology

#: Section id -> ClinicalHistory attribute. Kept explicit so a new ontology section cannot
#: silently vanish from the physician's screen: the assertion below fails the build instead.
SECTION_FIELDS: dict[str, str] = {
    "chief_complaint": "chief_complaint",
    "hpi": "hpi",
    "past_medical": "past_medical",
    "past_surgical": "past_surgical",
    "drug_allergy": "drug_allergy",
    "family_history": "family_history",
    "personal_history": "personal_history",
    "review_of_systems": "review_of_systems",
    "ayush": "ayush",
}


def _display_value(question: Question, value: Any, language: str) -> Any:
    """Turn option keys into the labels a physician reads. The key stays in the fact."""
    if question.kind in ("single_choice", "duration"):
        option = question.option(str(value))
        return option.label_en if option else value
    if question.kind == "multi_choice" and isinstance(value, list):
        return [
            (question.option(str(v)).label_en if question.option(str(v)) else v) for v in value
        ]
    return value


def _slot_from_facts(question: Question, facts: list[Fact], language: str) -> Slot:
    """Latest active fact wins; earlier ones are kept visible as contradictions."""
    active = [f for f in facts if f.active]
    superseded = [f for f in facts if not f.active]

    if not active:
        return Slot(path=question.path, label=question.prompt["en"], status=SlotStatus.NOT_ASKED)

    latest = max(active, key=lambda f: f.recorded_at)
    return Slot(
        path=question.path,
        label=question.prompt["en"],
        value=_display_value(question, latest.value, language),
        status=SlotStatus.RECORDED,
        tier=latest.tier,
        confidence=latest.confidence,
        fact_ids=[f.fact_id for f in active],
        verbatim=latest.source.verbatim,
        superseded=[
            {
                "value": _display_value(question, f.value, language),
                "verbatim": f.source.verbatim,
                "recordedAt": f.recorded_at.isoformat(),
                "factId": f.fact_id,
            }
            for f in sorted(superseded, key=lambda f: f.recorded_at)
        ],
    )


def _indexed_groups(ledger: FactLedger) -> dict[str, dict[int, dict[str, list[Fact]]]]:
    """Collect `group[i].field` facts into {group: {index: {field: [facts]}}}."""
    groups: dict[str, dict[int, dict[str, list[Fact]]]] = {}
    for fact in ledger.facts:
        if "[" not in fact.path or "]." not in fact.path:
            continue
        group, rest = fact.path.split("[", 1)
        index_text, field_name = rest.split("].", 1)
        try:
            index = int(index_text)
        except ValueError:
            continue
        groups.setdefault(group, {}).setdefault(index, {}).setdefault(field_name, []).append(fact)
    return groups


def _group_slot(path: str, facts: list[Fact], label: str = "") -> Slot:
    active = [f for f in facts if f.active]
    if not active:
        return Slot(path=path, label=label, status=SlotStatus.NOT_ASKED)
    latest = max(active, key=lambda f: f.recorded_at)
    return Slot(
        path=path, label=label, value=latest.value, status=SlotStatus.RECORDED,
        tier=latest.tier, confidence=latest.confidence,
        fact_ids=[f.fact_id for f in active], verbatim=latest.source.verbatim,
    )


def _blank(path: str) -> Slot:
    return Slot(path=path, status=SlotStatus.NOT_ASKED)


def _project_repeating(
    ledger: FactLedger,
) -> tuple[list[Medication], list[Allergy], list[ProblemEntry], list[InvestigationResult]]:
    """Build the repeating clinical groups. Every slot in them is fact-backed or empty."""
    groups = _indexed_groups(ledger)
    medications: list[Medication] = []
    allergies: list[Allergy] = []
    problems: list[ProblemEntry] = []
    investigations: list[InvestigationResult] = []

    def slot(group: str, index: int, field_name: str) -> Slot:
        path = f"{group}[{index}].{field_name}"
        return _group_slot(path, groups.get(group, {}).get(index, {}).get(field_name, []))

    for index in sorted(groups.get("medications", {})):
        medications.append(
            Medication(
                entry_id=f"med_{index}",
                name=slot("medications", index, "name"),
                dose=slot("medications", index, "dose"),
                frequency=slot("medications", index, "frequency"),
                route=slot("medications", index, "route"),
                started=slot("medications", index, "started"),
                ongoing=slot("medications", index, "ongoing"),
            )
        )
    for index in sorted(groups.get("allergies", {})):
        allergies.append(
            Allergy(
                entry_id=f"alg_{index}",
                substance=slot("allergies", index, "substance"),
                reaction=slot("allergies", index, "reaction"),
                severity=slot("allergies", index, "severity"),
            )
        )
    for index in sorted(groups.get("problems", {})):
        problems.append(
            ProblemEntry(
                entry_id=f"prob_{index}",
                reported_term=slot("problems", index, "reported_term"),
                reported_year=slot("problems", index, "reported_year"),
            )
        )
    for index in sorted(groups.get("investigations", {})):
        investigations.append(
            InvestigationResult(
                entry_id=f"inv_{index}",
                analyte=slot("investigations", index, "analyte"),
                value=slot("investigations", index, "value"),
            )
        )
    return medications, allergies, problems, investigations


def _problems_from_choices(
    ledger: FactLedger, ontology: Ontology, start_index: int
) -> list[ProblemEntry]:
    """A tapped 'Diabetes (sugar)' in past medical history is a reported problem too.

    The ontology option carries a `term:` — the phrase to look up. It never carries a code:
    the sidecar retrieves that, and often returns unmapped, which is fine (Invariant 5).
    """
    out: list[ProblemEntry] = []
    for fact in ledger.active_facts():
        question = ontology.by_path.get(fact.path)
        if question is None or question.path != "past_medical.conditions":
            continue
        values = fact.value if isinstance(fact.value, list) else [fact.value]
        for value in values:
            option = question.option(str(value))
            if option is None or not option.term:
                continue
            index = start_index + len(out)
            out.append(
                ProblemEntry(
                    entry_id=f"prob_{index}",
                    reported_term=Slot(
                        path=f"problems[{index}].reported_term",
                        label="Reported condition",
                        value=option.term,
                        status=SlotStatus.RECORDED,
                        tier=fact.tier,
                        confidence=fact.confidence,
                        fact_ids=[fact.fact_id],
                        verbatim=fact.source.verbatim,
                    ),
                    reported_year=_blank(f"problems[{index}].reported_year"),
                )
            )
    return out


def project(
    ledger: FactLedger,
    *,
    demographics: Demographics | None = None,
    ayush: bool = False,
    language: str = "en",
    ontology: Ontology | None = None,
) -> ClinicalHistory:
    """Build the physician-facing history. Pure; no I/O, no model, no network."""
    ontology = ontology or load_ontology(ayush=ayush)
    demographics = demographics or Demographics(language=language)

    facts_by_path: dict[str, list[Fact]] = {}
    for fact in ledger.facts:
        facts_by_path.setdefault(fact.path, []).append(fact)

    absence_by_path = {a.path: a for a in ledger.absences}

    sections: dict[str, Section] = {}
    declined: list[str] = []
    not_asked: list[str] = []

    for onto_section in ontology.sections:
        slots: dict[str, Slot] = {}
        for question in onto_section.questions:
            facts = facts_by_path.get(question.path, [])
            slot = _slot_from_facts(question, facts, language)
            if slot.status is SlotStatus.NOT_ASKED and question.path in absence_by_path:
                slot.status = absence_status(absence_by_path[question.path].reason)
            if slot.status is SlotStatus.DECLINED:
                declined.append(question.path)
            elif slot.status is SlotStatus.NOT_ASKED:
                not_asked.append(question.path)
            slots[question.path] = slot

        recorded = sum(1 for s in slots.values() if s.recorded)
        # Denominator excludes slots the branch legitimately closed: a section is not
        # "incomplete" because the patient has no allergies to describe.
        askable = sum(1 for s in slots.values() if s.status is not SlotStatus.NOT_ASKED) or len(slots)
        sections[onto_section.id] = Section(
            section_id=onto_section.id,
            title=onto_section.title,
            slots=slots,
            completeness=round(recorded / askable, 4) if askable else 0.0,
        )

    missing = set(sections) - set(SECTION_FIELDS)
    if missing:
        raise AssertionError(
            f"Ontology sections {sorted(missing)} have no home on ClinicalHistory. Add them to "
            "SECTION_FIELDS and to the contract, or the physician will never see them."
        )

    def _section(section_id: str) -> Section:
        return sections.get(section_id) or Section(section_id=section_id, title=section_id)

    total_recorded = sum(
        1 for s in sections.values() for slot in s.slots.values() if slot.recorded
    )
    total_askable = sum(
        1 for s in sections.values() for slot in s.slots.values()
        if slot.status is not SlotStatus.NOT_ASKED
    )

    medications, allergies, problems, investigations = _project_repeating(ledger)
    problems += _problems_from_choices(ledger, ontology, start_index=len(problems))

    return ClinicalHistory(
        session_id=ledger.session_id,
        generated_at=datetime.now(UTC),
        demographics=demographics,
        chief_complaint=_section("chief_complaint"),
        hpi=_section("hpi"),
        past_medical=_section("past_medical"),
        past_surgical=_section("past_surgical"),
        drug_allergy=_section("drug_allergy"),
        family_history=_section("family_history"),
        personal_history=_section("personal_history"),
        review_of_systems=_section("review_of_systems"),
        ayush=sections.get("ayush"),
        medications=medications,
        allergies=allergies,
        problems=problems,
        investigations=investigations,
        declined=sorted(set(declined)),
        not_asked=sorted(set(not_asked)),
        overall_completeness=(
            round(total_recorded / total_askable, 4) if total_askable else 0.0
        ),
    )

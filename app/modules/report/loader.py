"""Every row the brief needs, fetched once, then handed to a pure function.

WHY THE SPLIT IS THE WHOLE DESIGN. The brief must be byte-identical across two runs on the
same data, or click-to-source is a lie: a physician clicks a line, and the evidence that opens
has to be the evidence that produced *that* line. If assembly could reach back into the
database mid-render, two runs could interleave with a concurrent write and disagree, and
nothing on screen would show that they had.

So there are exactly two phases, and the type system enforces the boundary:

    load(db, patient) -> Rows        async, touches the database, does no reasoning
    assemble(rows)    -> dict        sync, pure, cannot reach a database even by mistake

`assemble` takes a frozen dataclass of plain rows. It has no session, no clock and no
randomness available to it, so determinism is not a discipline anyone has to remember — it is
the only thing the function is able to do. `tests/test_report_determinism.py` asserts it.

`generated_at` is deliberately NOT part of the assembled payload. It is metadata about the
render, not content, and stamping a clock inside the payload would make byte-equality
impossible to assert while proving nothing about the data. It is added by the snapshot writer,
where it belongs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.durable import (
    ClinicalFactRecord,
    ContradictionRecord,
    DocumentRecord,
    Encounter,
    MedicationEvent,
    ObservationEvent,
    Patient,
    PhysicianDecision,
    RedFlagEventRecord,
    SourceEvidence,
)


@dataclass(frozen=True)
class Rows:
    """A frozen read of everything the brief draws on. No session, on purpose."""

    patient: Patient
    #: Intake encounters, oldest first. The current one is the last.
    encounters: list[Encounter]
    current: Encounter | None
    #: The most recent PRIOR intake, which "What Changed?" compares against.
    previous: Encounter | None

    #: Facts for the current encounter — ALL of them, superseded and invalidated included.
    #: The assembler needs the dead ones to report supersession honestly; it filters, rather
    #: than being handed a pre-filtered set that hides what was changed.
    facts: list[ClinicalFactRecord] = field(default_factory=list)
    #: Facts for the previous encounter, for the diff.
    prior_facts: list[ClinicalFactRecord] = field(default_factory=list)
    #: fact.id -> its evidence rows.
    evidence: dict[int, list[SourceEvidence]] = field(default_factory=dict)

    medications: list[MedicationEvent] = field(default_factory=list)
    observations: list[ObservationEvent] = field(default_factory=list)
    red_flags: list[RedFlagEventRecord] = field(default_factory=list)
    contradictions: list[ContradictionRecord] = field(default_factory=list)
    documents: list[DocumentRecord] = field(default_factory=list)
    decisions: list[PhysicianDecision] = field(default_factory=list)


async def _facts_for(db: AsyncSession, encounter_id: int) -> list[ClinicalFactRecord]:
    return list(
        (
            await db.execute(
                select(ClinicalFactRecord)
                .where(ClinicalFactRecord.encounter_id == encounter_id)
                # Ordered by primary key so two loads return the same sequence. Without an
                # explicit ORDER BY, Postgres may return rows in any order it likes, and the
                # payload would differ between runs for reasons that have nothing to do with
                # the data.
                .order_by(ClinicalFactRecord.id)
            )
        )
        .scalars()
        .all()
    )


async def load(
    db: AsyncSession, patient: Patient, *, encounter_ref: str | None = None
) -> Rows:
    """One read of everything. Ordered explicitly everywhere, for the reason above.

    `encounter_ref` picks WHICH visit the brief is about. Without it the most recent one is
    "current", which is what a clinician opening a live queue wants. With it, a patient can
    open the report for a specific past visit — and "What changed?" then correctly compares
    against the visit before THAT one, not against today.

    CONFIRMED ENCOUNTERS ONLY, and the filter is belt-and-braces rather than necessary: an
    `Encounter` row can only be created by `promote()`, which is reachable only from the
    physician commit route behind `summary.commit` and an explicit `confirmed: true`. So an
    unconfirmed encounter cannot exist. `tests/test_patient_self_service.py` asserts that
    structurally; this filter means a future code path that broke the rule still could not
    show a patient an unconfirmed visit.
    """
    encounters = list(
        (
            await db.execute(
                select(Encounter)
                .where(
                    Encounter.patient_id == patient.id,
                    Encounter.kind == "intake",
                    Encounter.confirmed_by.is_not(None),
                    Encounter.confirmed_by != "",
                )
                .order_by(Encounter.occurred_at, Encounter.id)
            )
        )
        .scalars()
        .all()
    )

    if encounter_ref:
        index = next(
            (i for i, e in enumerate(encounters) if e.encounter_ref == encounter_ref), None
        )
        if index is None:
            # Not this patient's encounter. Returning an empty read rather than another
            # patient's data is the only safe answer; the route turns it into a 404.
            current, previous, encounters = None, None, []
        else:
            current = encounters[index]
            previous = encounters[index - 1] if index >= 1 else None
    else:
        current = encounters[-1] if encounters else None
        previous = encounters[-2] if len(encounters) >= 2 else None

    facts = await _facts_for(db, current.id) if current else []
    prior_facts = await _facts_for(db, previous.id) if previous else []

    evidence: dict[int, list[SourceEvidence]] = {}
    fact_ids = [f.id for f in facts]
    if fact_ids:
        rows = list(
            (
                await db.execute(
                    select(SourceEvidence)
                    .where(SourceEvidence.fact_id.in_(fact_ids))
                    .order_by(SourceEvidence.id)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            evidence.setdefault(row.fact_id, []).append(row)

    medications = list(
        (
            await db.execute(
                select(MedicationEvent)
                .where(MedicationEvent.patient_id == patient.id)
                .order_by(MedicationEvent.observed_on, MedicationEvent.id)
            )
        )
        .scalars()
        .all()
    )
    observations = list(
        (
            await db.execute(
                select(ObservationEvent)
                .where(ObservationEvent.patient_id == patient.id)
                .order_by(ObservationEvent.observed_on, ObservationEvent.id)
            )
        )
        .scalars()
        .all()
    )
    red_flags = (
        list(
            (
                await db.execute(
                    select(RedFlagEventRecord)
                    .where(RedFlagEventRecord.encounter_id == current.id)
                    .order_by(RedFlagEventRecord.id)
                )
            )
            .scalars()
            .all()
        )
        if current
        else []
    )
    contradictions = list(
        (
            await db.execute(
                select(ContradictionRecord)
                .where(ContradictionRecord.patient_id == patient.id)
                .order_by(ContradictionRecord.id)
            )
        )
        .scalars()
        .all()
    )
    documents = (
        list(
            (
                await db.execute(
                    select(DocumentRecord)
                    .where(DocumentRecord.encounter_id == current.id)
                    .order_by(DocumentRecord.id)
                )
            )
            .scalars()
            .all()
        )
        if current
        else []
    )
    decisions = (
        list(
            (
                await db.execute(
                    select(PhysicianDecision)
                    .where(PhysicianDecision.encounter_id == current.id)
                    .order_by(PhysicianDecision.id)
                )
            )
            .scalars()
            .all()
        )
        if current
        else []
    )

    return Rows(
        patient=patient,
        encounters=encounters,
        current=current,
        previous=previous,
        facts=facts,
        prior_facts=prior_facts,
        evidence=evidence,
        medications=medications,
        observations=observations,
        red_flags=red_flags,
        contradictions=contradictions,
        documents=documents,
        decisions=decisions,
    )

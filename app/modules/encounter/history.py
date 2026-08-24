"""Reading a patient's longitudinal record: timeline, medication history, similar encounters.

Everything here is a read over the durable tables. Three design decisions worth stating:

**Medication history reports provenance, not state.** `reconcile()` groups every mention of a
drug across every visit and says how each one is known — `documented`, `patient-reported-current`,
`historical`. It flags a drug as needing reconciliation when the sources disagree. It never
concludes that a medicine is currently being taken because it was once prescribed.

**Similar-encounter retrieval is deterministic and explainable.** Shared features are
computed by set intersection over recorded values, and the result *lists the features* rather
than reporting a percentage. There are no embeddings: they would be less explainable and, on
one patient's handful of encounters, no better.

**It never leaves the patient.** `similar_encounters()` filters on `patient_id` before it
compares anything. A retrieval that could surface another person's visit would be a
confidentiality breach dressed as a feature.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

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
    SourceEvidence,
    TimelineEventRecord,
)

#: Paths compared when looking for a similar past visit. Deliberately short: the presenting
#: complaint and the features a clinician would actually recognise a recurrence by.
SIMILARITY_PATHS: tuple[str, ...] = (
    "chief_complaint.text",
    "hpi.site",
    "hpi.character",
    "hpi.radiation",
    "hpi.timing",
    "hpi.associated",
    "hpi.exacerbating",
    "past_medical.conditions",
)

#: Human labels for the shared-feature list, so the physician reads words not paths.
FEATURE_LABELS: dict[str, str] = {
    "chief_complaint.text": "presenting complaint",
    "hpi.site": "site",
    "hpi.character": "character",
    "hpi.radiation": "radiation",
    "hpi.timing": "timing",
    "hpi.associated": "associated symptom",
    "hpi.exacerbating": "aggravating factor",
    "past_medical.conditions": "known condition",
}


async def get_patient(db: AsyncSession, *, patient_ref: str) -> Patient | None:
    return (
        await db.execute(select(Patient).where(Patient.patient_ref == patient_ref))
    ).scalars().first()


async def get_patient_by_abha(db: AsyncSession, *, abha_ref: str) -> Patient | None:
    return (
        await db.execute(select(Patient).where(Patient.abha_ref == abha_ref))
    ).scalars().first()


async def encounters_for(db: AsyncSession, patient_id: int) -> list[Encounter]:
    return list(
        (
            await db.execute(
                select(Encounter)
                .where(Encounter.patient_id == patient_id)
                .order_by(Encounter.occurred_at.desc())
            )
        ).scalars().all()
    )


async def overview(db: AsyncSession, patient: Patient) -> dict[str, Any]:
    """The patient home screen: what this person already has on file."""
    encounters = await encounters_for(db, patient.id)
    documents = list(
        (
            await db.execute(
                select(DocumentRecord)
                .join(Encounter, DocumentRecord.encounter_id == Encounter.id)
                .where(Encounter.patient_id == patient.id)
            )
        ).scalars().all()
    )
    medications = list(
        (
            await db.execute(
                select(MedicationEvent).where(MedicationEvent.patient_id == patient.id)
            )
        ).scalars().all()
    )
    observations = list(
        (
            await db.execute(
                select(ObservationEvent).where(ObservationEvent.patient_id == patient.id)
            )
        ).scalars().all()
    )

    return {
        "patientRef": patient.patient_ref,
        "displayName": patient.display_name,
        "abhaMasked": _mask(patient.abha_ref),
        "ageYears": patient.age_years,
        "gender": patient.gender,
        "language": patient.preferred_language,
        "counts": {
            "encounters": len(encounters),
            "prescriptions": sum(1 for d in documents if d.document_kind == "prescription"),
            "labReports": sum(1 for d in documents if d.document_kind == "lab_report"),
            "otherDocuments": sum(
                1 for d in documents if d.document_kind not in ("prescription", "lab_report")
            ),
            "medications": len({m.normalized_name for m in medications}),
            "observations": len(observations),
        },
        "recent": [
            {
                "encounterRef": e.encounter_ref,
                "occurredOn": e.occurred_at.date().isoformat(),
                "headline": e.headline or "Clinical encounter",
                "priority": e.priority,
                "ayush": e.ayush_mode,
            }
            for e in encounters[:6]
        ],
    }


def _mask(abha_ref: str | None) -> str | None:
    """Show enough to recognise, not enough to identify."""
    if not abha_ref:
        return None
    tail = abha_ref[-4:]
    return f"**** **** {tail}"


async def timeline(
    db: AsyncSession, patient_id: int, *, kinds: list[str] | None = None
) -> list[dict[str, Any]]:
    """Every event across every confirmed encounter, newest first, undated last."""
    statement = select(TimelineEventRecord).where(TimelineEventRecord.patient_id == patient_id)
    if kinds:
        statement = statement.where(TimelineEventRecord.kind.in_(kinds))
    rows = list((await db.execute(statement)).scalars().all())

    encounters = {
        e.id: e for e in await encounters_for(db, patient_id)
    }

    def sort_key(row: TimelineEventRecord) -> tuple[int, float]:
        if row.occurred_on is None:
            return (1, 0.0)
        return (0, -row.occurred_on.toordinal())

    return [
        {
            "eventRef": row.event_ref,
            "occurredOn": row.occurred_on.isoformat() if row.occurred_on else None,
            "datePrecision": row.date_precision,
            "kind": row.kind,
            "label": row.label,
            "detail": row.detail,
            "documentRef": row.source_document_ref,
            "factRef": row.source_fact_ref,
            "lowConfidence": row.low_confidence,
            "encounterRef": (
                encounters[row.encounter_id].encounter_ref
                if row.encounter_id in encounters
                else None
            ),
        }
        for row in sorted(rows, key=sort_key)
    ]


@dataclass(slots=True)
class MedicationThread:
    """Every mention of one drug across every visit, and whether the sources agree."""

    name: str
    normalized: str
    mentions: list[dict[str, Any]] = field(default_factory=list)
    needs_reconciliation: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "normalized": self.normalized,
            "mentions": self.mentions,
            "needsReconciliation": self.needs_reconciliation,
            "reason": self.reason,
        }


async def medication_history(db: AsyncSession, patient_id: int) -> list[dict[str, Any]]:
    """Group medications by drug across visits. Reports provenance, never current state."""
    rows = list(
        (
            await db.execute(
                select(MedicationEvent)
                .where(MedicationEvent.patient_id == patient_id)
                .order_by(MedicationEvent.observed_on, MedicationEvent.recorded_at)
            )
        ).scalars().all()
    )
    encounters = {e.id: e for e in await encounters_for(db, patient_id)}

    threads: dict[str, MedicationThread] = {}
    for row in rows:
        thread = threads.setdefault(
            row.normalized_name, MedicationThread(name=row.name, normalized=row.normalized_name)
        )
        encounter = encounters.get(row.encounter_id)
        thread.mentions.append(
            {
                "status": row.status,
                "dose": row.dose,
                "frequency": row.frequency,
                "observedOn": row.observed_on.isoformat() if row.observed_on else None,
                "documentRef": row.source_document_ref,
                "encounterRef": encounter.encounter_ref if encounter else None,
                "encounterOn": (
                    encounter.occurred_at.date().isoformat() if encounter else None
                ),
                "howWeKnow": _how_we_know(row.status),
            }
        )

    latest_encounter = max(encounters.values(), key=lambda e: e.occurred_at, default=None)
    denial = await _denies_medication(db, latest_encounter)

    for thread in threads.values():
        statuses = {m["status"] for m in thread.mentions}
        # Documented in the past, and the patient now says they take nothing.
        if denial and "documented" in statuses:
            thread.needs_reconciliation = True
            thread.reason = (
                "A document records this medicine, and the patient reported taking none at "
                "the most recent visit. Needs medication reconciliation."
            )
        elif {"documented", "stopped-reported"} <= statuses:
            thread.needs_reconciliation = True
            thread.reason = "Documented, and separately reported as stopped."

    return [thread.to_dict() for thread in threads.values()]


def _how_we_know(status: str) -> str:
    return {
        "documented": "found in an uploaded document",
        "patient-reported-current": "the patient said they take this",
        "historical": "recorded at a previous visit, not mentioned since",
        "stopped-reported": "the patient said they stopped",
        "uncertain": "source unclear",
    }.get(status, status)


async def _denies_medication(db: AsyncSession, encounter: Encounter | None) -> bool:
    if encounter is None:
        return False
    row = (
        await db.execute(
            select(ClinicalFactRecord).where(
                ClinicalFactRecord.encounter_id == encounter.id,
                ClinicalFactRecord.path == "drug_allergy.taking_medicines",
            )
        )
    ).scalars().first()
    return bool(row and (row.value_json or {}).get("v") is False)


@dataclass(slots=True)
class SimilarEncounter:
    encounter_ref: str
    occurred_on: str
    headline: str | None
    shared: list[dict[str, str]]
    #: A count of shared features, NOT a probability and NOT a clinical judgement.
    shared_count: int
    band: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "encounterRef": self.encounter_ref,
            "occurredOn": self.occurred_on,
            "headline": self.headline,
            "shared": self.shared,
            "sharedCount": self.shared_count,
            "band": self.band,
            "note": (
                "A count of features this visit shares with that one. Not a probability, "
                "not a diagnosis, and not a clinical judgement."
            ),
        }


async def _feature_set(db: AsyncSession, encounter_id: int) -> dict[str, set[str]]:
    rows = list(
        (
            await db.execute(
                select(ClinicalFactRecord).where(
                    ClinicalFactRecord.encounter_id == encounter_id,
                    ClinicalFactRecord.path.in_(SIMILARITY_PATHS),
                )
            )
        ).scalars().all()
    )
    features: dict[str, set[str]] = {}
    for row in rows:
        raw = (row.value_json or {}).get("v")
        values = raw if isinstance(raw, list) else [raw]
        cleaned = {str(v) for v in values if v not in (None, "", "none")}
        if cleaned:
            features.setdefault(row.path, set()).update(cleaned)
    return features


def _band(count: int) -> str:
    """Words, not a percentage. A number here invites being read as a probability."""
    if count >= 4:
        return "many shared features"
    if count >= 2:
        return "some shared features"
    return "one shared feature"


async def similar_encounters(
    db: AsyncSession,
    *,
    patient_id: int,
    current_features: dict[str, set[str]],
    exclude_encounter_id: int | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Prior visits of THE SAME PATIENT that share recorded features with this one."""
    candidates = [
        e
        for e in await encounters_for(db, patient_id)
        if e.id != exclude_encounter_id
    ]

    scored: list[SimilarEncounter] = []
    for candidate in candidates:
        past = await _feature_set(db, candidate.id)
        shared: list[dict[str, str]] = []
        for path, values in current_features.items():
            overlap = values & past.get(path, set())
            for value in sorted(overlap):
                shared.append(
                    {"feature": FEATURE_LABELS.get(path, path), "value": value, "path": path}
                )
        if not shared:
            continue
        scored.append(
            SimilarEncounter(
                encounter_ref=candidate.encounter_ref,
                occurred_on=candidate.occurred_at.date().isoformat(),
                headline=candidate.headline,
                shared=shared,
                shared_count=len(shared),
                band=_band(len(shared)),
            )
        )

    scored.sort(key=lambda s: (-s.shared_count, s.occurred_on))
    return [entry.to_dict() for entry in scored[:limit]]


async def current_features(db: AsyncSession, encounter_id: int) -> dict[str, set[str]]:
    return await _feature_set(db, encounter_id)


async def features_from_ledger(paths_and_values: dict[str, Any]) -> dict[str, set[str]]:
    """Feature set for a session still in capture, so 'similar visits' works before commit."""
    features: dict[str, set[str]] = {}
    for path, raw in paths_and_values.items():
        if path not in SIMILARITY_PATHS:
            continue
        values = raw if isinstance(raw, list) else [raw]
        cleaned = {str(v) for v in values if v not in (None, "", "none")}
        if cleaned:
            features.setdefault(path, set()).update(cleaned)
    return features


async def evidence_for_fact(
    db: AsyncSession, *, encounter_id: int, fact_ref: str
) -> dict[str, Any] | None:
    """Click-to-source for a durable fact, including a link to the document page."""
    fact = (
        await db.execute(
            select(ClinicalFactRecord).where(
                ClinicalFactRecord.encounter_id == encounter_id,
                ClinicalFactRecord.fact_ref == fact_ref,
            )
        )
    ).scalars().first()
    if fact is None:
        return None
    evidence = list(
        (
            await db.execute(select(SourceEvidence).where(SourceEvidence.fact_id == fact.id))
        ).scalars().all()
    )
    return {
        "factRef": fact.fact_ref,
        "path": fact.path,
        "value": (fact.value_json or {}).get("v"),
        "displayValue": fact.display_value,
        "tier": fact.tier,
        "confidence": fact.confidence,
        "confidenceStatus": fact.confidence_status,
        "confirmedByPhysician": fact.confirmed_by_physician,
        "evidence": [
            {
                "sourceType": e.source_type,
                "verbatim": e.verbatim,
                "language": e.language,
                "modality": e.modality,
                "questionId": e.question_id,
                "asrConfidence": e.asr_confidence,
                "documentRef": e.document_ref,
                "page": e.page,
                "bbox": e.bbox_json,
                "ocrConfidence": e.ocr_confidence,
                "handwritten": e.handwritten,
            }
            for e in evidence
        ],
    }


async def open_contradictions(db: AsyncSession, patient_id: int) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(ContradictionRecord).where(
                    ContradictionRecord.patient_id == patient_id,
                    ContradictionRecord.status == "open",
                )
            )
        ).scalars().all()
    )
    return [
        {
            "contradictionRef": row.contradiction_ref,
            "ruleId": row.rule_id,
            "label": row.label,
            "patientSide": row.side_a_json,
            "documentSide": row.side_b_json,
            "clarifyingQuestion": row.clarifying_question,
            "status": row.status,
        }
        for row in rows
    ]


def latest_observation_by_analyte(rows: list[ObservationEvent]) -> dict[str, ObservationEvent]:
    latest: dict[str, ObservationEvent] = {}
    for row in rows:
        key = row.analyte_key or row.display.casefold()
        current = latest.get(key)
        if current is None or _observed(row) >= _observed(current):
            latest[key] = row
    return latest


def _observed(row: ObservationEvent) -> date:
    return row.observed_on or date.min

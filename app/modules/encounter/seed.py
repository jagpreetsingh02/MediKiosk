"""Seed one synthetic patient who already has a history.

The point of the whole longitudinal build is invisible on an empty database: a patient home
screen with nothing on it looks exactly like the single-encounter product it replaced. This
seeds *Demo Patient* with two confirmed prior encounters, a prescription and a lab report, so
the first thing anyone sees is that MediKiosk already knows this person.

Every date, name and value here is invented. The prescription and lab report are the same
synthetic fixtures the OCR benchmark uses, so the extracted entities and their bounding boxes
are genuinely produced by the pipeline rather than hand-written.

Idempotent: seeding twice leaves one patient with two encounters.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.durable import (
    ClinicalFactRecord,
    DocumentRecord,
    Encounter,
    ExtractedDocumentEntity,
    MedicationEvent,
    ObservationEvent,
    Patient,
    PatientIdentifier,
    PhysicianDecision,
    SourceEvidence,
    TimelineEventRecord,
)
from app.modules.documents.pipeline import read_and_extract
from app.modules.encounter.promote import (
    ABHA_SYSTEM,
    STATUS_DOCUMENTED,
    STATUS_REPORTED_CURRENT,
    normalize_medicine,
)

log = get_logger(__name__)

FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "documents"

#: Must match the mock IdP's derivation, or the seeded history will not join to the login.
DEMO_ABHA_ADDRESS = "demo@abdm"


def demo_abha_ref() -> str:
    return "abha:" + hashlib.sha256(DEMO_ABHA_ADDRESS.encode("utf-8")).hexdigest()[:24]


#: The 2025 visit. Chosen so the 2026 intake demo recurs against it: same site, same
#: post-meal pattern, same nausea — which is what makes "similar previous visit" fire on
#: real shared features rather than on a contrived match.
PRIOR_VISIT_FACTS: tuple[tuple[str, Any, str, str], ...] = (
    ("chief_complaint.text", "stomach", "Stomach problem", "confirmed"),
    ("chief_complaint.duration", "week_1", "About a week", "confirmed"),
    ("hpi.site", "abdomen", "Stomach / abdomen", "confirmed"),
    ("hpi.onset", "gradual", "Slowly, over days or weeks", "confirmed"),
    ("hpi.character", "burning", "Burning", "confirmed"),
    ("hpi.timing", "intermittent", "Comes and goes", "confirmed"),
    ("hpi.associated", ["vomiting"], "Vomiting", "confirmed"),
    ("hpi.exacerbating", ["worse_food"], "Worse after eating", "confirmed"),
    ("hpi.severity", 5, "Uncomfortable (5 of 10)", "confirmed"),
    ("past_medical.conditions", ["diabetes"], "Diabetes (sugar)", "confirmed"),
    ("drug_allergy.taking_medicines", True, "Yes", "confirmed"),
    ("personal_history.diet", "mixed", "Both", "confirmed"),
)


async def already_seeded(db: AsyncSession) -> Patient | None:
    return (
        await db.execute(select(Patient).where(Patient.abha_ref == demo_abha_ref()))
    ).scalars().first()


async def seed_demo_patient(db: AsyncSession) -> dict[str, Any]:
    """Create Demo Patient with two prior encounters, a prescription and a lab report."""
    existing = await already_seeded(db)
    if existing is not None:
        encounters = (
            await db.execute(
                select(Encounter).where(Encounter.patient_id == existing.id)
            )
        ).scalars().all()
        return {
            "created": False,
            "patientRef": existing.patient_ref,
            "encounters": len(list(encounters)),
        }

    patient = Patient(
        patient_ref="pat_demo000001",
        abha_ref=demo_abha_ref(),
        display_name="Demo Patient",
        year_of_birth=datetime.now(UTC).year - 52,
        gender="male",
        preferred_language="en",
    )
    db.add(patient)
    await db.flush()
    db.add(
        PatientIdentifier(
            patient_id=patient.id,
            system=ABHA_SYSTEM,
            value=demo_abha_ref(),
            assigner="mock-abdm-idp (synthetic)",
        )
    )

    # ---------------------------------------------------- 2024: a lab report
    lab = await _seed_document_encounter(
        db,
        patient=patient,
        fixture="lab_report_2024-06-03.pdf",
        occurred=datetime(2024, 6, 3, 10, 30, tzinfo=UTC),
        headline="Laboratory report",
        kind="lab_report",
        timeline_kind="investigation",
    )

    # -------------------------------------- 2025 Feb: repeat bloods, before the script
    #
    # THE SERIES IS THE POINT. One lab report is a row of numbers; three, dated, are a
    # trajectory a physician reads at a glance — and this patient's trajectory is the
    # clinical spine of the demo. Values improve after the February 2025 prescription and
    # deteriorate through 2026, which is precisely the period the patient reports taking
    # no medicines. The lab trend and the medication-reconciliation flag are two views of
    # one story, and neither is an inference: both are recorded numbers carrying their own
    # dates and the reference ranges printed on the report a physician can open.
    lab_2025 = await _seed_document_encounter(
        db,
        patient=patient,
        fixture="lab_report_2025-02-10.pdf",
        occurred=datetime(2025, 2, 10, 9, 20, tzinfo=UTC),
        headline="Laboratory report",
        kind="lab_report",
        timeline_kind="investigation",
    )

    # ---------------------------------------------------- 2025 Feb: a prescription
    prescription = await _seed_document_encounter(
        db,
        patient=patient,
        fixture="prescription_2025-02-14.pdf",
        occurred=datetime(2025, 2, 14, 11, 15, tzinfo=UTC),
        headline="Prescription",
        kind="prescription",
        timeline_kind="medication",
    )

    # ------------------------------------------- 2026 Jan: bloods again, worse
    lab_2026 = await _seed_document_encounter(
        db,
        patient=patient,
        fixture="lab_report_2026-01-18.pdf",
        occurred=datetime(2026, 1, 18, 8, 40, tzinfo=UTC),
        headline="Laboratory report",
        kind="lab_report",
        timeline_kind="investigation",
    )

    # ---------------------------------------------------- 2025 Aug: a real visit
    visit = Encounter(
        encounter_ref="enc_demo20250820",
        patient_id=patient.id,
        occurred_at=datetime(2025, 8, 20, 9, 45, tzinfo=UTC),
        kind="intake",
        language="en",
        priority="routine",
        headline="Stomach problem",
        confirmed_by="dr.iyer@aiia (synthetic)",
        completeness=0.87,
        summary_json={"status": "confirmed", "seeded": True},
    )
    db.add(visit)
    await db.flush()

    for path, value, verbatim, tier in PRIOR_VISIT_FACTS:
        fact = ClinicalFactRecord(
            encounter_id=visit.id,
            fact_ref=f"fact_seed{abs(hash(path)) % 10**8:08d}",
            path=path,
            value_json={"v": value},
            display_value=verbatim,
            tier=tier,
            confidence=1.0,
            confidence_status="measured",
            recorded_at=visit.occurred_at,
            confirmed_by_physician=True,
        )
        db.add(fact)
        await db.flush()
        db.add(
            SourceEvidence(
                fact_id=fact.id,
                source_type="utterance",
                verbatim=verbatim,
                language="en",
                modality="touch",
                question_id=path,
            )
        )

    db.add(
        TimelineEventRecord(
            patient_id=patient.id,
            encounter_id=visit.id,
            event_ref="evt_demo20250820",
            occurred_on=visit.occurred_at.date(),
            date_precision="exact",
            kind="encounter",
            label="Stomach problem — burning, worse after eating, vomiting",
            detail="Confirmed by dr.iyer@aiia (synthetic)",
        )
    )
    db.add(
        MedicationEvent(
            patient_id=patient.id,
            encounter_id=visit.id,
            name="Metformin",
            normalized_name=normalize_medicine("Metformin"),
            dose="500MG",
            frequency="1-0-1",
            status=STATUS_REPORTED_CURRENT,
            observed_on=visit.occurred_at.date(),
        )
    )
    db.add(
        PhysicianDecision(
            encounter_id=visit.id,
            decision="confirmed_summary",
            actor="dr.iyer@aiia (synthetic)",
            detail_json={"seeded": True},
        )
    )

    await db.flush()
    documents = [lab, lab_2025, lab_2026, prescription]
    log.info(
        "demo.patient_seeded",
        patient=patient.patient_ref,
        encounters=5,
        documents=documents,
    )
    return {
        "created": True,
        "patientRef": patient.patient_ref,
        "abhaRef": patient.abha_ref,
        "encounters": 5,
        "documents": documents,
    }


async def _seed_document_encounter(
    db: AsyncSession,
    *,
    patient: Patient,
    fixture: str,
    occurred: datetime,
    headline: str,
    kind: str,
    timeline_kind: str,
) -> str:
    """One historical encounter that exists because a document was filed.

    The entities are produced by running the real OCR pipeline over the real fixture, so the
    bounding boxes a physician clicks on in 2026 are the ones the extractor actually found.
    """
    path = FIXTURES / fixture
    content = path.read_bytes() if path.exists() else None

    encounter = Encounter(
        encounter_ref=f"enc_demo{occurred:%Y%m%d}",
        patient_id=patient.id,
        occurred_at=occurred,
        kind="document",
        language="en",
        priority="routine",
        headline=headline,
        confirmed_by="dr.iyer@aiia (synthetic)",
        completeness=0.0,
        summary_json={"status": "confirmed", "seeded": True},
    )
    db.add(encounter)
    await db.flush()

    document = DocumentRecord(
        encounter_id=encounter.id,
        document_ref=f"doc_demo{occurred:%Y%m%d}",
        filename=fixture,
        media_type="application/pdf",
        document_kind=kind,
        pages=1,
        ocr_backend="textlayer",
        mean_confidence=0.99,
        document_date=occurred.date(),
        verified_by="dr.iyer@aiia (synthetic)",
        content=content,
        uploaded_at=occurred,
    )
    db.add(document)
    await db.flush()

    if content is None:
        return document.document_ref

    # THROUGH THE PIPELINE'S FRONT DOOR, not around it. This used to call
    # `get_ocr_backend("textlayer").read(...)` and `extract_entities(...)` directly, which is
    # how the demo patient's lab reports came to be described as having gone "through the
    # actual OCR pipeline" when they had skipped the route, the gate and this module.
    #
    # Note it no longer pins `textlayer` either: the engine is chosen from what the file
    # actually is, exactly as it is for a patient upload. These fixtures are digital PDFs so
    # the text-layer reader still wins — but by the same rule, not by a private exception.
    _ocr, confident, _needs_check = read_and_extract(
        content,
        filename=fixture,
        media_type="application/pdf",
        sex=patient.gender,
    )

    for position, entity in enumerate(confident):
        db.add(
            ExtractedDocumentEntity(
                document_id=document.id,
                kind=entity.kind,
                text=entity.text,
                source_text=entity.source_text,
                detail_json=entity.detail,
                page=entity.page,
                bbox_json=entity.bbox.model_dump(),
                confidence=entity.confidence,
                handwritten=entity.handwritten,
                observed_on=entity.observed_on or occurred.date(),
                verification="accepted",
                verified_by="dr.iyer@aiia (synthetic)",
            )
        )

        if entity.kind == "medication":
            db.add(
                MedicationEvent(
                    patient_id=patient.id,
                    encounter_id=encounter.id,
                    name=entity.text,
                    normalized_name=normalize_medicine(entity.text),
                    dose=entity.detail.get("dose"),
                    frequency=entity.detail.get("frequencyRaw"),
                    duration=entity.detail.get("duration"),
                    route=entity.detail.get("route"),
                    status=STATUS_DOCUMENTED,
                    observed_on=entity.observed_on or occurred.date(),
                    source_document_ref=document.document_ref,
                )
            )
        elif entity.kind == "investigation":
            db.add(
                ObservationEvent(
                    patient_id=patient.id,
                    encounter_id=encounter.id,
                    analyte_key=entity.detail.get("analyteKey"),
                    display=entity.detail.get("display") or entity.text,
                    value=_as_float(entity.detail.get("value")),
                    unit=entity.detail.get("unit"),
                    reference_low=entity.detail.get("referenceLow"),
                    reference_high=entity.detail.get("referenceHigh"),
                    range_flag=entity.detail.get("rangeFlag", "unknown"),
                    range_source=entity.detail.get("rangeSource", "none"),
                    observed_on=entity.observed_on or occurred.date(),
                    source_document_ref=document.document_ref,
                )
            )

        db.add(
            TimelineEventRecord(
                patient_id=patient.id,
                encounter_id=encounter.id,
                # Indexed by position, not by len(entity.text): two entities of the same
                # text length on one page collided, so a lab report filed two results
                # under one event reference and "open this event" was ambiguous between
                # them. The truncation to 32 characters made it likelier still.
                event_ref=f"evt_{document.document_ref}_{position}",
                occurred_on=entity.observed_on or occurred.date(),
                date_precision="exact",
                kind=timeline_kind if entity.kind != "diagnosis" else "diagnosis",
                label=_timeline_label(entity),
                detail=f"From {headline.lower()} filed {occurred:%d %b %Y}",
                source_document_ref=document.document_ref,
            )
        )

    await db.flush()
    return document.document_ref


def _timeline_label(entity: Any) -> str:
    detail = entity.detail
    if entity.kind == "medication":
        return " ".join(
            part for part in (entity.text, detail.get("dose"), detail.get("frequency")) if part
        )
    if entity.kind == "investigation":
        analyte = detail.get("display") or entity.text
        return f"{analyte} {detail.get('value')} {detail.get('unit') or ''}".strip()
    return entity.text


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None

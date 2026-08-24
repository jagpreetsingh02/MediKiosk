"""⛔ Promotion — the one path from a capture session into the durable record.

The ordering here is the whole point, and it is the reason `IntakeSession` was not simply
renamed `Encounter`:

    validate the draft is fully traceable
        └─▶ create or find the Patient
              └─▶ create the durable Encounter
                    └─▶ persist facts, evidence, medications, observations,
                        documents, timeline, red flags, the decision
                          └─▶ commit
                                └─▶ ONLY NOW purge the capture session

`promote()` does not purge. It returns, the caller commits, and the caller purges. A purge
that ran before the promotion committed would destroy a patient's visit on any failure after
it — and a half-promoted encounter is worse than a lost one, because it looks complete.

Medication status is the other load-bearing decision. A prescription found in a document is
`documented`; a patient saying they take something is `patient-reported-current`; the same
medicine seen in a *previous* encounter and not mentioned today stays `historical`. Nothing
here concludes that a medicine is currently being taken because it was once prescribed.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.contradictions import Contradiction
from app.contracts.history import ClinicalHistory
from app.contracts.record import FactLedger
from app.core.errors import InvariantViolation
from app.core.logging import get_logger
from app.db.durable import (
    ClinicalFactRecord,
    ContradictionRecord,
    DocumentRecord,
    Encounter,
    ExtractedDocumentEntity,
    MedicationEvent,
    ObservationEvent,
    Patient,
    PatientIdentifier,
    PhysicianDecision,
    RedFlagEventRecord,
    SourceEvidence,
    TimelineEventRecord,
)
from app.db.models import IntakeSession, SessionDocument
from app.redflags.engine import Escalation

log = get_logger(__name__)

ABHA_SYSTEM = "https://healthid.abdm.gov.in/"

#: Medication provenance → status. Never "is the patient taking this", only "how we know".
STATUS_DOCUMENTED = "documented"
STATUS_REPORTED_CURRENT = "patient-reported-current"
STATUS_HISTORICAL = "historical"
STATUS_STOPPED = "stopped-reported"
STATUS_UNCERTAIN = "uncertain"


def _ref(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_medicine(name: str) -> str:
    """Fold for matching the same drug across visits. Display always uses the original."""
    return _NON_WORD.sub(" ", name.casefold()).strip()


@dataclass(slots=True)
class PromotionResult:
    patient_ref: str
    encounter_ref: str
    facts: int = 0
    evidence: int = 0
    medications: int = 0
    observations: int = 0
    documents: int = 0
    timeline_events: int = 0
    red_flag_events: int = 0
    contradictions: int = 0
    created_patient: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patientRef": self.patient_ref,
            "encounterRef": self.encounter_ref,
            "createdPatient": self.created_patient,
            "facts": self.facts,
            "evidence": self.evidence,
            "medications": self.medications,
            "observations": self.observations,
            "documents": self.documents,
            "timelineEvents": self.timeline_events,
            "redFlagEvents": self.red_flag_events,
            "contradictions": self.contradictions,
            "warnings": self.warnings,
        }


async def find_or_create_patient(
    db: AsyncSession,
    *,
    abha_ref: str | None,
    display_name: str | None = None,
    age_years: int | None = None,
    gender: str | None = None,
    language: str = "en",
) -> tuple[Patient, bool]:
    """Resolve the person this visit belongs to. `abha_ref` is the join key across visits."""
    if abha_ref:
        existing = (
            await db.execute(select(Patient).where(Patient.abha_ref == abha_ref))
        ).scalars().first()
        if existing is not None:
            # Fill in anything we did not know before, but never overwrite what we did.
            if display_name and not existing.display_name:
                existing.display_name = display_name
            if gender and not existing.gender:
                existing.gender = gender
            return existing, False

    patient = Patient(
        patient_ref=_ref("pat"),
        abha_ref=abha_ref,
        display_name=display_name,
        year_of_birth=(datetime.now(UTC).year - age_years) if age_years else None,
        gender=gender,
        preferred_language=language,
    )
    db.add(patient)
    await db.flush()
    if abha_ref:
        db.add(
            PatientIdentifier(
                patient_id=patient.id,
                system=ABHA_SYSTEM,
                value=abha_ref,
                assigner="mock-abdm-idp",
            )
        )
    log.info("patient.created", patient=patient.patient_ref, linked=bool(abha_ref))
    return patient, True


async def promote(
    db: AsyncSession,
    *,
    session_row: IntakeSession,
    ledger: FactLedger,
    history: ClinicalHistory,
    escalation: Escalation,
    contradictions: list[Contradiction],
    summary_payload: dict[str, Any],
    traceable: bool,
    confirmed_by: str,
) -> PromotionResult:
    """Promote a confirmed capture session into a durable encounter.

    Raises before writing anything if the draft is not fully traceable — an untraceable
    summary must not become part of a patient's permanent record (Invariant 2 and 4 together).
    """
    if not traceable:
        raise InvariantViolation(
            "Refusing to promote an untraceable draft into the durable record. Every clinical "
            "claim must resolve to a recorded fact before a physician's confirmation can make "
            "it permanent."
        )

    demographics = history.demographics
    patient, created = await find_or_create_patient(
        db,
        abha_ref=session_row.abha_ref,
        display_name=demographics.display_name,
        age_years=demographics.age_years,
        gender=demographics.gender,
        language=session_row.language,
    )

    complaint = history.chief_complaint.slots.get("chief_complaint.text")
    encounter = Encounter(
        encounter_ref=_ref("enc"),
        patient_id=patient.id,
        source_session_ref=session_row.session_ref,
        occurred_at=session_row.created_at or datetime.now(UTC),
        kind="intake",
        language=session_row.language,
        ayush_mode=session_row.ayush_mode,
        priority=session_row.priority,
        headline=(str(complaint.value) if complaint and complaint.recorded else None),
        confirmed_by=confirmed_by,
        summary_json=summary_payload,
        completeness=history.overall_completeness,
    )
    db.add(encounter)
    await db.flush()

    result = PromotionResult(
        patient_ref=patient.patient_ref,
        encounter_ref=encounter.encounter_ref,
        created_patient=created,
    )

    # ---- facts + their evidence ------------------------------------------
    slots_by_path = {slot.path: slot for slot in history.all_slots().values()}
    fact_row_by_ref: dict[str, ClinicalFactRecord] = {}

    for fact in ledger.facts:
        span = fact.source
        slot = slots_by_path.get(fact.path)
        row = ClinicalFactRecord(
            encounter_id=encounter.id,
            fact_ref=fact.fact_id,
            path=fact.path,
            value_json={"v": fact.value},
            display_value=(
                ", ".join(str(v) for v in slot.value)
                if slot and isinstance(slot.value, list)
                else (str(slot.value) if slot and slot.recorded else str(fact.value))
            ),
            tier=fact.tier.value,
            confidence=fact.confidence,
            confidence_status=(
                "unavailable" if getattr(span, "asr_confidence", None) is None
                and getattr(getattr(span, "modality", None), "value", None) == "speech"
                else "measured"
            ),
            recorded_at=fact.recorded_at,
        )
        db.add(row)
        await db.flush()
        fact_row_by_ref[fact.fact_id] = row
        result.facts += 1

        bbox = getattr(span, "bbox", None)
        db.add(
            SourceEvidence(
                fact_id=row.id,
                source_type=span.kind,
                verbatim=span.verbatim,
                language=span.language,
                modality=getattr(getattr(span, "modality", None), "value", None),
                question_id=getattr(span, "question_id", None),
                turn_id=getattr(span, "turn_id", None),
                asr_confidence=getattr(span, "asr_confidence", None),
                document_ref=getattr(span, "document_id", None),
                page=getattr(span, "page", None),
                bbox_json=bbox.model_dump() if bbox is not None else None,
                ocr_confidence=getattr(span, "ocr_confidence", None),
                handwritten=bool(getattr(span, "handwritten", False)),
            )
        )
        result.evidence += 1

    # ---- documents, with the bytes kept so evidence can be shown ----------
    session_documents = (
        await db.execute(
            select(SessionDocument).where(SessionDocument.session_id == session_row.id)
        )
    ).scalars().all()

    document_rows: dict[str, DocumentRecord] = {}
    for source in session_documents:
        document_date = _document_date_from(source.entities_json or [])
        document_row = DocumentRecord(
            encounter_id=encounter.id,
            document_ref=source.document_id,
            filename=source.filename,
            media_type=source.media_type,
            document_kind=_classify_document(source.entities_json or []),
            pages=source.pages,
            ocr_backend=source.ocr_backend,
            mean_confidence=source.mean_confidence,
            document_date=document_date,
            verified_by=source.verified_by,
            content=source.content,
            uploaded_at=source.uploaded_at,
        )
        db.add(document_row)
        await db.flush()
        document_rows[source.document_id] = document_row
        result.documents += 1

        for payload in source.entities_json or []:
            # A low-confidence entity that no human accepted must not become durable truth.
            if payload.get("entityIndex") is not None and not source.verified_by:
                result.warnings.append(
                    f"{payload.get('text', 'an entity')} was left unverified and was not "
                    "promoted."
                )
                continue
            db.add(
                ExtractedDocumentEntity(
                    document_id=document_row.id,
                    kind=payload["kind"],
                    text=payload["text"],
                    source_text=payload["sourceText"],
                    detail_json=payload.get("detail"),
                    page=int(payload.get("page", 1)),
                    bbox_json=payload.get("bbox"),
                    confidence=float(payload.get("confidence", 0.0)),
                    handwritten=bool(payload.get("handwritten", False)),
                    observed_on=_as_date(payload.get("observedOn")),
                    verification=(
                        "accepted" if payload.get("entityIndex") is None else "corrected"
                    ),
                    verified_by=source.verified_by,
                )
            )

    # ---- medications and observations ------------------------------------
    for medication in history.medications:
        if not medication.name.recorded:
            continue
        med_span = _span_for(ledger, medication.name.fact_ids)
        document_ref = getattr(med_span, "document_id", None)
        from_document = document_ref is not None
        # A medicine read off a document is dated by that document, not by today. Dating it
        # today would make a two-year-old prescription look like a current one.
        observed = (
            document_rows[document_ref].document_date
            if document_ref in document_rows
            else None
        )
        db.add(
            MedicationEvent(
                patient_id=patient.id,
                encounter_id=encounter.id,
                name=str(medication.name.value),
                normalized_name=normalize_medicine(str(medication.name.value)),
                dose=str(medication.dose.value) if medication.dose.recorded else None,
                frequency=(
                    str(medication.frequency.value) if medication.frequency.recorded else None
                ),
                route=str(medication.route.value) if medication.route.recorded else None,
                status=STATUS_DOCUMENTED if from_document else STATUS_REPORTED_CURRENT,
                observed_on=observed,
                source_document_ref=document_ref,
                source_fact_ref=(
                    medication.name.fact_ids[0] if medication.name.fact_ids else None
                ),
                coding_json=medication.coding,
            )
        )
        result.medications += 1

    for investigation in history.investigations:
        if not investigation.analyte.recorded:
            continue
        inv_span = _span_for(ledger, investigation.analyte.fact_ids)
        document_ref = getattr(inv_span, "document_id", None)
        db.add(
            ObservationEvent(
                patient_id=patient.id,
                encounter_id=encounter.id,
                analyte_key=None,
                display=str(investigation.analyte.value),
                value=_as_float(investigation.value.value),
                value_text=(
                    str(investigation.value.value) if investigation.value.recorded else None
                ),
                unit=investigation.unit,
                reference_low=investigation.reference_low,
                reference_high=investigation.reference_high,
                range_flag=investigation.range_flag,
                observed_on=investigation.observed_on
                or (
                    document_rows[document_ref].document_date
                    if document_ref in document_rows
                    else None
                ),
                source_document_ref=document_ref,
            )
        )
        result.observations += 1

    # ---- timeline: the encounter itself, then everything inside it --------
    db.add(
        TimelineEventRecord(
            patient_id=patient.id,
            encounter_id=encounter.id,
            event_ref=_ref("evt"),
            occurred_on=(encounter.occurred_at or datetime.now(UTC)).date(),
            date_precision="exact",
            kind="encounter",
            label=encounter.headline or "Clinical encounter",
            detail=f"Confirmed by {confirmed_by}",
        )
    )
    result.timeline_events += 1

    for event in history.timeline:
        db.add(
            TimelineEventRecord(
                patient_id=patient.id,
                encounter_id=encounter.id,
                event_ref=event.event_id,
                occurred_on=event.occurred_on,
                date_precision=event.date_precision,
                kind=event.kind,
                label=event.label,
                detail=event.detail,
                source_document_ref=event.document_id,
                source_fact_ref=event.fact_ids[0] if event.fact_ids else None,
                low_confidence=event.low_confidence,
            )
        )
        result.timeline_events += 1

    # ---- red flags: every evaluation, fired or not ------------------------
    for proposal in escalation.proposals:
        db.add(
            RedFlagEventRecord(
                encounter_id=encounter.id,
                rule_id=proposal.rule_id,
                fired=proposal.fired,
                level=proposal.level,
                rationale=proposal.rationale,
                evidence_json=proposal.triggering_paths or None,
            )
        )
        result.red_flag_events += 1

    # ---- contradictions ---------------------------------------------------
    for conflict in contradictions:
        db.add(
            ContradictionRecord(
                patient_id=patient.id,
                encounter_id=encounter.id,
                contradiction_ref=conflict.contradiction_id,
                rule_id=conflict.rule_id,
                label=conflict.label,
                side_a_json=conflict.patient_side.model_dump(mode="json", by_alias=True),
                side_b_json=conflict.document_side.model_dump(mode="json", by_alias=True),
                clarifying_question=conflict.clarifying_question,
                status=conflict.status,
            )
        )
        result.contradictions += 1

    db.add(
        PhysicianDecision(
            encounter_id=encounter.id,
            decision="confirmed_summary",
            actor=confirmed_by,
            detail_json={
                "completeness": history.overall_completeness,
                "priority": session_row.priority,
                "facts": result.facts,
            },
        )
    )

    await db.flush()
    log.info(
        "encounter.promoted",
        patient=patient.patient_ref, encounter=encounter.encounter_ref,
        facts=result.facts, medications=result.medications,
        documents=result.documents, timeline=result.timeline_events,
    )
    return result


# ---------------------------------------------------------------- helpers


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _span_for(ledger: FactLedger, fact_ids: list[str]) -> Any | None:
    """The source span behind the first of these facts, if any."""
    for fact_id in fact_ids:
        fact = ledger.by_id(fact_id)
        if fact is not None:
            return fact.source
    return None


def _classify_document(entities: list[dict[str, Any]]) -> str:
    kinds = {e.get("kind") for e in entities}
    if "investigation" in kinds and "medication" not in kinds:
        return "lab_report"
    if "medication" in kinds:
        return "prescription"
    if "procedure" in kinds or "diagnosis" in kinds:
        return "discharge_summary"
    return "other"


def _document_date_from(entities: list[dict[str, Any]]) -> date | None:
    for entity in entities:
        if entity.get("detail", {}).get("dateSource") == "document_header":
            return _as_date(entity.get("observedOn"))
    for entity in entities:
        parsed = _as_date(entity.get("observedOn"))
        if parsed:
            return parsed
    return None

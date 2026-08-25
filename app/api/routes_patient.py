"""The longitudinal patient surface: memory, timeline, medications, similar visits, evidence.

Every route here reads the durable tables and is scoped to one patient. `_resolve()` is the
authorisation choke point: a patient token may only reach its *own* record, matched on the
`abha_ref` in the token, and only a clinician may name a patient by reference. Without that,
a patient reference in a URL would be enough to read somebody else's history.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentIdentity, DbSession, require_action, require_any_action
from app.audit.chain import record
from app.core.errors import PolicyDenied, ValidationError
from app.db.durable import DocumentRecord, Encounter, Patient
from app.modules.documents.render import render_page_png
from app.modules.encounter import history as H
from app.modules.encounter import report as R
from app.modules.report import brief as B
from app.modules.report import loader as L
from app.modules.report.patient_view import to_patient_view

router = APIRouter(prefix="/api/v1/patients", tags=["patient-memory"])


async def _resolve(db: DbSession, identity: CurrentIdentity, patient_ref: str) -> Patient:
    """Find the patient, and refuse if this caller has no business reading them.

    A patient token carries a pseudonymous `abha_ref`; it may read exactly the record that
    reference resolves to. Staff roles may read any patient, which is what a clinician needs
    and what the ABAC policy already grants them through `session.read`.
    """
    patient = await H.get_patient(db, patient_ref=patient_ref)
    if patient is None:
        raise ValidationError(f"No patient {patient_ref!r}.")

    if identity.role == "patient":
        if not identity.abha_ref or identity.abha_ref != patient.abha_ref:
            raise PolicyDenied(
                "A patient may only read their own record. This reference belongs to "
                "somebody else."
            )
    elif identity.role not in ("clinician", "auditor"):
        raise PolicyDenied(f"Role {identity.role!r} may not read a patient record.")
    return patient


@router.get("/me")
async def my_record(db: DbSession, identity: CurrentIdentity) -> dict[str, Any]:
    """The patient home screen — resolved from the token, so no reference is ever guessable."""
    if not identity.abha_ref:
        raise PolicyDenied("This token carries no ABHA reference, so it has no record.")
    patient = await H.get_patient_by_abha(db, abha_ref=identity.abha_ref)
    if patient is None:
        # A first-time patient is not an error. They simply have no history yet.
        return {
            "known": False,
            "abhaMasked": None,
            "counts": {"encounters": 0, "prescriptions": 0, "labReports": 0},
            "recent": [],
            "note": "No previous visits on file. This will be your first.",
        }
    return {"known": True, **await H.overview(db, patient)}


@router.get("/{patient_ref}", dependencies=[Depends(require_action("session.read"))])
async def patient_overview(
    db: DbSession, patient_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    patient = await _resolve(db, identity, patient_ref)
    return {"known": True, **await H.overview(db, patient)}


@router.get("/{patient_ref}/timeline", dependencies=[Depends(require_action("session.read"))])
async def patient_timeline(
    db: DbSession,
    patient_ref: str,
    identity: CurrentIdentity,
    kinds: str | None = None,
) -> dict[str, Any]:
    """Every event across every confirmed encounter. `kinds` is a comma-separated filter."""
    patient = await _resolve(db, identity, patient_ref)
    wanted = [k.strip() for k in kinds.split(",")] if kinds else None
    events = await H.timeline(db, patient.id, kinds=wanted)
    return {
        "patientRef": patient.patient_ref,
        "count": len(events),
        "events": events,
        "availableKinds": sorted({e["kind"] for e in await H.timeline(db, patient.id)}),
    }


@router.get(
    "/{patient_ref}/medications", dependencies=[Depends(require_action("session.read"))]
)
async def patient_medications(
    db: DbSession, patient_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """Medication history grouped by drug, reporting how each mention is known."""
    patient = await _resolve(db, identity, patient_ref)
    threads = await H.medication_history(db, patient.id)
    return {
        "patientRef": patient.patient_ref,
        "medications": threads,
        "needsReconciliation": [t["name"] for t in threads if t["needsReconciliation"]],
        "note": (
            "Status describes how each mention is KNOWN, not whether the patient is taking "
            "the medicine today. A past prescription is not evidence of current use."
        ),
    }


@router.get("/{patient_ref}/report", dependencies=[Depends(require_action("session.read"))])
async def clinical_report(
    db: DbSession, patient_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """The clinical brief: what the physician gets back for the intake they were given.

    Everything upstream is capture. This is the return value — lab trajectories, the
    medication picture with its provenance, how often this complaint has brought the
    patient in, what changed since last time, and which deterministic rules fired.

    It contains no assessment. Every number is a recorded measurement or arithmetic
    between recorded measurements, which is what keeps a chart on the physician's screen
    on the right side of Invariant 1.
    """
    patient = await _resolve(db, identity, patient_ref)
    built = await R.build(db, patient)
    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="report.read",
        abha_ref=patient.abha_ref,
        request_summary={"patientRef": patient.patient_ref},
        response_summary={
            "trends": len(built["trends"]),
            "medications": built["medications"]["count"],
        },
    )
    return built


@router.get(
    "/{patient_ref}/contradictions", dependencies=[Depends(require_action("session.read"))]
)
async def patient_contradictions(
    db: DbSession, patient_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    patient = await _resolve(db, identity, patient_ref)
    return {
        "patientRef": patient.patient_ref,
        "contradictions": await H.open_contradictions(db, patient.id),
    }


@router.get(
    "/{patient_ref}/encounters/{encounter_ref}",
    dependencies=[Depends(require_action("session.read"))],
)
async def encounter_detail(
    db: DbSession, patient_ref: str, encounter_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    from sqlalchemy import select

    patient = await _resolve(db, identity, patient_ref)
    encounter = (
        await db.execute(
            select(Encounter).where(
                Encounter.encounter_ref == encounter_ref,
                Encounter.patient_id == patient.id,
            )
        )
    ).scalars().first()
    if encounter is None:
        raise ValidationError(f"No encounter {encounter_ref!r} for this patient.")

    features = await H.current_features(db, encounter.id)
    return {
        "encounterRef": encounter.encounter_ref,
        "occurredOn": encounter.occurred_at.date().isoformat(),
        "headline": encounter.headline,
        "priority": encounter.priority,
        "ayushMode": encounter.ayush_mode,
        "confirmedBy": encounter.confirmed_by,
        "completeness": encounter.completeness,
        "summary": encounter.summary_json,
        "features": {path: sorted(values) for path, values in features.items()},
        "similar": await H.similar_encounters(
            db,
            patient_id=patient.id,
            current_features=features,
            exclude_encounter_id=encounter.id,
        ),
    }


@router.get(
    "/{patient_ref}/encounters/{encounter_ref}/facts/{fact_ref}",
    dependencies=[Depends(require_action("fact.read"))],
)
async def durable_fact_evidence(
    db: DbSession,
    patient_ref: str,
    encounter_ref: str,
    fact_ref: str,
    identity: CurrentIdentity,
) -> dict[str, Any]:
    """Click-to-source for a fact in a *past* encounter."""
    from sqlalchemy import select

    patient = await _resolve(db, identity, patient_ref)
    encounter = (
        await db.execute(
            select(Encounter).where(
                Encounter.encounter_ref == encounter_ref,
                Encounter.patient_id == patient.id,
            )
        )
    ).scalars().first()
    if encounter is None:
        raise ValidationError(f"No encounter {encounter_ref!r} for this patient.")
    found = await H.evidence_for_fact(db, encounter_id=encounter.id, fact_ref=fact_ref)
    if found is None:
        raise ValidationError(f"No fact {fact_ref!r} in that encounter.")
    return found


@router.get(
    "/{patient_ref}/documents/{document_ref}/file",
    dependencies=[Depends(require_action("document.read"))],
)
async def document_file(
    db: DbSession,
    patient_ref: str,
    document_ref: str,
    identity: CurrentIdentity,
    page: int | None = None,
) -> Response:
    """The original document, so the evidence drawer can show the page OCR read.

    A bounding box drawn on an empty rectangle is not evidence. This is the route that makes
    the drawer show the actual prescription — synthetic, and only for a confirmed encounter
    the physician committed.
    """
    from sqlalchemy import select

    patient = await _resolve(db, identity, patient_ref)
    document = (
        await db.execute(
            select(DocumentRecord)
            .join(Encounter, DocumentRecord.encounter_id == Encounter.id)
            .where(
                DocumentRecord.document_ref == document_ref,
                Encounter.patient_id == patient.id,
            )
        )
    ).scalars().first()
    if document is None or document.content is None:
        raise ValidationError(f"No stored file for document {document_ref!r}.")

    if page is not None:
        return Response(
            content=render_page_png(document.content, media_type=document.media_type, page=page),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="document.view_original",
        abha_ref=patient.abha_ref,
        request_summary={"documentRef": document_ref},
    )
    return Response(
        content=document.content,
        media_type=document.media_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.filename}"',
            "Cache-Control": "no-store",
        },
    )


# ──────────────────────────────────────── the Clinical Intelligence Brief


@router.get(
    "/{patient_ref}/brief",
    dependencies=[Depends(require_any_action("session.read", "report.read_own"))],
)
async def clinical_brief(
    db: DbSession, patient_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """The brief, assembled deterministically from stored rows.

    Two phases, and the split is the point: `load()` reads the database once, `assemble()` is
    a pure function over that frozen read. Two calls on the same rows are byte-identical,
    which is what makes the `factRef`/`evidenceIds` on every line trustworthy — the line and
    the evidence it points at came from the same read.

    Nothing here is generated by a model. See `app/modules/report/brief.py`.
    """
    patient = await _resolve(db, identity, patient_ref)
    rows = await L.load(db, patient)
    payload = B.assemble(rows)
    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="report.read",
        abha_ref=patient.abha_ref,
        request_summary={"patientRef": patient.patient_ref, "audience": "clinician"},
        response_summary={
            "reportVersion": payload["reportVersion"],
            "snapshotItems": len(payload["snapshot"]["items"]),
            "changedNew": len(payload["whatChanged"]["new"]),
        },
    )
    return payload


@router.get(
    "/{patient_ref}/brief/patient",
    dependencies=[Depends(require_any_action("session.read", "report.read_own"))],
)
async def patient_brief(
    db: DbSession, patient_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """The same brief, regrouped for the person it is about.

    DERIVED from the clinician payload rather than assembled separately, so the two can never
    disagree about what is on the record. Internal identifiers, tiers, states and confidence
    numbers are stripped; the fact that something is still unverified is NOT — that is the one
    edit that would make this view dangerous rather than gentler.
    """
    patient = await _resolve(db, identity, patient_ref)
    rows = await L.load(db, patient)
    payload = to_patient_view(B.assemble(rows))
    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="report.read",
        abha_ref=patient.abha_ref,
        request_summary={"patientRef": patient.patient_ref, "audience": "patient"},
        response_summary={"groups": len(payload["groups"])},
    )
    return payload

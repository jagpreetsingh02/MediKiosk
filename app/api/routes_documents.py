"""Document upload, the verification lane, and the timeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import (
    CurrentIdentity,
    DbSession,
    load_context,
    require_action,
    save_context,
)
from app.audit.chain import record
from app.core.errors import ConsentRequired, ValidationError
from app.db.models import SessionDocument
from app.modules.documents.backends import available_backends
from app.modules.documents.pipeline import (
    IngestResult,
    classify_document,
    confidence_band,
    ingest,
    verify_entity,
)
from app.modules.documents.timeline import group_by_period

router = APIRouter(prefix="/api/v1/sessions/{session_ref}/documents", tags=["documents"])


@router.get("/backends")
async def backends() -> dict[str, Any]:
    return {
        "backends": available_backends(),
        "note": (
            "Two implementations behind one protocol so they can be benchmarked. "
            "See eval/ocr_bench.py and docs/EVALUATION.md for the measured numbers."
        ),
    }


@router.post("", status_code=201)
async def upload(
    db: DbSession,
    session_ref: str,
    identity: CurrentIdentity,
    file: Annotated[UploadFile, File()],
    backend: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Upload → OCR → entities → facts → timeline, in one call."""
    context = await load_context(db, session_ref, identity=identity)
    if "documents" not in context.ledger.consent_scopes:
        raise ConsentRequired("The documents scope was not granted for this session.")

    data = await file.read()
    sex = context.state.values.get("demographics.gender")

    result: IngestResult = ingest(
        context.ledger,
        data,
        filename=file.filename or "upload",
        media_type=file.content_type or "application/octet-stream",
        known_paths=context.machine.ontology.known_paths,
        backend_name=backend,
        sex=str(sex) if sex else None,
    )

    db.add(
        SessionDocument(
            session_id=context.row.id,
            document_id=result.document_id,
            filename=result.filename,
            media_type=file.content_type or "application/octet-stream",
            pages=len(result.pages),
            ocr_backend=result.backend,
            mean_confidence=result.mean_confidence,
            needs_verification=bool(result.needs_verification),
            pages_json=result.pages,
            entities_json=[e.to_dict() for e in result.entities] + result.needs_verification,
        )
    )

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="document.upload",
        abha_ref=context.row.abha_ref,
        consent_ref=context.row.consent_ref,
        request_summary={"backend": result.backend, "pages": len(result.pages)},
        response_summary={
            "factsRecorded": len(result.facts),
            "needsVerification": len(result.needs_verification),
        },
    )
    await save_context(db, context)
    return result.to_dict()


@router.get("/timeline")
async def timeline(db: DbSession, session_ref: str, identity: CurrentIdentity) -> dict[str, Any]:
    """Chronological view across every uploaded document."""
    from sqlalchemy import select

    from app.contracts.history import TimelineEvent
    from app.modules.documents.entities import ExtractedEntity
    from app.modules.documents.timeline import build_timeline

    context = await load_context(db, session_ref, identity=identity)
    rows = (
        (
            await db.execute(
                select(SessionDocument).where(SessionDocument.session_id == context.row.id)
            )
        )
        .scalars()
        .all()
    )

    events: list[TimelineEvent] = []
    for row in rows:
        entities = []
        for payload in row.entities_json or []:
            from datetime import date

            from app.contracts.provenance import BoundingBox

            observed = payload.get("observedOn")
            entities.append(
                ExtractedEntity(
                    kind=payload["kind"],
                    text=payload["text"],
                    page=payload["page"],
                    bbox=BoundingBox(**payload["bbox"]),
                    confidence=payload["confidence"],
                    handwritten=payload["handwritten"],
                    source_text=payload["sourceText"],
                    detail=payload.get("detail", {}),
                    observed_on=date.fromisoformat(observed) if observed else None,
                    date_precision=payload.get("datePrecision", "unknown"),
                )
            )
        events.extend(build_timeline(entities, document_id=row.document_id))

    return {
        "documents": [
            {
                "documentId": r.document_id,
                "filename": r.filename,
                "pages": r.pages,
                "backend": r.ocr_backend,
                "meanConfidence": round(r.mean_confidence, 4),
                "needsVerification": r.needs_verification,
                "verifiedBy": r.verified_by,
            }
            for r in rows
        ],
        "periods": group_by_period(events),
        "eventCount": len(events),
    }


@router.post("/{document_id}/verify", dependencies=[Depends(require_action("document.verify"))])
async def verify(
    db: DbSession,
    session_ref: str,
    document_id: str,
    identity: CurrentIdentity,
    payload: Annotated[dict, Body()],
) -> dict[str, Any]:
    """A human accepts or rejects a low-confidence entity. The only way into the record."""
    from sqlalchemy import select

    context = await load_context(db, session_ref, identity=identity)
    row = (
        (
            await db.execute(
                select(SessionDocument).where(
                    SessionDocument.session_id == context.row.id,
                    SessionDocument.document_id == document_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise ValidationError(f"No document {document_id} in this session.")

    entity_index = payload.get("entityIndex")
    if entity_index is None:
        raise ValidationError("entityIndex is required.")

    pending = [e for e in (row.entities_json or []) if e.get("entityIndex") == entity_index]
    if not pending:
        raise ValidationError(f"No pending entity at index {entity_index}.")

    result = IngestResult(
        document_id=document_id,
        filename=row.filename,
        backend=row.ocr_backend,
        pages=row.pages_json or [],
        mean_confidence=row.mean_confidence,
        needs_verification=[e for e in (row.entities_json or []) if "entityIndex" in e],
    )
    facts = verify_entity(
        context.ledger,
        result,
        entity_index=int(entity_index),
        accepted=bool(payload.get("accepted", False)),
        verified_by=identity.actor,
        known_paths=context.machine.ontology.known_paths,
        corrected_text=payload.get("correctedText"),
    )
    row.verified_by = identity.actor
    row.needs_verification = any(
        e.get("entityIndex") != entity_index
        for e in (row.entities_json or [])
        if "entityIndex" in e
    )

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="document.verify",
        abha_ref=context.row.abha_ref,
        request_summary={"documentId": document_id, "accepted": payload.get("accepted")},
        response_summary={"factsRecorded": len(facts)},
    )
    await save_context(db, context)
    return {
        "documentId": document_id,
        "entityIndex": entity_index,
        "accepted": bool(payload.get("accepted", False)),
        "factsRecorded": [f.fact_id for f in facts],
        "verifiedBy": identity.actor,
    }


@router.get("")
async def list_documents(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """Every document in this session with everything OCR read off it.

    Both surfaces need this and neither had it. The patient reads back what was found on
    their prescription; the physician's verification lane gets the pending entities it was
    built for and had no route to fetch — `PhysicianApp` was setting them to `[]`.
    """
    from sqlalchemy import select

    context = await load_context(db, session_ref, identity=identity)
    rows = (
        (
            await db.execute(
                select(SessionDocument)
                .where(SessionDocument.session_id == context.row.id)
                .order_by(SessionDocument.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "sessionRef": session_ref,
        "documents": [
            {
                "documentId": row.document_id,
                "filename": row.filename,
                "mediaType": row.media_type,
                "pages": row.pages,
                "backend": row.ocr_backend,
                "meanConfidence": row.mean_confidence,
                "needsVerification": row.needs_verification,
                "verifiedBy": row.verified_by,
                "kind": classify_document(list(row.entities_json or [])),
                "extracted": _addressed(list(row.entities_json or [])),
            }
            for row in rows
        ],
    }


@router.post(
    "/{document_id}/review",
    dependencies=[Depends(require_action("document.verify_own"))],
)
async def review(
    db: DbSession,
    session_ref: str,
    document_id: str,
    identity: CurrentIdentity,
    payload: Annotated[dict, Body()],
) -> dict[str, Any]:
    """The patient reads back what was scanned off their own paper.

    Two lanes, and the difference is deliberate:

    * A **pending** item was never recorded, so the patient confirming it is what admits it —
      the same gate the physician lane uses, reached earlier by the person holding the paper.
    * A **recorded** item is document-tier: it is what the prescription *says*. A patient
      cannot delete that by disagreeing, and this route will not let them. Disagreement is
      recorded as a dispute against the item and travels to the physician, who resolves it.
      Deciding for them which source wins is precisely what §16 forbids.
    """
    from sqlalchemy import select

    context = await load_context(db, session_ref, identity=identity)
    row = (
        (
            await db.execute(
                select(SessionDocument).where(
                    SessionDocument.session_id == context.row.id,
                    SessionDocument.document_id == document_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise ValidationError(f"No document {document_id} in this session.")

    item_id = str(payload.get("itemId") or "")
    action = str(payload.get("action") or "")
    if action not in ("confirm", "correct", "dispute"):
        raise ValidationError("action must be one of: confirm, correct, dispute.")

    entities = list(row.entities_json or [])
    addressed = _addressed(entities)
    target = next((e for e in addressed if e["itemId"] == item_id), None)
    if target is None:
        raise ValidationError(f"No item {item_id!r} on document {document_id}.")

    corrected = payload.get("correctedText")
    if action == "correct" and not str(corrected or "").strip():
        raise ValidationError("A correction needs correctedText.")

    facts: list[Any] = []
    if target["pending"]:
        result = IngestResult(
            document_id=document_id,
            filename=row.filename,
            backend=row.ocr_backend,
            pages=row.pages_json or [],
            mean_confidence=row.mean_confidence,
            needs_verification=[e for e in entities if "entityIndex" in e],
        )
        facts = verify_entity(
            context.ledger,
            result,
            entity_index=int(target["entityIndex"]),
            accepted=action != "dispute",
            verified_by=identity.actor,
            known_paths=context.machine.ontology.known_paths,
            corrected_text=str(corrected) if action == "correct" else None,
        )

    # Stamp the outcome onto the stored entity either way, so the physician sees what the
    # patient said about each line rather than only the net effect on the ledger.
    position = int(item_id.split(":")[1])
    marker = _marker_for(entities, item_id, position)
    if marker is not None:
        marker["patientReview"] = action
        marker["patientReviewedAt"] = datetime.now(UTC).isoformat()
        if action == "correct":
            marker["patientReading"] = str(corrected)
        if action == "dispute" and not target["pending"]:
            marker["patientDisputed"] = True
    # A JSON column mutated in place is invisible to the unit of work: the entities were
    # being stamped and the UPDATE never emitted, so every review vanished on the next read.
    # Reassigning the list is not enough either — the dicts inside it are the same objects.
    row.entities_json = list(entities)
    flag_modified(row, "entities_json")
    row.needs_verification = any(
        e.get("entityIndex") is not None and "patientReview" not in e for e in entities
    )

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="document.patient_review",
        abha_ref=context.row.abha_ref,
        consent_ref=context.row.consent_ref,
        request_summary={"documentId": document_id, "itemId": item_id, "action": action},
        response_summary={"factsRecorded": len(facts)},
    )
    await save_context(db, context)
    return {
        "documentId": document_id,
        "itemId": item_id,
        "action": action,
        "factsRecorded": [f.fact_id for f in facts],
        "disputed": action == "dispute" and not target["pending"],
        "note": (
            "A document-tier fact is what the paper says; a patient disagreeing with it is "
            "recorded as a dispute for the physician, not as a deletion."
            if action == "dispute" and not target["pending"]
            else ""
        ),
    }


def _addressed(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give every stored entity the same `itemId` the upload response handed out."""
    items: list[dict[str, Any]] = []
    recorded = 0
    for entity in entities:
        if entity.get("entityIndex") is None:
            items.append(
                {
                    **entity,
                    "itemId": f"recorded:{recorded}",
                    "pending": False,
                    "confidenceBand": confidence_band(
                        float(entity.get("confidence") or 0.0),
                        bool(entity.get("handwritten")),
                    ),
                }
            )
            recorded += 1
        else:
            items.append(
                {
                    **entity,
                    "itemId": f"pending:{entity['entityIndex']}",
                    "pending": True,
                    "confidenceBand": "verify",
                }
            )
    return items


def _marker_for(
    entities: list[dict[str, Any]], item_id: str, position: int
) -> dict[str, Any] | None:
    """The stored dict behind an `itemId`, so a review outcome can be written onto it."""
    if item_id.startswith("pending:"):
        return next((e for e in entities if e.get("entityIndex") == position), None)
    seen = -1
    for entity in entities:
        if entity.get("entityIndex") is None:
            seen += 1
            if seen == position:
                return entity
    return None

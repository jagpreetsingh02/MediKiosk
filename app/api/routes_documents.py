"""Document upload, the verification lane, and the timeline."""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Form, UploadFile

from app.api.deps import CurrentIdentity, DbSession, load_context, save_context
from app.audit.chain import record
from app.core.errors import ConsentRequired, ValidationError
from app.db.models import SessionDocument
from app.modules.documents.backends import available_backends
from app.modules.documents.pipeline import IngestResult, ingest, verify_entity
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
    context = await load_context(db, session_ref)
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
            entities_json=[e.to_dict() for e in result.entities]
            + result.needs_verification,
        )
    )

    await record(
        db, actor=identity.actor, actor_role=identity.role, purpose_of_use="TREATMENT",
        action="document.upload", abha_ref=context.row.abha_ref,
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
async def timeline(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """Chronological view across every uploaded document."""
    from sqlalchemy import select

    from app.contracts.history import TimelineEvent
    from app.modules.documents.entities import ExtractedEntity
    from app.modules.documents.timeline import build_timeline

    context = await load_context(db, session_ref)
    rows = (
        await db.execute(
            select(SessionDocument).where(SessionDocument.session_id == context.row.id)
        )
    ).scalars().all()

    events: list[TimelineEvent] = []
    for row in rows:
        entities = []
        for payload in row.entities_json or []:
            from datetime import date

            from app.contracts.provenance import BoundingBox

            observed = payload.get("observedOn")
            entities.append(
                ExtractedEntity(
                    kind=payload["kind"], text=payload["text"], page=payload["page"],
                    bbox=BoundingBox(**payload["bbox"]), confidence=payload["confidence"],
                    handwritten=payload["handwritten"], source_text=payload["sourceText"],
                    detail=payload.get("detail", {}),
                    observed_on=date.fromisoformat(observed) if observed else None,
                    date_precision=payload.get("datePrecision", "unknown"),
                )
            )
        events.extend(build_timeline(entities, document_id=row.document_id))

    return {
        "documents": [
            {
                "documentId": r.document_id, "filename": r.filename, "pages": r.pages,
                "backend": r.ocr_backend, "meanConfidence": round(r.mean_confidence, 4),
                "needsVerification": r.needs_verification, "verifiedBy": r.verified_by,
            }
            for r in rows
        ],
        "periods": group_by_period(events),
        "eventCount": len(events),
    }


@router.post("/{document_id}/verify")
async def verify(
    db: DbSession,
    session_ref: str,
    document_id: str,
    identity: CurrentIdentity,
    payload: Annotated[dict, Body()],
) -> dict[str, Any]:
    """A human accepts or rejects a low-confidence entity. The only way into the record."""
    from sqlalchemy import select

    context = await load_context(db, session_ref)
    row = (
        await db.execute(
            select(SessionDocument).where(
                SessionDocument.session_id == context.row.id,
                SessionDocument.document_id == document_id,
            )
        )
    ).scalars().first()
    if row is None:
        raise ValidationError(f"No document {document_id} in this session.")

    entity_index = payload.get("entityIndex")
    if entity_index is None:
        raise ValidationError("entityIndex is required.")

    pending = [
        e for e in (row.entities_json or []) if e.get("entityIndex") == entity_index
    ]
    if not pending:
        raise ValidationError(f"No pending entity at index {entity_index}.")

    result = IngestResult(
        document_id=document_id, filename=row.filename, backend=row.ocr_backend,
        pages=row.pages_json or [], mean_confidence=row.mean_confidence,
        needs_verification=[e for e in (row.entities_json or []) if "entityIndex" in e],
    )
    facts = verify_entity(
        context.ledger, result, entity_index=int(entity_index),
        accepted=bool(payload.get("accepted", False)), verified_by=identity.actor,
        known_paths=context.machine.ontology.known_paths,
        corrected_text=payload.get("correctedText"),
    )
    row.verified_by = identity.actor
    row.needs_verification = any(
        e.get("entityIndex") != entity_index for e in (row.entities_json or [])
        if "entityIndex" in e
    )

    await record(
        db, actor=identity.actor, actor_role=identity.role, purpose_of_use="TREATMENT",
        action="document.verify", abha_ref=context.row.abha_ref,
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

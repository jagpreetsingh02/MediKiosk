"""The physician surface: summary, click-to-source, edit, and the commit (Invariant 4)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select

from app.api.deps import (
    CurrentIdentity,
    DbSession,
    load_context,
    require_action,
    save_context,
)
from app.audit.chain import record, record_ai_call
from app.contracts.history import Demographics, api_dump
from app.contracts.projection import project
from app.core.errors import PolicyDenied, ValidationError
from app.db.models import ConsentRecord, IntakeSession, SubmittedBundle
from app.fhir.bundle import build_bundle, bundle_json
from app.modules.consent.his_push import push
from app.modules.consent.session import purge
from app.modules.encounter import history as H
from app.modules.summary.generate import generate
from app.redflags.engine import evaluate
from app.terminology.sidecar import code_reported_term

router = APIRouter(prefix="/api/v1", tags=["physician"])


async def _history_for(db, context):
    """Project the history and attach codings from the sidecar. Unmapped is a valid result."""
    demographics = Demographics(
        abha_ref=context.row.abha_ref,
        language=context.row.language,
        age_years=context.state.values.get("demographics.age_years"),
        gender=context.state.values.get("demographics.gender"),
        display_name=context.state.values.get("demographics.display_name"),
    )
    history = project(
        context.ledger,
        demographics=demographics,
        ayush=context.row.ayush_mode,
        language=context.row.language,
    )
    for problem in history.problems:
        if problem.reported_term.recorded:
            result = await code_reported_term(db, str(problem.reported_term.value))
            problem.coding = result.coding
            problem.unmapped = result.unmapped

    escalation = evaluate(
        context.ledger,
        current_priority=context.row.priority,
        extra_values=context.state.values,
    )
    history.red_flags = escalation.flags

    from sqlalchemy import select as _select

    from app.db.models import SessionDocument

    rows = (
        (
            await db.execute(
                _select(SessionDocument).where(SessionDocument.session_id == context.row.id)
            )
        )
        .scalars()
        .all()
    )
    from app.contracts.history import DocumentRef

    history.documents = [
        DocumentRef(
            document_id=r.document_id,
            filename=r.filename,
            pages=r.pages,
            ocr_backend=r.ocr_backend,
            mean_confidence=r.mean_confidence,
            low_confidence_pages=[1] if r.needs_verification else [],
            uploaded_at=r.uploaded_at,
        )
        for r in rows
    ]
    return history, escalation


@router.get("/queue", dependencies=[Depends(require_action("queue.read"))])
async def queue(db: DbSession, identity: CurrentIdentity) -> dict[str, Any]:
    """Triage queue, highest priority first. Visible to nurses; the narrative is not."""
    rows = (
        (await db.execute(select(IntakeSession).where(IntakeSession.purged_at.is_(None))))
        .scalars()
        .all()
    )
    order = {"immediate": 0, "urgent": 1, "routine": 2}
    entries = sorted(
        (
            {
                "sessionRef": r.session_ref,
                "priority": r.priority,
                "status": r.status,
                "language": r.language,
                "ayushMode": r.ayush_mode,
                "createdAt": r.created_at.isoformat(),
                "waitingMinutes": int(
                    (
                        datetime.now(UTC) - r.created_at.replace(tzinfo=r.created_at.tzinfo or UTC)
                    ).total_seconds()
                    // 60
                ),
            }
            for r in rows
        ),
        key=lambda e: (order.get(str(e["priority"]), 3), str(e["createdAt"])),
    )
    return {"queue": entries, "count": len(entries)}


@router.get(
    "/sessions/{session_ref}/summary",
    dependencies=[Depends(require_action("summary.read"))],
)
async def summary(
    db: DbSession, session_ref: str, identity: CurrentIdentity, prose: bool = False
) -> dict[str, Any]:
    """Generate the draft. Fails outright rather than returning a half-verified summary."""
    context = await load_context(db, session_ref, identity=identity)
    history, escalation = await _history_for(db, context)

    result = generate(history, context.ledger, escalation=escalation, use_prose=prose)

    for outcome in result.smoothing:
        if outcome.response is not None:
            await record_ai_call(
                db,
                actor=identity.actor,
                actor_role=identity.role,
                action="llm.smooth",
                model_name=outcome.response.model_name,
                model_version=outcome.response.model_version,
                prompt=outcome.response.prompt,
                abha_ref=context.row.abha_ref,
                response_summary={"applied": outcome.applied, "section": outcome.section_id},
            )

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="summary.generate",
        abha_ref=context.row.abha_ref,
        consent_ref=context.row.consent_ref,
        response_summary={
            "factLines": result.traceability.fact_lines,
            "traceable": result.traceability.ok,
            "priority": escalation.priority.label,
        },
    )
    await save_context(db, context)
    return {
        **result.to_dict(),
        "escalation": escalation.to_dict(),
        "history": api_dump(history),
    }


@router.get(
    "/sessions/{session_ref}/contradictions",
    dependencies=[Depends(require_action("fact.read"))],
)
async def contradictions(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """Every disagreement between two sources. Both sides, never a resolution."""
    from app.contracts.contradictions import detect

    context = await load_context(db, session_ref, identity=identity)
    found = detect(context.ledger)
    return {
        "sessionRef": session_ref,
        "count": len(found),
        "contradictions": [c.model_dump(mode="json", by_alias=True) for c in found],
        "note": (
            "Neither source has been discarded and neither has been preferred. Resolving a "
            "clinical conflict is a clinical judgement."
        ),
    }


@router.get(
    "/sessions/{session_ref}/facts/{fact_id}",
    dependencies=[Depends(require_action("fact.read"))],
)
async def fact_detail(
    db: DbSession, session_ref: str, fact_id: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """Click-to-source: everything behind one line of the summary."""
    context = await load_context(db, session_ref, identity=identity)
    fact = context.ledger.by_id(fact_id)
    if fact is None:
        raise ValidationError(f"No fact {fact_id} in this session.")
    span = fact.source
    return {
        "factId": fact.fact_id,
        "path": fact.path,
        "value": fact.value,
        "tier": fact.tier.value,
        "confidence": fact.confidence,
        "recordedAt": fact.recorded_at.isoformat(),
        "supersededBy": fact.superseded_by,
        "provenanceNote": fact.provenance_note,
        "source": span.model_dump(mode="json"),
        "explanation": _explain(fact),
    }


def _explain(fact) -> str:
    span = fact.source
    if fact.tier.value == "document":
        return (
            f"Read from {span.document_id}, page {span.page}, at "
            f"{span.ocr_confidence:.0%} OCR confidence"
            + (" — handwritten, human-verified." if span.handwritten else ".")
        )
    modality = getattr(getattr(span, "modality", None), "value", "unknown")
    if fact.tier.value == "confirmed":
        return f"The patient selected this in answer to {span.question_id} ({modality})."
    asr = getattr(span, "asr_confidence", None)
    suffix = f", ASR confidence {asr:.0%}" if asr is not None else ""
    return f"The patient said this, in answer to {span.question_id} ({modality}{suffix})."


@router.post(
    "/sessions/{session_ref}/summary/edit",
    dependencies=[Depends(require_action("summary.edit"))],
)
async def edit_fact(
    db: DbSession,
    session_ref: str,
    identity: CurrentIdentity,
    payload: Annotated[dict, Body()],
) -> dict[str, Any]:
    """A physician corrects a value. Recorded as a NEW fact citing the physician, never an
    overwrite: the patient's original answer and the correction both stay visible."""
    from app.contracts.provenance import Modality, SourceTier
    from app.contracts.record import record_fact, utterance_span

    context = await load_context(db, session_ref, identity=identity)
    path = str(payload.get("path") or "")
    value = payload.get("value")
    reason = str(payload.get("reason") or "physician correction")
    if not path or value is None:
        raise ValidationError("path and value are both required.")

    span = utterance_span(
        verbatim=f"{value} — corrected by {identity.actor}: {reason}",
        turn_id=f"edit_{datetime.now(UTC).timestamp():.0f}",
        question_id=path,
        modality=Modality.TYPED,
        language=context.row.language,
    )
    question = context.machine.ontology.by_path.get(path)
    fact = record_fact(
        context.ledger,
        path=path,
        value=value,
        tier=SourceTier.CONFIRMED,
        source=span,
        confidence=1.0,
        provenance_note=f"physician-edit:{identity.actor}",
        known_paths=context.machine.ontology.known_paths,
        coded_value_of=question.valid_values() if question and question.options else None,
    )
    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="summary.edit",
        abha_ref=context.row.abha_ref,
        request_summary={"path": path},
    )
    await save_context(db, context)
    return {"factId": fact.fact_id, "path": path, "supersededPrior": True}


@router.get(
    "/sessions/{session_ref}/fhir/preview",
    dependencies=[Depends(require_action("summary.read"))],
)
async def fhir_preview(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """Build the bundle WITHOUT committing, so it can be inspected before it is sent.

    Invariant 4 is untouched: this route builds and returns the document, and sends it
    nowhere. Nothing reaches the HIS or the ABHA record until `POST /commit`, which is the
    only route that transmits and the only one restricted to `summary.commit`.
    """
    context = await load_context(db, session_ref, identity=identity)
    history, escalation = await _history_for(db, context)
    result = generate(history, context.ledger, escalation=escalation)

    summary_text = "\n".join(
        f"{section.title}\n" + "\n".join(f"  - {line.text}" for line in section.lines)
        for section in result.summary.sections
    )
    bundle = build_bundle(
        history,
        context.ledger,
        summary_text=summary_text,
        consent_ref=context.row.consent_ref or "unknown",
        committed_by=f"PREVIEW — not committed (requested by {identity.actor})",
        abha_ref=context.row.abha_ref,
    )
    payload = bundle_json(bundle)
    counts: dict[str, int] = {}
    for entry in payload.get("entry", []):
        kind = entry.get("resource", {}).get("resourceType", "?")
        counts[kind] = counts.get(kind, 0) + 1

    return {
        "committed": False,
        "notice": (
            "Preview only. This bundle has not been transmitted and is not in any record. "
            "A physician must confirm before anything is sent."
        ),
        "fhirVersion": payload.get("_fhirVersion"),
        "resourceCounts": counts,
        "entries": len(payload.get("entry", [])),
        "bundle": payload,
    }


@router.post(
    "/sessions/{session_ref}/commit",
    dependencies=[Depends(require_action("summary.commit"))],
)
async def commit(
    db: DbSession,
    session_ref: str,
    identity: CurrentIdentity,
    payload: Annotated[dict | None, Body()] = None,
) -> dict[str, Any]:
    """⛔ INVARIANT 4. The only route that lets anything leave the building.

    ABAC restricts `summary.commit` to the clinician role, and `confirmed: true` must be
    explicit in the body. A patient token cannot reach this code path at all.
    """
    if not (payload or {}).get("confirmed"):
        raise PolicyDenied(
            "Commit requires an explicit `confirmed: true`. The summary is a draft until a "
            "physician confirms it."
        )

    context = await load_context(db, session_ref, identity=identity)
    history, escalation = await _history_for(db, context)
    result = generate(history, context.ledger, escalation=escalation)

    stored_consent = (
        (await db.execute(select(ConsentRecord).where(ConsentRecord.session_ref == session_ref)))
        .scalars()
        .first()
    )
    allows_share = bool(stored_consent and "abdm_share" in (stored_consent.scopes_granted or []))

    summary_text = "\n".join(
        f"{section.title}\n" + "\n".join(f"  - {line.text}" for line in section.lines)
        for section in result.summary.sections
    )
    bundle = build_bundle(
        history,
        context.ledger,
        summary_text=summary_text,
        consent_ref=context.row.consent_ref or "unknown",
        committed_by=identity.actor,
        abha_ref=context.row.abha_ref,
    )
    payload_json = bundle_json(bundle)

    pushed = await push(
        payload_json,
        committed_by=identity.actor,
        physician_confirmed=True,
        consent_allows_share=allows_share,
    )

    stored = SubmittedBundle(
        bundle_id=payload_json.get("identifier", {}).get("value", session_ref),
        session_ref=session_ref,
        abha_ref=context.row.abha_ref,
        consent_ref=context.row.consent_ref or "unknown",
        committed_by=identity.actor,
        bundle_json=payload_json,
        his_status=pushed.status,
        his_detail=pushed.detail[:500],
    )
    db.add(stored)

    context.row.status = "submitted"
    context.row.submitted_at = datetime.now(UTC)

    # ---- promote into the durable record BEFORE anything is purged ----------
    # Ordering is the whole point: a purge that ran first would destroy the visit on any
    # later failure, and a half-promoted encounter is worse than a lost one because it looks
    # complete. promote() writes; this function commits; only then does the purge run.
    from app.contracts.contradictions import detect as detect_contradictions
    from app.modules.encounter.promote import promote

    promotion = await promote(
        db,
        session_row=context.row,
        ledger=context.ledger,
        history=history,
        escalation=escalation,
        contradictions=detect_contradictions(context.ledger),
        summary_payload=result.to_dict(),
        traceable=result.traceability.ok,
        confirmed_by=identity.actor,
    )

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="summary.commit",
        abha_ref=context.row.abha_ref,
        consent_ref=context.row.consent_ref,
        response_summary={
            "hisStatus": pushed.status,
            "shared": allows_share,
            "entries": len(payload_json.get("entry", [])),
        },
    )
    # Commit the promotion and everything above it. If this raises, the capture session is
    # still intact and the visit is recoverable.
    await db.commit()

    # Only now is the capture session expendable (Invariant 6).
    from app.core.config import settings

    purged = None
    if settings.purge_on_submit:
        purged = (await purge(db, session_ref, reason="submit")).to_dict()

    return {
        "committed": True,
        "committedBy": identity.actor,
        "bundleId": stored.bundle_id,
        "fhirVersion": payload_json.get("_fhirVersion"),
        "entries": len(payload_json.get("entry", [])),
        "hisPush": pushed.to_dict(),
        "consentAllowedShare": allows_share,
        "promotion": promotion.to_dict(),
        "purge": purged,
    }


@router.get("/sessions/{session_ref}/bundle")
async def committed_bundle(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """The committed FHIR document. Survives the purge because a physician confirmed it."""
    row = (
        (
            await db.execute(
                select(SubmittedBundle).where(SubmittedBundle.session_ref == session_ref)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise ValidationError(f"No committed bundle for {session_ref}.")
    return {
        "bundleId": row.bundle_id,
        "committedBy": row.committed_by,
        "committedAt": row.committed_at.isoformat(),
        "hisStatus": row.his_status,
        "bundle": row.bundle_json,
    }


@router.get(
    "/sessions/{session_ref}/patient-context",
    dependencies=[Depends(require_action("session.read"))],
)
async def patient_context(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """The bridge from the visit on screen to the person it belongs to.

    Nothing joined these two halves before. The durable patient routes existed and the
    physician had no way to reach them from a session under review: the queue hands out a
    session reference, the history is keyed by patient, and the surface that needed both had
    neither. This resolves the session's ABHA reference to a patient and returns the four
    things a physician wants beside a draft — what else is on file, what medicines are known
    and how, which past visits look like this one, and where today's answers disagree with
    the record.

    Similarity is computed against the LIVE ledger, not a committed encounter, because the
    physician needs it while deciding — after commit it would be a historical curiosity.

    `known: false` is a normal answer, not an error. A first-time patient is the common case
    at a walk-in OPD, and a screen that errors on them is a screen that breaks on day one.
    """
    context = await load_context(db, session_ref, identity=identity)
    abha_ref = context.row.abha_ref
    patient = (
        await H.get_patient_by_abha(db, abha_ref=abha_ref) if abha_ref else None
    )
    if patient is None:
        return {
            "sessionRef": session_ref,
            "known": False,
            "note": "No previous record for this patient. This will be their first encounter.",
            "overview": None,
            "timeline": [],
            "medications": [],
            "similar": [],
            "reconciliation": [],
        }

    values = dict(context.state.values)
    features = await H.features_from_ledger(values)
    similar = await H.similar_encounters(
        db, patient_id=patient.id, current_features=features
    )

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="TREATMENT",
        action="patient.context_read",
        abha_ref=abha_ref,
        consent_ref=context.row.consent_ref,
        response_summary={"patientRef": patient.patient_ref, "similar": len(similar)},
    )
    return {
        "sessionRef": session_ref,
        "known": True,
        "patientRef": patient.patient_ref,
        "overview": await H.overview(db, patient),
        "timeline": await H.timeline(db, patient.id),
        "medications": await H.medication_history(db, patient.id, live_values=values),
        "similar": similar,
        "reconciliation": await H.reconcile_live_session(
            db, patient_id=patient.id, values=values
        ),
        # Labelled here rather than in the frontend: FEATURE_LABELS already exists and a
        # second mapping over there had drifted to paths the ontology does not define,
        # which rendered as a truncated `CHIEF_COMPLAINT.TE:` on the physician's screen.
        "currentFeatures": [
            {
                "path": path,
                "label": H.FEATURE_LABELS.get(path, path),
                "values": sorted(values),
            }
            for path, values in sorted(features.items())
        ],
        "note": (
            "History is read-only here. Nothing in this panel is part of today's draft until "
            "the physician commits it."
        ),
    }

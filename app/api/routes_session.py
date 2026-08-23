"""Session creation, consent, and teardown. The kiosk's first and last calls."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select

from app.api.deps import CurrentIdentity, DbSession, load_context, save_context
from app.audit.chain import record
from app.core.config import SUPPORTED_LANGUAGES, settings
from app.core.errors import ConsentRequired, ValidationError
from app.db.models import ConsentRecord, IntakeSession
from app.modules.consent import consent as consent_module
from app.modules.consent.session import purge, sweep_expired
from app.modules.dialogue.machine import DialogueState

router = APIRouter(prefix="/api/v1", tags=["session"])


@router.get("/languages")
async def languages() -> dict[str, Any]:
    return {
        "languages": [
            {"code": code, "name": name, "isDefault": code == "en"}
            for code, name in SUPPORTED_LANGUAGES.items()
        ],
        "note": (
            "Every question has an English and a Hindi prompt. Other languages fall back to "
            "English and the response marks translationMissing so the gap is visible in the "
            "UI rather than silently served."
        ),
    }


@router.get("/consent/presentation")
async def consent_presentation(language: str = "en") -> dict[str, Any]:
    """What the kiosk shows and reads aloud before a single question is asked."""
    return consent_module.presentation(language)


@router.post("/sessions", status_code=201)
async def create_session(
    db: DbSession,
    identity: CurrentIdentity,
    payload: Annotated[dict, Body()],
) -> dict[str, Any]:
    """Create a session and record consent. Nothing is captured before this succeeds."""
    language = str(payload.get("language", "en"))
    if language not in SUPPORTED_LANGUAGES:
        raise ValidationError(f"{language!r} is not a supported language.")

    granted = list(payload.get("consentScopes") or [])
    audio_explained = bool(payload.get("audioExplained", False))
    session_ref = f"sess_{uuid.uuid4().hex[:12]}"

    # Raises ConsentRequired if a required scope is missing. Nothing is created.
    consent = consent_module.grant(
        session_ref=session_ref,
        granted=granted,
        language=language,
        audio_explained=audio_explained,
    )

    ayush_mode = "ayush" in consent.granted
    row = IntakeSession(
        session_ref=session_ref,
        abha_ref=identity.abha_ref,
        consent_ref=consent.consent_ref,
        language=language,
        ayush_mode=ayush_mode,
        status="in_progress",
        priority="routine",
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        state_json=DialogueState(
            session_id=session_ref, language=language, ayush_mode=ayush_mode
        ).to_json(),
    )
    db.add(row)

    db.add(
        ConsentRecord(
            consent_ref=consent.consent_ref,
            abha_ref=identity.abha_ref,
            session_ref=session_ref,
            language=language,
            scopes_granted=sorted(consent.granted),
            scopes_refused=sorted(consent.refused),
            audio_explained=audio_explained,
            policy_version=consent.policy_version,
            expires_at=consent.expires_at,
        )
    )
    await db.flush()

    await record(
        db, actor=identity.actor, actor_role=identity.role, purpose_of_use="TREATMENT",
        action="session.create", abha_ref=identity.abha_ref,
        consent_ref=consent.consent_ref,
        request_summary={"language": language, "scopes": sorted(consent.granted)},
    )

    context = await load_context(db, session_ref)
    context.ledger.consent_scopes = set(consent.granted)
    # Demographics come from the ABHA token, never from the patient re-typing them.
    if identity.demographics:
        context.state.values.update(
            {
                f"demographics.{k}": v
                for k, v in identity.demographics.items()
                if v is not None
            }
        )
    await save_context(db, context)

    return {
        "sessionRef": session_ref,
        "consentRef": consent.consent_ref,
        "language": language,
        "ayushMode": ayush_mode,
        "expiresAt": row.expires_at.isoformat() if row.expires_at else None,
        "consent": consent.to_dict(),
        "abhaRef": identity.abha_ref,
        "demographics": identity.demographics,
    }


@router.get("/sessions/{session_ref}")
async def get_session_state(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    context = await load_context(db, session_ref)
    return {
        "sessionRef": context.ref,
        "status": context.row.status,
        "priority": context.row.priority,
        "language": context.row.language,
        "ayushMode": context.row.ayush_mode,
        "expiresAt": context.row.expires_at.isoformat() if context.row.expires_at else None,
        "progress": context.machine.progress(),
        "sections": context.machine.section_progress(),
        "factsRecorded": len(context.ledger.active_facts()),
        "consentScopes": sorted(context.ledger.consent_scopes),
    }


@router.post("/sessions/{session_ref}/consent/revoke")
async def revoke_consent(
    db: DbSession,
    session_ref: str,
    identity: CurrentIdentity,
    payload: Annotated[dict, Body()] = {},
) -> dict[str, Any]:
    """Withdraw consent, wholly or per-scope. Facts under a withdrawn scope are purged."""
    context = await load_context(db, session_ref)
    stored = (
        await db.execute(
            select(ConsentRecord).where(ConsentRecord.session_ref == session_ref)
        )
    ).scalars().first()
    if stored is None:
        raise ConsentRequired(f"No consent record exists for {session_ref}.")

    consent = consent_module.Consent(
        consent_ref=stored.consent_ref,
        session_ref=session_ref,
        granted=set(stored.scopes_granted or []),
        refused=set(stored.scopes_refused or []),
        language=stored.language,
        audio_explained=stored.audio_explained,
        policy_version=stored.policy_version,
        expires_at=stored.expires_at,
    )
    scopes = payload.get("scopes")
    result = consent_module.revoke(consent, context.ledger, scopes=scopes)

    stored.scopes_granted = sorted(consent.granted)
    stored.scopes_refused = sorted(consent.refused)
    stored.revoked_at = consent.revoked_at

    await record(
        db, actor=identity.actor, actor_role=identity.role, purpose_of_use="TREATMENT",
        action="consent.revoke", abha_ref=identity.abha_ref, consent_ref=stored.consent_ref,
        request_summary={"scopes": result["revokedScopes"]},
        response_summary={"factsPurged": result["factsPurged"]},
    )

    if result["sessionEnded"]:
        purged = await purge(db, session_ref, reason="consent_revoked")
        return {**result, "purge": purged.to_dict()}

    # Rewrite the persisted ledger to match what survived the revocation.
    from app.db.models import SessionFact
    from sqlalchemy import delete

    surviving = {f.fact_id for f in context.ledger.facts}
    for row in (
        await db.execute(select(SessionFact).where(SessionFact.session_id == context.row.id))
    ).scalars().all():
        if row.fact_id not in surviving:
            await db.execute(delete(SessionFact).where(SessionFact.id == row.id))
    await save_context(db, context)
    return result


@router.post("/sessions/{session_ref}/purge")
async def purge_session(
    db: DbSession, session_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    result = await purge(db, session_ref, reason="explicit")
    await record(
        db, actor=identity.actor, actor_role=identity.role, purpose_of_use="TREATMENT",
        action="session.purge", response_summary={"factsDeleted": result.facts_deleted},
    )
    return result.to_dict()


@router.post("/admin/sweep")
async def sweep(db: DbSession, identity: CurrentIdentity) -> dict[str, Any]:
    """Purge every session past its TTL. Called on a timer and available manually."""
    results = await sweep_expired(db)
    return {"purged": len(results), "sessions": [r.to_dict() for r in results]}

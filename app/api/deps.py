"""FastAPI dependencies: identity, policy, session loading and the ledger round-trip.

The session state lives in three places and this module is what keeps them in step: the
`intake_session` row (durable-ish, purgeable), the `session_fact` rows (the persisted ledger)
and the cache (the dialogue state). `load_context()` reads all three; `save_context()` writes
them back in one place so no route can persist half a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.identity import Identity, identity_from_header
from app.auth.policy import Decision, Purpose, evaluate, parse_purpose
from app.contracts.provenance import DocumentSpan, Fact, SourceTier, UtteranceSpan
from app.contracts.record import FactLedger
from app.core.errors import SessionExpired
from app.db.models import IntakeSession, SessionFact
from app.db.session import get_session
from app.modules.consent.session import assert_live, get_store
from app.modules.dialogue.machine import DialogueMachine, DialogueState

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def current_identity(
    authorization: Annotated[str | None, Header()] = None,
) -> Identity:
    return identity_from_header(authorization)


CurrentIdentity = Annotated[Identity, Depends(current_identity)]


async def current_purpose(
    purpose: str | None = None,
    x_purpose_of_use: Annotated[str | None, Header()] = None,
) -> Purpose:
    """Purpose-of-use is required on every request. Ported behaviour from SIH 25026."""
    return parse_purpose(purpose or x_purpose_of_use or "TREATMENT")


CurrentPurpose = Annotated[Purpose, Depends(current_purpose)]


def require_action(action: str):
    """Dependency factory: enforce one ABAC action for a route."""

    async def _check(identity: CurrentIdentity, purpose: CurrentPurpose) -> Decision:
        return evaluate(role=identity.role, purpose=purpose, action=action).require()

    return _check


@dataclass(slots=True)
class SessionContext:
    row: IntakeSession
    ledger: FactLedger
    machine: DialogueMachine
    state: DialogueState

    @property
    def ref(self) -> str:
        return self.row.session_ref


def _fact_from_row(row: SessionFact) -> Fact:
    payload: dict[str, Any] = dict(row.source_json or {})
    span = (
        DocumentSpan.model_validate(payload)
        if payload.get("kind") == "document"
        else UtteranceSpan.model_validate(payload)
    )
    # Rehydrating a Fact bypasses record_fact by necessity — the fact was already validated
    # when it was first written, and re-validating a stored row is not the same operation.
    # This is the ONLY place that reconstructs one, and tests/test_invariant_provenance.py
    # allows it by path.
    return Fact.model_construct(
        fact_id=row.fact_id,
        session_id=str(row.session_id),
        path=row.path,
        value=(row.value_json or {}).get("v"),
        # model_construct skips coercion, so the enum has to be built explicitly. Leaving
        # this a bare string made `fact.tier.value` blow up in the consent purge path.
        tier=SourceTier(row.tier),
        source=span,
        confidence=row.confidence,
        recorded_at=row.recorded_at,
        superseded_by=row.superseded_by,
    )


async def load_context(db: AsyncSession, session_ref: str) -> SessionContext:
    """Load a live session: the row, its persisted facts, and its cached dialogue state."""
    row = await assert_live(db, session_ref)

    ledger = FactLedger(session_ref)
    rows = (
        (await db.execute(select(SessionFact).where(SessionFact.session_id == row.id)))
        .scalars()
        .all()
    )
    for fact_row in rows:
        fact = _fact_from_row(fact_row)
        ledger._facts.append(fact)
        from app.contracts.provenance import span_digest

        ledger._digests.add(f"{fact.path}|{span_digest(fact.source)}")

    store = await get_store()
    cached = await store.get(session_ref)
    state = (
        DialogueState.from_json(cached["dialogue"])
        if cached and "dialogue" in cached
        else DialogueState(
            session_id=session_ref,
            language=row.language,
            ayush_mode=row.ayush_mode,
        )
    )
    if cached and "absences" in cached:
        from app.contracts.provenance import Absence

        ledger._absences = [Absence.model_validate(a) for a in cached["absences"]]
    if cached and "consent_scopes" in cached:
        ledger.consent_scopes = set(cached["consent_scopes"])

    return SessionContext(
        row=row, ledger=ledger, machine=DialogueMachine(state, ledger), state=state
    )


async def save_context(db: AsyncSession, context: SessionContext) -> None:
    """Persist the ledger and cache the dialogue state. The only writer of session state."""
    existing = {
        row.fact_id
        for row in (
            await db.execute(select(SessionFact).where(SessionFact.session_id == context.row.id))
        )
        .scalars()
        .all()
    }
    for fact in context.ledger.facts:
        if fact.fact_id in existing:
            continue
        db.add(
            SessionFact(
                session_id=context.row.id,
                fact_id=fact.fact_id,
                path=fact.path,
                value_json={"v": fact.value},
                tier=fact.tier.value,
                confidence=fact.confidence,
                source_json=fact.source.model_dump(mode="json"),
                superseded_by=fact.superseded_by,
                recorded_at=fact.recorded_at,
            )
        )
    # Supersession happens in memory; mirror it onto the rows so a reload sees it.
    superseded = {f.fact_id: f.superseded_by for f in context.ledger.facts if f.superseded_by}
    if superseded:
        for row in (
            (await db.execute(select(SessionFact).where(SessionFact.session_id == context.row.id)))
            .scalars()
            .all()
        ):
            if row.fact_id in superseded:
                row.superseded_by = superseded[row.fact_id]

    context.row.state_json = context.state.to_json()

    store = await get_store()
    from app.core.config import settings

    await store.put(
        context.ref,
        {
            "dialogue": context.state.to_json(),
            "absences": [a.model_dump(mode="json") for a in context.ledger.absences],
            "consent_scopes": sorted(context.ledger.consent_scopes),
        },
        ttl=settings.session_ttl_seconds,
    )
    await db.flush()


async def session_or_410(db: AsyncSession, session_ref: str) -> SessionContext:
    try:
        return await load_context(db, session_ref)
    except SessionExpired:
        raise

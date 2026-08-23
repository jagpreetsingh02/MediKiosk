"""Invariant 6 (audit half) — the hash chain, ported from SIH 25026 and extended for AI calls."""

from __future__ import annotations

from sqlalchemy import select

from app.audit.chain import (
    count_events,
    prompt_fingerprint,
    record,
    record_ai_call,
    scrub,
    verify_chain,
)
from app.db.models import AuditEvent


async def test_chain_verifies_after_appends(db_session) -> None:
    for i in range(5):
        await record(
            db_session,
            actor="kiosk",
            actor_role="patient",
            purpose_of_use="TREATMENT",
            action=f"dialogue.answer.{i}",
        )
    await db_session.commit()
    result = await verify_chain(db_session)
    assert result.intact and result.checked == 5
    assert await count_events(db_session) == 5


async def test_tampering_with_a_row_breaks_the_chain(db_session) -> None:
    for i in range(4):
        await record(
            db_session,
            actor="kiosk",
            actor_role="patient",
            purpose_of_use="TREATMENT",
            action=f"action.{i}",
        )
    await db_session.commit()

    victim = (await db_session.execute(select(AuditEvent).where(AuditEvent.id == 2))).scalar_one()
    victim.action = "action.tampered"
    await db_session.commit()

    result = await verify_chain(db_session)
    assert not result.intact
    assert result.first_broken_index == 1
    assert "modified after it was written" in (result.detail or "")


async def test_deleting_a_row_breaks_the_chain(db_session) -> None:
    for i in range(4):
        await record(
            db_session,
            actor="kiosk",
            actor_role="patient",
            purpose_of_use="TREATMENT",
            action=f"action.{i}",
        )
    await db_session.commit()
    victim = (await db_session.execute(select(AuditEvent).where(AuditEvent.id == 2))).scalar_one()
    await db_session.delete(victim)
    await db_session.commit()

    result = await verify_chain(db_session)
    assert not result.intact
    assert "inserted or removed" in (result.detail or "")


async def test_ai_call_is_recorded_with_model_and_prompt_hash(db_session) -> None:
    event = await record_ai_call(
        db_session,
        actor="kiosk",
        actor_role="patient",
        action="llm.extract",
        model_name="llama-3.3-70b-versatile",
        model_version="2025-04",
        prompt="Extract slots from: my chest hurts",
    )
    await db_session.commit()
    assert event.model_name == "llama-3.3-70b-versatile"
    assert event.prompt_hash == prompt_fingerprint("Extract slots from: my chest hurts")
    assert len(event.prompt_hash) == 64
    assert (await verify_chain(db_session)).intact


async def test_ai_fields_are_covered_by_the_hash(db_session) -> None:
    """Changing a model name after the fact must break the chain, or the log proves nothing."""
    await record_ai_call(
        db_session,
        actor="kiosk",
        actor_role="patient",
        action="llm.extract",
        model_name="llama-3.3-70b-versatile",
        model_version="v1",
        prompt="hello",
    )
    await db_session.commit()
    row = (await db_session.execute(select(AuditEvent))).scalars().first()
    assert row is not None
    row.model_name = "some-other-model"
    await db_session.commit()
    assert not (await verify_chain(db_session)).intact


async def test_patient_narrative_never_reaches_the_audit_log(db_session) -> None:
    """The scrubber is the last line of defence: clinical content must not be persisted here."""
    dirty = {
        "verbatim": "I have been having chest pain since Tuesday",
        "transcript": "long narration",
        "questionId": "hpi.site",
        "nested": {"summary": "patient reports chest pain"},
    }
    clean = scrub(dirty)
    assert clean is not None
    assert clean["verbatim"] == "<redacted>"
    assert clean["transcript"] == "<redacted>"
    assert clean["nested"]["summary"] == "<redacted>"
    assert clean["questionId"] == "hpi.site", "non-clinical metadata should survive"

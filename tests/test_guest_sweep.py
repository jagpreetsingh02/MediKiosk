"""The guest sweep removes everything, and can never reach a clinical record.

TWO FAILURES THIS GUARDS, and they fail in opposite directions.

TOO LITTLE. `DELETE FROM patient` looks complete because most of the schema cascades. Three
capture-side tables do NOT — `consent_record`, `intake_session` and `submitted_bundle` are
keyed by `session_ref` with no foreign key to the patient. Deleting only the patient strands
them: rows pointing at a session whose encounter no longer exists, invisible to every join.
The storage leak the sweep exists to fix would simply move tables.

TOO MUCH. This is a CASCADING delete. Pointed at a clinical record it would take the patient,
their encounters, every fact, every piece of evidence and every document with it, and nothing
would bring them back. So the sweep requires two independent conditions and refuses anything
else — and the test below hands it a real patient wearing a guest's name to prove the refusal
is not merely a filter upstream.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.durable import (
    ClinicalFactRecord,
    DocumentRecord,
    Encounter,
    MedicationEvent,
    Patient,
    SourceEvidence,
    TimelineEventRecord,
)
from app.db.models import ConsentRecord, IntakeSession
from app.modules.encounter import sweep as S

#: Every table a swept guest must leave nothing in.
TRACKED = (
    (Encounter, "encounter"),
    (ClinicalFactRecord, "clinical_fact"),
    (SourceEvidence, "source_evidence"),
    (DocumentRecord, "document_record"),
    (MedicationEvent, "medication_event"),
    (TimelineEventRecord, "timeline_event"),
    (ConsentRecord, "consent_record"),
    (IntakeSession, "intake_session"),
)


async def _counts(db) -> dict[str, int]:
    out = {}
    for model, name in TRACKED:
        out[name] = int(
            (await db.execute(select(func.count()).select_from(model))).scalar() or 0
        )
    out["patient"] = int(
        (await db.execute(select(func.count()).select_from(Patient))).scalar() or 0
    )
    return out


async def _make_guest(db, *, ref: str, age_hours: float, with_session: bool = True) -> Patient:
    """A guest with the shape a real one has, including the capture-side rows."""
    created = datetime.now(UTC) - timedelta(hours=age_hours)
    session_ref = f"sess_{ref[-8:]}"

    patient = Patient(
        patient_ref=ref, abha_ref=None, display_name="Demo Patient (synthetic)",
        year_of_birth=1970, gender="male", is_synthetic=True, created_at=created,
    )
    db.add(patient)
    await db.flush()

    encounter = Encounter(
        encounter_ref=f"enc_{ref[-8:]}", patient_id=patient.id,
        source_session_ref=session_ref if with_session else None,
        occurred_at=created, kind="intake", headline="Stomach problem",
        confirmed_by="dr.t", confirmed_at=created,
    )
    db.add(encounter)
    await db.flush()

    fact = ClinicalFactRecord(
        encounter_id=encounter.id, fact_ref=f"fact_{ref[-8:]}", path="chief_complaint.text",
        value_json={"v": "stomach"}, display_value="Stomach problem", tier="confirmed",
        state="confirmed", confidence=1.0, recorded_at=created, valid_from=created,
    )
    db.add(fact)
    await db.flush()
    db.add(SourceEvidence(fact_id=fact.id, source_type="utterance",
                          verbatim="my stomach hurts", language="en", modality="touch"))
    db.add(DocumentRecord(
        encounter_id=encounter.id, document_ref=f"doc_{ref[-8:]}", filename="rx.pdf",
        media_type="application/pdf", document_kind="prescription", pages=1,
        ocr_backend="textlayer", mean_confidence=0.99, uploaded_at=created))
    db.add(MedicationEvent(
        patient_id=patient.id, encounter_id=encounter.id, name="METFORMIN",
        normalized_name="metformin", dose="500MG", status="documented", observed_on=created.date()))
    db.add(TimelineEventRecord(
        patient_id=patient.id, encounter_id=encounter.id, event_ref=f"evt_{ref[-8:]}",
        occurred_on=created.date(), date_precision="exact", kind="encounter", label="Visit"))

    if with_session:
        # The capture-side rows that have NO foreign key to the patient.
        db.add(IntakeSession(session_ref=session_ref, language="en", state_json={}))
        db.add(ConsentRecord(
            consent_ref=f"consent_{ref[-8:]}", session_ref=session_ref, language="en",
            scopes_granted=["history", "documents"], scopes_refused=[],
            audio_explained=True, policy_version="1.0.0"))
    await db.flush()
    return patient


async def test_a_swept_guest_leaves_zero_rows_anywhere(db_session) -> None:
    """Before and after, table by table. The whole record goes or the sweep is not done."""
    baseline = await _counts(db_session)

    await _make_guest(db_session, ref="pat_guest_sweep01", age_hours=48)
    populated = await _counts(db_session)
    for table, before in baseline.items():
        assert populated[table] > before, f"{table} was not populated; the fixture proves nothing"

    result = await S.sweep(db_session)
    after = await _counts(db_session)

    assert result["count"] == 1
    assert result["swept"] == ["pat_guest_sweep01"]
    # The sweep proves its own cleanup rather than the test taking it on trust.
    assert result["rowsRemoved"].get("residue", 0) == 0
    for table, before in baseline.items():
        assert after[table] == before, (
            f"{table} still holds {after[table] - before} row(s) after the sweep — "
            f"a swept guest must leave nothing behind"
        )


async def test_the_capture_side_rows_go_too(db_session) -> None:
    """consent_record and intake_session have NO foreign key; cascade alone misses them."""
    await _make_guest(db_session, ref="pat_guest_sweep02", age_hours=48)
    assert (await _counts(db_session))["consent_record"] >= 1

    await S.sweep(db_session)

    assert (await _counts(db_session))["consent_record"] == 0
    assert (await _counts(db_session))["intake_session"] == 0
    assert await S.orphan_report(db_session) == {"consent_record": 0, "submitted_bundle": 0}


async def test_a_young_guest_is_left_alone(db_session) -> None:
    """The TTL is a TTL. A demo in progress must not vanish under the person using it."""
    await _make_guest(db_session, ref="pat_guest_young1", age_hours=1)
    result = await S.sweep(db_session)
    assert result["count"] == 0
    assert (
        await db_session.execute(
            select(Patient).where(Patient.patient_ref == "pat_guest_young1")
        )
    ).scalars().first() is not None


async def test_the_ttl_is_configurable(db_session) -> None:
    await _make_guest(db_session, ref="pat_guest_ttl001", age_hours=3)
    assert (await S.sweep(db_session, dry_run=True))["count"] == 0
    assert (await S.sweep(db_session, hours=2, dry_run=True))["count"] == 1


async def test_a_dry_run_deletes_nothing(db_session) -> None:
    """The only sane way to point a cascading delete at production the first time."""
    await _make_guest(db_session, ref="pat_guest_dryrun", age_hours=48)
    before = await _counts(db_session)
    result = await S.sweep(db_session, dry_run=True)
    assert result["dryRun"] is True
    assert result["wouldRemove"] == ["pat_guest_dryrun"]
    assert await _counts(db_session) == before


async def test_a_clinical_patient_is_never_swept(db_session) -> None:
    """The sweep may not reach a real record, however old it is."""
    old = datetime.now(UTC) - timedelta(days=400)
    db_session.add(Patient(
        patient_ref="pat_real_old", abha_ref="abha:real", display_name="Real",
        year_of_birth=1970, is_synthetic=False, created_at=old))
    await db_session.flush()

    result = await S.sweep(db_session)
    assert result["count"] == 0
    assert (
        await db_session.execute(select(Patient).where(Patient.patient_ref == "pat_real_old"))
    ).scalars().first() is not None


async def test_a_mislabelled_real_patient_still_cannot_be_swept(db_session) -> None:
    """⛔ THE ONE THAT MATTERS. Two independent conditions, not one.

    A real record carrying a guest-shaped ref must still be refused, because the cost of
    being wrong here is a cascading delete nothing can undo. `purge_guest` re-checks rather
    than trusting that the caller filtered correctly.
    """
    old = datetime.now(UTC) - timedelta(days=400)
    impostor = Patient(
        patient_ref="pat_guest_impostor", abha_ref="abha:impostor",
        display_name="Actually clinical", year_of_birth=1970,
        is_synthetic=False,  # the cohort marker says CLINICAL
        created_at=old,
    )
    db_session.add(impostor)
    await db_session.flush()

    # The selector never picks it up...
    assert (await S.sweep(db_session))["count"] == 0

    # ...and calling the deleter directly still refuses.
    with pytest.raises(ValueError, match="not a guest record"):
        await S.purge_guest(db_session, impostor)

    assert (
        await db_session.execute(
            select(Patient).where(Patient.patient_ref == "pat_guest_impostor")
        )
    ).scalars().first() is not None


async def test_audit_events_are_deliberately_retained(db_session) -> None:
    """The audit log is HASH-CHAINED. Deleting from the middle breaks verification.

    Invariant 6. Removing a demo session's entries would turn a tamper-evident log into one
    that reports tampering for every entry after them — and the rows hold action names and
    references, not clinical content.
    """
    from app.db.models import AuditEvent

    before = int(
        (await db_session.execute(select(func.count()).select_from(AuditEvent))).scalar() or 0
    )
    await _make_guest(db_session, ref="pat_guest_audit1", age_hours=48)
    await S.sweep(db_session)
    after = int(
        (await db_session.execute(select(func.count()).select_from(AuditEvent))).scalar() or 0
    )
    assert after >= before, "the sweep removed audit rows; the hash chain would no longer verify"


async def test_an_abandoned_intake_is_not_reported_as_an_orphan(db_session) -> None:
    """A session that never became an encounter is ordinary, not a leak.

    The first orphan_report counted exactly this and reported 48 on production — sending
    somebody hunting a problem that does not exist. `consent_record` is also documented as
    outliving its session deliberately, because proving consent was given is a legal
    requirement. Only a row that can no longer be tied to ANY patient is a real orphan.
    """
    db_session.add(IntakeSession(session_ref="sess_abandoned", language="en", state_json={}))
    db_session.add(ConsentRecord(
        consent_ref="consent_abandoned", session_ref="sess_abandoned", language="en",
        scopes_granted=["history"], scopes_refused=[], audio_explained=True,
        policy_version="1.0.0"))
    await db_session.flush()

    assert await S.orphan_report(db_session) == {"consent_record": 0, "submitted_bundle": 0}, (
        "an abandoned intake was reported as an orphan; it is a patient who did not finish"
    )

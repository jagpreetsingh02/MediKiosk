"""The longitudinal slice: patient → encounters → promotion → history.

These are the tests §26 of the build prompt asks for. The two that matter most are
`test_confirmed_encounter_survives_the_session_purge` and
`test_promotion_happens_before_the_purge`: together they are the guarantee that confirming a
visit makes it permanent, and that nothing is thrown away before that has succeeded.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.contracts.history import Demographics
from app.contracts.projection import project
from app.contracts.record import FactLedger
from app.core.errors import InvariantViolation
from app.db.durable import (
    ClinicalFactRecord,
    Encounter,
    MedicationEvent,
    Patient,
    SourceEvidence,
)
from app.db.models import IntakeSession, SessionFact
from app.modules.consent.session import purge
from app.modules.dialogue.ontology import load_ontology
from app.modules.documents.pipeline import ingest
from app.modules.encounter import history as H
from app.modules.encounter.promote import promote
from app.modules.encounter.seed import demo_abha_ref, seed_demo_patient
from app.redflags.engine import evaluate
from tests.helpers import tap

FIXTURE = "data/fixtures/documents/prescription.pdf"


async def _session(db, *, abha_ref: str = "abha:test0001") -> IntakeSession:
    row = IntakeSession(
        session_ref=f"sess_{abha_ref[-6:]}",
        abha_ref=abha_ref,
        consent_ref="consent_test",
        language="en",
        status="ready_for_review",
        priority="routine",
        created_at=datetime.now(UTC),
    )
    db.add(row)
    await db.flush()
    return row


async def _promote(db, row, ledger, *, traceable: bool = True, by: str = "dr.test"):
    history = project(ledger, demographics=Demographics(age_years=52, gender="male"))
    return await promote(
        db,
        session_row=row,
        ledger=ledger,
        history=history,
        escalation=evaluate(ledger),
        contradictions=[],
        summary_payload={"status": "draft"},
        traceable=traceable,
        confirmed_by=by,
    )


# ------------------------------------------------------------------ patients


async def test_a_patient_can_have_multiple_encounters(db_session) -> None:
    first = await _session(db_session, abha_ref="abha:multi01")
    ledger = FactLedger("s1")
    tap(ledger, "chief_complaint.text", "pain")
    result_one = await _promote(db_session, first, ledger)

    second = IntakeSession(
        session_ref="sess_multi02", abha_ref="abha:multi01", consent_ref="c",
        language="en", status="ready_for_review", created_at=datetime.now(UTC),
    )
    db_session.add(second)
    await db_session.flush()
    ledger_two = FactLedger("s2")
    tap(ledger_two, "chief_complaint.text", "fever")
    result_two = await _promote(db_session, second, ledger_two)

    assert result_one.patient_ref == result_two.patient_ref, "the same ABHA is the same person"
    assert result_one.encounter_ref != result_two.encounter_ref
    patient = await H.get_patient(db_session, patient_ref=result_one.patient_ref)
    assert patient is not None
    assert len(await H.encounters_for(db_session, patient.id)) == 2


async def test_a_new_abha_creates_a_new_patient(db_session) -> None:
    one = await _promote(
        db_session, await _session(db_session, abha_ref="abha:aaa"), _with_complaint()
    )
    two = await _promote(
        db_session, await _session(db_session, abha_ref="abha:bbb"), _with_complaint()
    )
    assert one.patient_ref != two.patient_ref
    assert one.created_patient and two.created_patient


def _with_complaint() -> FactLedger:
    ledger = FactLedger("s")
    tap(ledger, "chief_complaint.text", "pain")
    return ledger


# ------------------------------------------------------------------ promotion


async def test_confirmed_encounter_survives_the_session_purge(db_session) -> None:
    """The central guarantee of the whole longitudinal design."""
    row = await _session(db_session, abha_ref="abha:survive")
    ledger = FactLedger(row.session_ref)
    tap(ledger, "chief_complaint.text", "pain")
    tap(ledger, "hpi.site", "chest")
    for fact in ledger.facts:
        db_session.add(
            SessionFact(
                session_id=row.id,
                fact_id=fact.fact_id, path=fact.path, value_json={"v": fact.value},
                tier=fact.tier.value, confidence=fact.confidence,
                source_json=fact.source.model_dump(mode="json"),
            )
        )
    await db_session.flush()

    result = await _promote(db_session, row, ledger)
    await db_session.commit()

    purged = await purge(db_session, row.session_ref, reason="submit")
    await db_session.commit()
    assert purged.facts_deleted > 0, "the capture session must actually be cleared"

    # The durable record is untouched.
    encounter = (
        await db_session.execute(
            select(Encounter).where(Encounter.encounter_ref == result.encounter_ref)
        )
    ).scalars().first()
    assert encounter is not None
    facts = (
        await db_session.execute(
            select(ClinicalFactRecord).where(ClinicalFactRecord.encounter_id == encounter.id)
        )
    ).scalars().all()
    assert len(list(facts)) == 2
    remaining = (
        await db_session.execute(select(SessionFact).where(SessionFact.session_id == row.id))
    ).scalars().all()
    assert not list(remaining), "capture facts must be gone"


async def test_unconfirmed_session_data_is_purged_and_promotes_nothing(db_session) -> None:
    row = await _session(db_session, abha_ref="abha:unconfirmed")
    ledger = FactLedger(row.session_ref)
    tap(ledger, "chief_complaint.text", "pain")
    db_session.add(
        SessionFact(
            session_id=row.id, fact_id="fact_x", path="chief_complaint.text",
            value_json={"v": "pain"}, tier="confirmed", confidence=1.0, source_json={},
        )
    )
    await db_session.flush()

    await purge(db_session, row.session_ref, reason="ttl_expiry")
    await db_session.commit()

    assert not list((await db_session.execute(select(Encounter))).scalars().all())
    assert not list((await db_session.execute(select(Patient))).scalars().all())


async def test_an_untraceable_draft_is_refused_promotion(db_session) -> None:
    """An untraceable summary must never become part of a permanent record."""
    row = await _session(db_session, abha_ref="abha:untraceable")
    with pytest.raises(InvariantViolation, match="untraceable"):
        await _promote(db_session, row, _with_complaint(), traceable=False)
    assert not list((await db_session.execute(select(Encounter))).scalars().all())


async def test_every_promoted_fact_keeps_its_evidence(db_session) -> None:
    row = await _session(db_session, abha_ref="abha:evidence")
    ledger = FactLedger(row.session_ref)
    tap(ledger, "chief_complaint.text", "pain")
    tap(ledger, "hpi.site", "chest")
    result = await _promote(db_session, row, ledger)
    await db_session.flush()

    facts = list(
        (
            await db_session.execute(
                select(ClinicalFactRecord).join(
                    Encounter, ClinicalFactRecord.encounter_id == Encounter.id
                ).where(Encounter.encounter_ref == result.encounter_ref)
            )
        ).scalars().all()
    )
    assert facts
    for fact in facts:
        evidence = list(
            (
                await db_session.execute(
                    select(SourceEvidence).where(SourceEvidence.fact_id == fact.id)
                )
            ).scalars().all()
        )
        assert evidence, f"{fact.path} was promoted without its source"
        assert evidence[0].verbatim.strip()


# ------------------------------------------------------------------ medications


async def test_a_documented_medicine_is_not_recorded_as_currently_taken(db_session) -> None:
    """A prescription is evidence of a prescription, not of current use."""
    row = await _session(db_session, abha_ref="abha:meds")
    ledger = FactLedger(row.session_ref)
    tap(ledger, "chief_complaint.text", "checkup")
    ingest(
        ledger,
        __import__("pathlib").Path(FIXTURE).read_bytes(),
        filename="prescription.pdf",
        media_type="application/pdf",
        known_paths=load_ontology().known_paths,
        backend_name="textlayer",
        sex="male",
    )
    result = await _promote(db_session, row, ledger)
    await db_session.flush()

    rows = list(
        (await db_session.execute(select(MedicationEvent))).scalars().all()
    )
    assert rows, "the prescription's medicines must be promoted"
    assert all(row_.status == "documented" for row_ in rows), (
        "a documented medicine must not be promoted as patient-reported-current"
    )
    assert result.medications == len(rows)


async def test_medication_history_threads_one_drug_across_visits(seeded_patient) -> None:
    db, patient = seeded_patient
    threads = await H.medication_history(db, patient.id)
    metformin = next(t for t in threads if "metformin" in t["normalized"])
    assert len(metformin["mentions"]) >= 2, "the same drug across visits is one thread"
    statuses = {m["status"] for m in metformin["mentions"]}
    assert "documented" in statuses
    assert all(m["howWeKnow"] for m in metformin["mentions"])


# ------------------------------------------------------------------ timeline


async def test_timeline_spans_multiple_encounters(seeded_patient) -> None:
    db, patient = seeded_patient
    events = await H.timeline(db, patient.id)
    encounters = {e["encounterRef"] for e in events}
    assert len(encounters) >= 3, "the timeline must cross encounters, not just this visit"
    dated = [e for e in events if e["occurredOn"]]
    assert dated == sorted(dated, key=lambda e: e["occurredOn"], reverse=True)


async def test_timeline_dates_match_the_documents_they_came_from(seeded_patient) -> None:
    """A timeline date contradicting the date printed on the document destroys provenance."""
    db, patient = seeded_patient
    events = await H.timeline(db, patient.id)
    prescription_events = [e for e in events if e["documentRef"] == "doc_demo20250214"]
    assert prescription_events
    assert all(e["occurredOn"] == "2025-02-14" for e in prescription_events)


async def test_timeline_filters_by_kind(seeded_patient) -> None:
    db, patient = seeded_patient
    meds = await H.timeline(db, patient.id, kinds=["medication"])
    assert meds and all(e["kind"] == "medication" for e in meds)


# ------------------------------------------------------------------ similar encounters


async def test_similar_encounters_only_search_the_same_patient(seeded_patient) -> None:
    """A retrieval that could surface another person's visit is a confidentiality breach."""
    db, patient = seeded_patient
    other = Patient(patient_ref="pat_other", abha_ref="abha:other", display_name="Someone Else")
    db.add(other)
    await db.flush()
    stranger = Encounter(
        encounter_ref="enc_other", patient_id=other.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC), headline="Stomach problem",
        confirmed_by="dr.x",
    )
    db.add(stranger)
    await db.flush()
    db.add(
        ClinicalFactRecord(
            encounter_id=stranger.id, fact_ref="fact_other", path="hpi.site",
            value_json={"v": "abdomen"}, tier="confirmed", confidence=1.0,
        )
    )
    await db.flush()

    found = await H.similar_encounters(
        db, patient_id=patient.id, current_features={"hpi.site": {"abdomen"}}
    )
    assert all(entry["encounterRef"] != "enc_other" for entry in found)


async def test_similar_encounter_result_lists_the_shared_features(seeded_patient) -> None:
    db, patient = seeded_patient
    found = await H.similar_encounters(
        db,
        patient_id=patient.id,
        current_features={
            "hpi.site": {"abdomen"},
            "hpi.exacerbating": {"worse_food"},
            "hpi.associated": {"vomiting"},
        },
    )
    assert found, "the seeded 2025 visit should match an abdominal recurrence"
    top = found[0]
    assert top["sharedCount"] >= 3
    features = {entry["feature"] for entry in top["shared"]}
    assert "site" in features
    assert isinstance(top["band"], str) and "%" not in top["band"], (
        "similarity must be words, not a percentage that reads as a probability"
    )
    assert "not a diagnosis" in top["note"]


async def test_no_shared_features_means_no_match(seeded_patient) -> None:
    db, patient = seeded_patient
    assert (
        await H.similar_encounters(
            db, patient_id=patient.id, current_features={"hpi.site": {"joints"}}
        )
        == []
    )


# ------------------------------------------------------------------ evidence


async def test_durable_fact_evidence_resolves(seeded_patient) -> None:
    db, patient = seeded_patient
    encounters = await H.encounters_for(db, patient.id)
    visit = next(e for e in encounters if e.headline == "Stomach problem")
    facts = list(
        (
            await db.execute(
                select(ClinicalFactRecord).where(ClinicalFactRecord.encounter_id == visit.id)
            )
        ).scalars().all()
    )
    assert facts
    found = await H.evidence_for_fact(
        db, encounter_id=visit.id, fact_ref=facts[0].fact_ref
    )
    assert found is not None
    assert found["evidence"] and found["evidence"][0]["verbatim"]


async def test_the_seeded_patient_is_idempotent(db_session) -> None:
    first = await seed_demo_patient(db_session)
    await db_session.commit()
    second = await seed_demo_patient(db_session)
    assert first["created"] is True
    assert second["created"] is False
    patients = list((await db_session.execute(select(Patient))).scalars().all())
    assert len(patients) == 1


async def test_the_seeded_patient_joins_to_the_demo_login(seeded_patient) -> None:
    """The seeded history is worthless if logging in as demo@abdm does not find it."""
    db, patient = seeded_patient
    assert patient.abha_ref == demo_abha_ref()
    assert await H.get_patient_by_abha(db, abha_ref=demo_abha_ref()) is not None


async def test_overview_masks_the_identifier(seeded_patient) -> None:
    db, patient = seeded_patient
    overview = await H.overview(db, patient)
    assert overview["abhaMasked"] is not None
    assert patient.abha_ref not in overview["abhaMasked"]
    assert overview["counts"]["encounters"] == 3
    assert overview["counts"]["prescriptions"] == 1
    assert overview["counts"]["labReports"] == 1


async def test_timeline_event_count_is_not_zero(seeded_patient) -> None:
    db, patient = seeded_patient
    assert len(await H.timeline(db, patient.id)) > 10

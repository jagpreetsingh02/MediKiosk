"""The bridge from a session under review to the person it belongs to.

This is the join that did not exist: the queue hands out a session reference, the history is
keyed by patient, and the physician surface needed both. Everything here is about that seam —
that it resolves, that it refuses when it should, and that the two halves of the screen never
disagree with each other about the same question.
"""

from __future__ import annotations

import pytest

from app.modules.encounter import history as H


@pytest.fixture
async def patient_with_history(seeded_patient):
    db, patient = seeded_patient
    return db, patient


# ------------------------------------------------------ reconciliation, one source of truth


async def test_a_denial_today_flags_documented_medicines(patient_with_history) -> None:
    db, patient = patient_with_history
    findings = await H.reconcile_live_session(
        db,
        patient_id=patient.id,
        values={"drug_allergy.taking_medicines": False},
    )
    assert findings, "a patient denying medication with a prescription on file is the case"
    reconciliation = next(f for f in findings if f["kind"] == "medication_reconciliation")
    assert reconciliation["historicalEvidence"]
    # Neither side is declared correct. That is the whole point of §16.
    assert "may have stopped" in reconciliation["note"]
    assert reconciliation["status"] == "Needs medication reconciliation"


async def test_the_panel_and_the_banner_agree_about_today(patient_with_history) -> None:
    """These were answering the same question two ways on one screen.

    `medication_history` could only see the last *confirmed* encounter, so a denial in the
    session being reviewed raised a banner at the top of the physician's view while the
    medication panel underneath it said no reconciliation was needed.
    """
    db, patient = patient_with_history
    live = {"drug_allergy.taking_medicines": False}

    banner = await H.reconcile_live_session(db, patient_id=patient.id, values=live)
    threads = await H.medication_history(db, patient.id, live_values=live)

    assert any(f["kind"] == "medication_reconciliation" for f in banner)
    documented = [t for t in threads if any(m["status"] == "documented" for m in t["mentions"])]
    assert documented
    assert all(t["needsReconciliation"] for t in documented), (
        "the medication panel must reach the same conclusion as the banner above it"
    )


async def test_a_medicine_the_patient_confirms_is_not_flagged_as_denied(
    patient_with_history,
) -> None:
    db, patient = patient_with_history
    threads = await H.medication_history(db, patient.id)
    name = next(
        t["name"] for t in threads if any(m["status"] == "documented" for m in t["mentions"])
    )

    findings = await H.reconcile_live_session(
        db,
        patient_id=patient.id,
        values={"drug_allergy.taking_medicines": True, "medications[0].name": name},
    )
    mentioned = {
        evidence["name"] for finding in findings for evidence in finding["historicalEvidence"]
    }
    assert name not in mentioned, "a medicine the patient just named is not an open question"


async def test_a_documented_medicine_not_mentioned_today_is_asked_about_not_assumed(
    patient_with_history,
) -> None:
    """Silence is not evidence of stopping, and a past prescription is not evidence of use."""
    db, patient = patient_with_history
    findings = await H.reconcile_live_session(
        db, patient_id=patient.id, values={"drug_allergy.taking_medicines": True}
    )
    unmentioned = [f for f in findings if f["kind"] == "medication_not_mentioned"]
    assert unmentioned
    assert all("Confirm whether" in f["status"] for f in unmentioned)
    assert all("not evidence" in f["note"] for f in unmentioned)


async def test_no_history_means_no_findings(db_session) -> None:
    """A first-time patient must not produce a wall of reconciliation warnings."""
    from app.modules.encounter.promote import find_or_create_patient

    patient, created = await find_or_create_patient(db_session, abha_ref="abha:nobody")
    assert created
    await db_session.flush()
    findings = await H.reconcile_live_session(
        db_session,
        patient_id=patient.id,
        values={"drug_allergy.taking_medicines": False},
    )
    assert findings == []


# ----------------------------------------------------------------- similarity, from a ledger


async def test_similarity_works_before_the_encounter_is_committed(
    patient_with_history,
) -> None:
    """The physician needs this while deciding. After commit it is a historical curiosity."""
    db, patient = patient_with_history
    features = await H.features_from_ledger(
        {
            "hpi.site": "abdomen",
            "hpi.character": "burning",
            "hpi.exacerbating": ["worse_food"],
        }
    )
    similar = await H.similar_encounters(db, patient_id=patient.id, current_features=features)
    assert similar, "the seeded 2025 visit shares site, character and the post-meal pattern"
    shared = {entry["value"] for entry in similar[0]["shared"]}
    assert {"abdomen", "burning", "worse_food"} <= shared


async def test_a_similarity_result_carries_no_percentage(patient_with_history) -> None:
    """A number between two encounters reads as a probability of recurrence whatever the
    label says. Invariant 1 is why there is not one."""
    db, patient = patient_with_history
    features = await H.features_from_ledger({"hpi.site": "abdomen"})
    similar = await H.similar_encounters(db, patient_id=patient.id, current_features=features)
    assert similar
    assert "%" not in str(similar[0])
    assert isinstance(similar[0]["band"], str)

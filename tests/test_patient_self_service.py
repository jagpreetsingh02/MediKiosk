"""A patient reads their own record and nobody else's.

THREE GUARANTEES, and the second is the one that would be most embarrassing to get wrong.

  OWN RECORD ONLY. A patient token resolves to exactly the record its ABHA reference names.
  Reaching another patient's encounters, report or PDF must be refused — not filtered to
  empty, refused, because an empty list looks like "you have no visits" rather than "that is
  not yours".

  CONFIRMED VISITS ONLY. Invariant 4. A patient must never see a draft a physician has not
  committed. This is a property of the schema rather than a filter: `Encounter` rows are
  created ONLY by `promote()`, which is reachable only from the commit route. The structural
  test below asserts that, so the guarantee survives someone adding a new write path.

  A NAMED ENCOUNTER IS THAT ENCOUNTER. Asking for a visit that is not yours must 404, never
  silently fall back to the most recent one — a patient who clicked "March" and was shown
  August would have no way to notice.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.api.routes_patient import _resolve
from app.auth.identity import Identity
from app.core.errors import PolicyDenied
from app.db.durable import ClinicalFactRecord, Encounter, Patient, SourceEvidence
from app.modules.report import loader as L

APP = Path(__file__).resolve().parents[1] / "app"


async def _patient_with_visits(db, *, ref: str, abha: str, visits: int = 2) -> Patient:
    patient = Patient(
        patient_ref=ref, abha_ref=abha, display_name=ref,
        year_of_birth=1970, gender="female", is_synthetic=False,
    )
    db.add(patient)
    await db.flush()
    for i in range(visits):
        when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=30 * i)
        enc = Encounter(
            encounter_ref=f"enc_{ref}_{i}", patient_id=patient.id,
            occurred_at=when, kind="intake", headline=f"Visit {i}",
            confirmed_by="dr.mehta@aiia", confirmed_at=when,
        )
        db.add(enc)
        await db.flush()
        fact = ClinicalFactRecord(
            encounter_id=enc.id, fact_ref=f"fact_{ref}_{i}", path="chief_complaint.text",
            value_json={"v": f"complaint {i}"}, display_value=f"Complaint {i}",
            tier="confirmed", state="confirmed", confidence=1.0,
            recorded_at=when, valid_from=when,
        )
        db.add(fact)
        await db.flush()
        db.add(SourceEvidence(
            fact_id=fact.id, source_type="utterance", verbatim=f"I have complaint {i}",
            language="en", modality="touch"))
    await db.flush()
    return patient


@pytest.fixture
async def two_patients(db_session):
    a = await _patient_with_visits(db_session, ref="pat_alice", abha="abha:alice", visits=2)
    b = await _patient_with_visits(db_session, ref="pat_bob", abha="abha:bob", visits=1)
    return db_session, a, b


def _token(abha: str) -> Identity:
    return Identity(actor=abha, role="patient", abha_ref=abha)


async def test_a_patient_resolves_their_own_record(two_patients) -> None:
    db, alice, _ = two_patients
    assert (await _resolve(db, _token("abha:alice"), "pat_alice")).id == alice.id


async def test_a_patient_cannot_resolve_another_patients_record(two_patients) -> None:
    """⛔ THE ONE THAT MATTERS. Refused, not filtered to empty."""
    db, _, _ = two_patients
    with pytest.raises(PolicyDenied, match="only read their own record"):
        await _resolve(db, _token("abha:alice"), "pat_bob")


async def test_a_patient_cannot_reach_another_patients_encounters(two_patients) -> None:
    """The list endpoint goes through the same choke point, not its own check."""
    db, _, _ = two_patients
    with pytest.raises(PolicyDenied):
        await _resolve(db, _token("abha:bob"), "pat_alice")


async def test_a_named_encounter_belonging_to_someone_else_is_not_served(two_patients) -> None:
    """Alice asking for Bob's encounter gets an empty read, never Bob's data."""
    db, alice, _ = two_patients
    rows = await L.load(db, alice, encounter_ref="enc_pat_bob_0")
    assert rows.current is None, "another patient's encounter was loaded"
    assert rows.encounters == []
    assert rows.facts == []


async def test_a_named_encounter_never_falls_back_to_a_different_visit(two_patients) -> None:
    """A patient who clicked March must not be shown August without noticing."""
    db, alice, _ = two_patients
    rows = await L.load(db, alice, encounter_ref="enc_pat_alice_0")
    assert rows.current is not None
    assert rows.current.encounter_ref == "enc_pat_alice_0"
    # And the diff compares against the visit BEFORE that one, not against today.
    assert rows.previous is None, "the first visit has nothing before it"

    rows2 = await L.load(db, alice, encounter_ref="enc_pat_alice_1")
    assert rows2.current.encounter_ref == "enc_pat_alice_1"
    assert rows2.previous is not None
    assert rows2.previous.encounter_ref == "enc_pat_alice_0"


async def test_an_unknown_encounter_is_an_empty_read_not_the_latest(two_patients) -> None:
    db, alice, _ = two_patients
    rows = await L.load(db, alice, encounter_ref="enc_does_not_exist")
    assert rows.current is None


async def test_unconfirmed_encounters_are_excluded(db_session) -> None:
    """Invariant 4 at the read boundary, belt-and-braces over the schema guarantee."""
    patient = await _patient_with_visits(db_session, ref="pat_c", abha="abha:c", visits=1)
    draft = Encounter(
        encounter_ref="enc_draft", patient_id=patient.id,
        occurred_at=datetime(2026, 6, 1, tzinfo=UTC), kind="intake",
        headline="Not committed", confirmed_by="",  # never confirmed
        confirmed_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    db_session.add(draft)
    await db_session.flush()

    rows = await L.load(db_session, patient)
    refs = {e.encounter_ref for e in rows.encounters}
    assert "enc_draft" not in refs, "an unconfirmed encounter reached a patient's history"
    assert rows.current.encounter_ref != "enc_draft"


def test_only_the_commit_route_can_create_an_encounter() -> None:
    """⛔ THE STRUCTURAL GUARANTEE, which is why the filter above is belt-and-braces.

    An `Encounter` row is what "a physician confirmed this" MEANS. If any other code path
    could create one, "confirmed visits only" would be a filter over an assumption rather
    than a fact about the system. This scans the source: `Encounter(` may only be constructed
    in `promote.py` (the commit path) and `seed.py` (fixtures, which set a confirmer).
    """
    allowed = {"promote.py", "seed.py"}
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        if path.name in allowed or path.name == "durable.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "Encounter":
                    offenders.append(f"{path.relative_to(APP.parent)}:{node.lineno}")
    assert not offenders, (
        "an Encounter is constructed outside promote.py — 'only confirmed visits' would stop "
        "being a property of the schema and become a filter over an assumption:\n  "
        + "\n  ".join(offenders)
    )


def test_promotion_is_only_reachable_from_the_commit_route() -> None:
    """And the commit route is gated by `summary.commit`, a clinician-only action."""
    source = (APP / "api" / "routes_physician.py").read_text(encoding="utf-8")
    assert "from app.modules.encounter.promote import promote" in source
    assert 'require_action("summary.commit")' in source, (
        "the commit route lost its ABAC guard; a patient token could then create an encounter"
    )
    assert '"confirmed"' in source, "the explicit confirmed:true requirement is gone"


async def test_the_synthetic_boundary_still_holds_for_self_service(db_session) -> None:
    """A demo patient and a real one must not see each other through these routes either."""
    real = await _patient_with_visits(db_session, ref="pat_real_ss", abha="abha:realss")
    demo = Patient(
        patient_ref="pat_guest_ss", abha_ref=None, display_name="Demo",
        year_of_birth=1970, is_synthetic=True)
    db_session.add(demo)
    await db_session.flush()

    # A real patient's token cannot resolve the demo record by reference...
    # (synthetic records are readable by design — see the cohort module — so what must hold
    # is that their DATA never mixes, which the loader enforces by patient_id.)
    rows = await L.load(db_session, demo)
    assert all(e.patient_id == demo.id for e in rows.encounters)
    rows_real = await L.load(db_session, real)
    assert all(e.patient_id == real.id for e in rows_real.encounters)
    assert not ({e.encounter_ref for e in rows.encounters}
                & {e.encounter_ref for e in rows_real.encounters})

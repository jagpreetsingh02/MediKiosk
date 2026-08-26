"""Demo data and clinical data must never retrieve against each other.

⛔ THE FAILURE THIS PREVENTS HAS TWO DIRECTIONS, AND THE SECOND ONE IS THE DANGEROUS ONE.

    a demo patient retrieving against a real one
        a judge at a stand is shown a stranger's medical history. A privacy breach.

    a REAL patient retrieving against a DEMO one
        a clinician is shown a "similar previous visit" that was invented for a conference.
        Same type, same click-to-source affordance, nothing on screen saying it is fiction.
        A clinical safety failure — and the one a `WHERE is_synthetic = false` written from
        the demo's point of view would miss completely.

Guest mode writes REAL ROWS INTO THE REAL SCHEMA on purpose (see `guest.py`), so this is not
hypothetical tidiness: the two populations genuinely share every table.

The tests below build a synthetic and a non-synthetic patient with DELIBERATELY IDENTICAL
clinical features — same complaint, same site, same character — so that any retrieval which
matches on content rather than on cohort would return the other one. If the boundary were
missing, these would fail loudly rather than pass by luck.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.durable import ClinicalFactRecord, Encounter, Patient, SourceEvidence
from app.modules.encounter import history as H
from app.modules.encounter.cohort import cohort_label, restrict_to_cohort, same_cohort

APP = Path(__file__).resolve().parents[1] / "app"

#: The same complaint, recorded for both patients. Identical on purpose.
SHARED_FEATURES = (
    ("chief_complaint.text", "stomach", "Stomach problem"),
    ("hpi.site", "abdomen", "Stomach / abdomen"),
    ("hpi.character", "burning", "Burning"),
)


async def _make_patient(db, *, ref: str, synthetic: bool) -> Patient:
    patient = Patient(
        patient_ref=ref,
        abha_ref=f"abha:{ref}",
        display_name=ref,
        year_of_birth=1970,
        gender="female",
        is_synthetic=synthetic,
    )
    db.add(patient)
    await db.flush()

    encounter = Encounter(
        encounter_ref=f"enc_{ref}",
        patient_id=patient.id,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind="intake",
        headline="Stomach problem",
        confirmed_by="dr.test",
        confirmed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db.add(encounter)
    await db.flush()

    for i, (path, value, verbatim) in enumerate(SHARED_FEATURES):
        fact = ClinicalFactRecord(
            encounter_id=encounter.id,
            fact_ref=f"fact_{ref}_{i}",
            path=path,
            value_json={"v": value},
            display_value=verbatim,
            tier="confirmed",
            state="confirmed",
            confidence=1.0,
            recorded_at=encounter.occurred_at,
            valid_from=encounter.occurred_at,
        )
        db.add(fact)
        await db.flush()
        db.add(
            SourceEvidence(
                fact_id=fact.id,
                source_type="utterance",
                verbatim=verbatim,
                language="en",
                modality="touch",
                question_id=path,
            )
        )
    await db.flush()
    return patient


@pytest.fixture
async def two_populations(db_session):
    """One synthetic patient and one clinical patient, clinically indistinguishable."""
    demo = await _make_patient(db_session, ref="pat_demo_boundary", synthetic=True)
    real = await _make_patient(db_session, ref="pat_real_boundary", synthetic=False)
    await db_session.flush()
    return db_session, demo, real


async def test_a_demo_patient_never_retrieves_a_real_one(two_populations) -> None:
    db, demo, real = two_populations
    stmt = restrict_to_cohort(select(Patient), viewer=demo)
    found = {p.patient_ref for p in (await db.execute(stmt)).scalars().all()}
    assert real.patient_ref not in found, (
        "a demo record reached a clinical one — a judge would be shown a real history"
    )
    assert demo.patient_ref in found


async def test_a_real_patient_never_retrieves_a_demo_one(two_populations) -> None:
    """THE DIRECTION THAT MATTERS MOST. A clinician must not be shown invented history."""
    db, demo, real = two_populations
    stmt = restrict_to_cohort(select(Patient), viewer=real)
    found = {p.patient_ref for p in (await db.execute(stmt)).scalars().all()}
    assert demo.patient_ref not in found, (
        "a clinical record reached demo data — a clinician would be shown a 'similar "
        "previous visit' that was invented for a conference stand"
    )
    assert real.patient_ref in found


async def test_the_boundary_holds_on_a_join_across_encounters(two_populations) -> None:
    """The realistic shape: a cross-patient retrieval joining encounters to patients."""
    db, demo, real = two_populations
    for viewer, forbidden in ((demo, real), (real, demo)):
        stmt = restrict_to_cohort(select(Encounter).join(Patient), viewer=viewer)
        refs = {e.encounter_ref for e in (await db.execute(stmt)).scalars().all()}
        assert f"enc_{forbidden.patient_ref}" not in refs
        assert f"enc_{viewer.patient_ref}" in refs


async def test_identical_features_are_not_enough_to_cross(two_populations) -> None:
    """Proves the fixture is actually adversarial: the two records ARE the same clinically."""
    db, demo, real = two_populations
    demo_enc = (
        await db.execute(select(Encounter).where(Encounter.patient_id == demo.id))
    ).scalars().first()
    real_enc = (
        await db.execute(select(Encounter).where(Encounter.patient_id == real.id))
    ).scalars().first()
    assert await H.current_features(db, demo_enc.id) == await H.current_features(db, real_enc.id), (
        "the fixture must be clinically identical, or these tests pass for the wrong reason"
    )
    assert not same_cohort(demo, real)


async def test_similar_encounters_is_scoped_to_one_patient(two_populations) -> None:
    """`similar_encounters` takes a patient_id, so it cannot cross — asserted, not assumed."""
    db, demo, real = two_populations
    real_enc = (
        await db.execute(select(Encounter).where(Encounter.patient_id == real.id))
    ).scalars().first()
    found = await H.similar_encounters(
        db, patient_id=real.id, current_features=await H.current_features(db, real_enc.id)
    )
    refs = {f["encounterRef"] for f in found}
    assert f"enc_{demo.patient_ref}" not in refs


def test_a_synthetic_record_is_always_labelled() -> None:
    """The UI is never permitted to render a demo record with no marking."""
    assert cohort_label(Patient(patient_ref="x", is_synthetic=True)) == "synthetic"
    assert cohort_label(Patient(patient_ref="y", is_synthetic=False)) == "clinical"


def test_the_boundary_is_symmetric_by_construction() -> None:
    """A source scan: the filter must compare to the VIEWER, never to a hardcoded literal.

    `WHERE is_synthetic = false` would be correct-looking, would pass every runtime test that
    only checks the demo direction, and would silently let real patients retrieve demo data.
    Only reading the expression catches it.
    """
    source = (APP / "modules" / "encounter" / "cohort.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute):
            if node.left.attr == "is_synthetic":
                right = node.comparators[0]
                assert not isinstance(right, ast.Constant), (
                    "the cohort filter compares is_synthetic to a literal; it must compare to "
                    "the viewer's own value or the boundary only works in one direction"
                )


async def test_a_patient_token_may_read_a_synthetic_record(two_populations) -> None:
    """A demo record is nobody's private record, and refusing broke the judge path.

    Guests are created with `abha_ref = None` (no fabricated identity), then the demo signs
    the visitor in through the mock ABHA IdP to run the intake. That token's abha_ref can
    never equal None, so the ownership check returned 403 on the visitor's OWN demo brief —
    protecting nothing, because the record contains no person's data.
    """
    from app.api.routes_patient import _resolve
    from app.auth.identity import Identity

    db, demo, real = two_populations
    visitor = Identity(actor="demo@abdm", role="patient", abha_ref="abha:someone-else")

    resolved = await _resolve(db, visitor, demo.patient_ref)
    assert resolved.patient_ref == demo.patient_ref


async def test_a_patient_token_still_cannot_read_someone_elses_clinical_record(
    two_populations,
) -> None:
    """The exception is for SYNTHETIC records only. Ownership is unchanged for real ones."""
    from app.api.routes_patient import _resolve
    from app.auth.identity import Identity
    from app.core.errors import PolicyDenied

    db, demo, real = two_populations
    visitor = Identity(actor="someone@abdm", role="patient", abha_ref="abha:not-theirs")

    with pytest.raises(PolicyDenied, match="only read their own record"):
        await _resolve(db, visitor, real.patient_ref)

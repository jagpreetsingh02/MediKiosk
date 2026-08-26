"""Guest mode — a real record, created on demand, marked as demo and kept apart.

WHAT A JUDGE GETS BY PRESSING ONE BUTTON: a patient with three dated lab reports, a
prescription that OCR genuinely misreads, two prior visits to diff against, and a voice
answer with a measured ASR confidence. All of it built by `seed.build_history` — the same
function the seeded demo patient uses, including the real OCR run and the real Vosk
transcription. Nothing here is a lighter-weight imitation of the real path.

That matters because "What changed?" and the lab trajectory are the two screens that make
longitudinal memory legible, and both are empty on a patient with one visit. A guest who
presses Try Demo and lands on a blank brief has been shown the plumbing, not the product.

⛔ THE ROWS ARE REAL, WHICH IS WHY THE BOUNDARY IS ENFORCED AND NOT ASSUMED. Guest patients
are written into the same tables as everything else, flagged `is_synthetic=True`, and
`app/modules/encounter/cohort.py` keeps retrieval from crossing between the populations in
either direction. See its docstring for why the direction that matters most is the one people
forget.

RESET IS A DELETE AND REBUILD, NOT AN UPDATE. A demo is run repeatedly in front of people,
and the second run starting from the first run's leftovers is how a live demo goes wrong.
`reset()` removes the guest patient entirely — the ON DELETE CASCADE takes every encounter,
fact, document and piece of evidence with it — then rebuilds from the same seed, so the
starting counts are identical every time. `tests/test_guest_mode.py` asserts exactly that.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.durable import (
    ClinicalFactRecord,
    Encounter,
    MedicationEvent,
    ObservationEvent,
    Patient,
    SourceEvidence,
)
from app.modules.encounter import seed as S

log = get_logger(__name__)

#: Every guest record's ref starts with this, so one glance at a row says what it is.
GUEST_PREFIX = "pat_guest_"

#: The name shown on screen. Deliberately not a plausible person's name — a demo record
#: should not be mistakable for a real patient in a screenshot.
GUEST_DISPLAY_NAME = "Demo Patient (synthetic)"


def is_guest_ref(patient_ref: str) -> bool:
    return patient_ref.startswith(GUEST_PREFIX)


async def create(db: AsyncSession) -> dict[str, Any]:
    """Create one guest patient with the full seeded history. The caller commits.

    Sweeps expired guests first. Guest creation is the one moment guest records are definitely
    being made, which makes it the natural place to clear the old ones — and it means the
    cleanup needs no scheduler, which this deployment does not have.
    """
    from app.modules.encounter.sweep import sweep_on_create

    await sweep_on_create(db)

    ref = f"{GUEST_PREFIX}{uuid.uuid4().hex[:10]}"
    patient = Patient(
        patient_ref=ref,
        # NO abha_ref. A guest has not authenticated with anything, and minting a
        # plausible-looking one would put a fake identity into the column real identities
        # live in. Nullable precisely so this case can be honest.
        abha_ref=None,
        display_name=GUEST_DISPLAY_NAME,
        year_of_birth=datetime.now(UTC).year - 52,
        gender="male",
        preferred_language="en",
        is_synthetic=True,
    )
    db.add(patient)
    await db.flush()

    # THE PATIENT'S OWN ID, hex, as the ref suffix. Guaranteed unique by the primary key —
    # no collision is possible — and short, which matters: `timeline_event.event_ref` is
    # String(32) and a longer suffix overflowed it (`evt_doc_demo20240603_<11 chars>_0` is
    # 34). Using the uuid tail looked tidier and broke the column.
    built = await S.build_history(db, patient, suffix=f"_{patient.id:x}")
    log.info("guest.created", patientRef=ref, **built)
    return {
        "patientRef": ref,
        "displayName": patient.display_name,
        "isSynthetic": True,
        **built,
    }


async def get(db: AsyncSession, patient_ref: str) -> Patient | None:
    return (
        await db.execute(
            select(Patient).where(
                Patient.patient_ref == patient_ref, Patient.is_synthetic.is_(True)
            )
        )
    ).scalars().first()


async def counts(db: AsyncSession, patient: Patient) -> dict[str, int]:
    """The shape of a guest record, used to prove a reset restored it exactly."""
    encounter_ids = (
        select(Encounter.id).where(Encounter.patient_id == patient.id).scalar_subquery()
    )
    out: dict[str, int] = {}
    out["encounters"] = int(
        (
            await db.execute(
                select(func.count()).select_from(Encounter).where(
                    Encounter.patient_id == patient.id
                )
            )
        ).scalar()
        or 0
    )
    out["facts"] = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ClinicalFactRecord)
                .where(ClinicalFactRecord.encounter_id.in_(encounter_ids))
            )
        ).scalar()
        or 0
    )
    out["evidence"] = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SourceEvidence)
                .where(
                    SourceEvidence.fact_id.in_(
                        select(ClinicalFactRecord.id).where(
                            ClinicalFactRecord.encounter_id.in_(encounter_ids)
                        )
                    )
                )
            )
        ).scalar()
        or 0
    )
    for model, key in ((MedicationEvent, "medications"), (ObservationEvent, "observations")):
        out[key] = int(
            (
                await db.execute(
                    select(func.count()).select_from(model).where(model.patient_id == patient.id)
                )
            ).scalar()
            or 0
        )
    return out


async def reset(db: AsyncSession, patient_ref: str) -> dict[str, Any]:
    """Delete the guest record and rebuild it from seed. The caller commits.

    A NEW REF EACH TIME, deliberately. Reusing the old one would leave any tab still holding
    it pointing at a record whose rows have all been replaced underneath — the same
    identifier, different data, which is the confusing failure rather than the obvious one.
    The response carries the new ref and the frontend swaps to it.
    """
    existing = await get(db, patient_ref)
    if existing is None:
        # Nothing to reset. Creating one is what the caller wanted anyway, and refusing here
        # would strand a judge whose session outlived the row.
        created = await create(db)
        return {**created, "wasReset": False, "note": "No such demo record; started a new one."}

    before = await counts(db, existing)
    # CASCADE does the rest: encounters, facts, evidence, documents, timeline, decisions.
    await db.execute(delete(Patient).where(Patient.id == existing.id))
    await db.flush()

    created = await create(db)
    after = await counts(db, await get(db, created["patientRef"]))  # type: ignore[arg-type]

    log.info("guest.reset", old=patient_ref, new=created["patientRef"], before=before, after=after)
    return {
        **created,
        "wasReset": True,
        "countsBefore": before,
        "countsAfter": after,
        # Proved, not asserted: the numbers are returned so the caller — and the test — can
        # see that a reset restored the same starting state rather than a similar one.
        "identical": before == after,
    }

"""The auditor's surface. Every route below is a GET. There is no other verb in this file.

⛔ THAT IS NOT A STYLE CHOICE, it is the whole point of the role. `config/policy.yaml` grants
`auditor` exactly `audit.read`, `audit.verify` and `system.about` — no `*.commit`, no
`*.edit`, no `document.verify`, nothing that writes a clinical row. `require_action` refuses
before this file's code ever runs, so a POST added here by mistake would still be reachable
by role — which is why there is no POST here to add by mistake.
`tests/test_auditor_role.py` proves the stronger, structural version: that no mutating route
anywhere in the API is reachable by any action this role holds.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import CurrentIdentity, DbSession, require_action
from app.audit.chain import record
from app.audit.review import full_review, no_assessment_claim_check, tamper_demonstration
from app.core.errors import ValidationError
from app.db.durable import Encounter, Patient
from app.modules.report import brief as B
from app.modules.report import loader as L

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


async def _encounter_or_404(db: DbSession, encounter_ref: str) -> Encounter:
    encounter = (
        await db.execute(select(Encounter).where(Encounter.encounter_ref == encounter_ref))
    ).scalars().first()
    if encounter is None:
        raise ValidationError(f"No encounter {encounter_ref!r}.")
    return encounter


@router.get("/encounters/{encounter_ref}", dependencies=[Depends(require_action("audit.read"))])
async def review_encounter(
    db: DbSession, encounter_ref: str, identity: CurrentIdentity
) -> dict[str, Any]:
    """Everything an auditor needs for one visit: trail, chain, provenance, content claim.

    The content-claim check runs over the SAME assembled brief the physician and patient
    screens render — not a separate summary built for this endpoint, which could drift from
    what was actually shown.
    """
    encounter = await _encounter_or_404(db, encounter_ref)
    # `encounter.patient` is a lazy relationship — touching it here would trigger an
    # implicit lazy-load outside the greenlet the async driver expects, raising
    # MissingGreenlet at runtime. Fetch the row explicitly instead, the same way every
    # other caller of `L.load` already resolves its patient (see routes_patient.py).
    patient = await db.get(Patient, encounter.patient_id)
    if patient is None:
        raise ValidationError(f"No encounter {encounter_ref!r}.")
    rows = await L.load(db, patient, encounter_ref=encounter_ref)
    payload = B.assemble(rows)

    result = await full_review(db, encounter)
    result["noAssessmentClaim"] = await no_assessment_claim_check(payload)

    await record(
        db,
        actor=identity.actor,
        actor_role=identity.role,
        purpose_of_use="RESEARCH",
        action="audit.read",
        request_summary={"encounterRef": encounter_ref},
        response_summary={
            "chainIntact": result["chain"]["intact"],
            "provenanceComplete": result["provenance"]["complete"],
        },
    )
    await db.commit()
    return result


@router.get("/tamper-demo", dependencies=[Depends(require_action("audit.read"))])
async def tamper_demo(db: DbSession) -> dict[str, Any]:
    """Corrupt one event in an in-memory COPY and show the chain catches it. Nothing written.

    See `app.audit.review.tamper_demonstration` for why the real table cannot be reached from
    here even by mistake. No audit event is written for calling this one — it reads nothing
    patient-specific and recording it would only add noise to every future encounter's trail.
    """
    return (await tamper_demonstration(db)).to_dict()

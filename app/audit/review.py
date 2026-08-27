"""What the auditor role reads. Nothing here writes anything.

⛔ THIS IS A READ-ONLY LAYER, STRUCTURALLY. Every function takes a session and returns a
dict; none calls `db.add`, `db.execute(insert(...))`, `db.execute(update(...))`, or
`db.execute(delete(...))`. `tests/test_auditor_role.py` proves the stronger claim — that the
`auditor` role in `config/policy.yaml` cannot reach ANY mutating route in the API — but this
module's own shape is the first line of that: there is nothing here to call that writes.

FOUR THINGS AN AUDITOR NEEDS FOR ONE ENCOUNTER, and each is built from data this project
already had before this file existed — this is a viewer, not a new subsystem:

    the audit trail        every audit_event sharing the encounter's consent_ref
    chain integrity         `app.audit.chain.verify_chain`, unchanged, over the whole log
    provenance completeness every durable fact has evidence, or an explicit absence state
    no assessment claim     `app.contracts.no_diagnosis.scan_for_assessment_language`,
                            the SAME scanner that gates every outbound payload
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.chain import GENESIS_HASH, compute_hash, count_events, row_payload, verify_chain
from app.contracts.no_diagnosis import scan_for_assessment_language
from app.db.durable import ClinicalFactRecord, Encounter, SourceEvidence
from app.db.models import AuditEvent

#: States a durable fact may legitimately carry with NO evidence — an explicit absence,
#: recorded because the patient declined or the question was never reached, never because
#: something was lost. Mirrors `app.modules.report.brief.ABSENCE_STATES` plus `not_asked`,
#: which the brief module handles as a separate branch rather than folding into the tuple.
ABSENCE_OK_WITHOUT_EVIDENCE = ("declined", "unknown", "not_asked")


async def audit_trail_for_encounter(
    db: AsyncSession, encounter: Encounter
) -> list[dict[str, Any]]:
    """Every audit event correlated to this encounter's capture session.

    `encounter.consent_ref` is the join key — set at promotion time (session 3A) from the
    same `session_ref` every `record()` call during capture already carried. This is why the
    trail is not limited to the commit itself: a document upload, a dialogue turn, an LLM
    call, all recorded under the same consent reference before the encounter existed at all.

    An encounter with no consent_ref (a seeded fixture predating that column, or a
    document-only encounter with no capture session) returns an empty list. That is reported
    honestly on screen rather than treated as an error — see the route.
    """
    if not encounter.consent_ref:
        return []
    rows = (
        await db.execute(
            select(AuditEvent)
            .where(AuditEvent.consent_ref == encounter.consent_ref)
            .order_by(AuditEvent.ts, AuditEvent.id)
        )
    ).scalars().all()
    return [
        {
            "id": e.id,
            "ts": e.ts.isoformat(),
            "actor": e.actor,
            "actorRole": e.actor_role,
            "purposeOfUse": e.purpose_of_use,
            "action": e.action,
            "outcome": e.outcome,
            "modelName": e.model_name,
        }
        for e in rows
    ]


async def provenance_completeness(db: AsyncSession, encounter: Encounter) -> dict[str, Any]:
    """Invariant 2, checked live rather than assumed: does every fact have a source?

    A fact passes if it carries at least one `SourceEvidence` row, OR its `state` is one of
    the recognised absences. Anything else is an offender — a fact with neither a source nor
    a reason for having none, which `record_fact` should make unreachable but this checks
    rather than trusts.
    """
    facts = (
        await db.execute(
            select(ClinicalFactRecord).where(ClinicalFactRecord.encounter_id == encounter.id)
        )
    ).scalars().all()

    offenders: list[dict[str, Any]] = []
    with_evidence = 0
    for fact in facts:
        has_evidence = (
            await db.execute(
                select(SourceEvidence.id).where(SourceEvidence.fact_id == fact.id).limit(1)
            )
        ).scalar() is not None
        if has_evidence:
            with_evidence += 1
        elif fact.state not in ABSENCE_OK_WITHOUT_EVIDENCE:
            offenders.append(
                {"factRef": fact.fact_ref, "path": fact.path, "state": fact.state}
            )

    return {
        "totalFacts": len(facts),
        "withEvidence": with_evidence,
        "withExplicitAbsence": len(facts) - with_evidence - len(offenders),
        "offenders": offenders,
        "complete": not offenders,
    }


async def no_assessment_claim_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the SAME scanner that gates every outbound response, but to show, not to raise.

    Two call sites reading one definition of "assessment-shaped" is the point: this cannot
    drift from what actually protects a live request, because it is the same function.
    """
    offenders = scan_for_assessment_language(payload)
    return {
        "clean": not offenders,
        "offenders": [{"field": key, "path": trail} for key, trail in offenders],
    }


@dataclass(slots=True)
class TamperDemo:
    available: bool
    events_in_demo: int = 0
    tampered_event_id: int | None = None
    tampered_field: str | None = None
    original_value: str | None = None
    corrupted_value: str | None = None
    detected: bool = False
    first_broken_index: int | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "eventsInDemo": self.events_in_demo,
            "tamperedEventId": self.tampered_event_id,
            "tamperedField": self.tampered_field,
            "originalValue": self.original_value,
            "corruptedValue": self.corrupted_value,
            "detected": self.detected,
            "firstBrokenIndex": self.first_broken_index,
            "note": self.note,
        }


async def tamper_demonstration(db: AsyncSession) -> TamperDemo:
    """Corrupt one event's content — in memory, in a copy — and show the chain catches it.

    ⛔ THE REAL TABLE IS NEVER AT RISK, BY CONSTRUCTION, NOT BY DISCIPLINE. `row_payload(r)`
    only reads attributes off the loaded ORM object and returns a fresh dict; nothing here
    ever assigns back onto `r`. That distinction matters: an ORM instance loaded through this
    session is tracked by SQLAlchemy's unit of work, and mutating one of its attributes in
    place would mark it dirty — invisible until the next `commit()` on this session, at which
    point the corruption would reach the real table. Reading into plain dicts up front makes
    that class of mistake structurally impossible rather than merely avoided.

    `tests/test_auditor_role.py::test_the_tamper_demo_never_touches_the_real_table` proves the
    row count and every stored hash are byte-identical before and after calling this.
    """
    rows = (await db.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars().all()
    if len(rows) < 2:
        return TamperDemo(
            available=False,
            note="Not enough audit history yet to demonstrate a tamper. Run through the "
            "kiosk once, then try again.",
        )

    # Plain dicts from here on. `payload` is `row_payload(r)` — read-only access to `r` — and
    # every subsequent line operates on the dict, never on `r` itself.
    copies: list[dict[str, Any]] = [
        {"id": r.id, "hash": r.hash, "prev_hash": r.prev_hash, "payload": row_payload(r)}
        for r in rows
    ]

    target = len(copies) // 2
    target_payload: dict[str, Any] = copies[target]["payload"]
    original: str = target_payload["action"]
    corrupted = "summary.commit" if original != "summary.commit" else "audit.verify"
    copies[target] = {
        **copies[target],
        "payload": {**target_payload, "action": corrupted},
    }

    prev = GENESIS_HASH
    first_broken: int | None = None
    for index, copy in enumerate(copies):
        if copy["prev_hash"] != prev:
            first_broken = index
            break
        if compute_hash(prev, copy["payload"]) != copy["hash"]:
            first_broken = index
            break
        prev = copy["hash"]

    return TamperDemo(
        available=True,
        events_in_demo=len(copies),
        tampered_event_id=int(copies[target]["id"]),
        tampered_field="action",
        original_value=original,
        corrupted_value=corrupted,
        detected=first_broken is not None,
        first_broken_index=first_broken,
        note=(
            "Ran on an in-memory copy of the log. The real audit_event table was only read, "
            "never written — this call cannot corrupt anything."
        ),
    )


async def full_review(db: AsyncSession, encounter: Encounter) -> dict[str, Any]:
    """Everything one auditor screen needs for one encounter, in a single read."""
    chain = await verify_chain(db)
    return {
        "encounterRef": encounter.encounter_ref,
        "occurredOn": encounter.occurred_at.date().isoformat(),
        "confirmedBy": encounter.confirmed_by,
        "consentRef": encounter.consent_ref,
        "chain": {**chain.to_dict(), "totalEvents": await count_events(db)},
        "trail": await audit_trail_for_encounter(db, encounter),
        "provenance": await provenance_completeness(db, encounter),
    }

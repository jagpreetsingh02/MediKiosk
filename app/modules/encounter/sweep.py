"""Expiring guest records, and everything that hangs off them.

WHY THIS EXISTS. Guest mode writes real rows into the real schema, and only an explicit Reset
removed them. Every judge who pressed Try Demo left a patient with six encounters, its facts,
its evidence and its documents behind — permanently, on a free-tier database with a hard
storage cap. That is a slow leak with a definite end date.

⛔ `DELETE FROM patient` IS NOT ENOUGH, and the schema is what says so.

Most of the record does cascade: encounter, clinical_fact, source_evidence, document_record,
extracted_entity, medication_event, observation_event, timeline_event, physician_decision,
red_flag_event, contradiction_record, report_snapshot, patient_identifier — all ON DELETE
CASCADE from patient or encounter.

THREE TABLES DO NOT, because they belong to the CAPTURE side and are keyed by `session_ref`
rather than by a foreign key to the patient:

    consent_record      the proof consent was given
    intake_session      the capture session itself
    submitted_bundle    what was pushed to the stub HIS

A guest who actually runs an intake creates all three. Deleting only the patient leaves them
orphaned — rows referencing a session whose encounter no longer exists, invisible to every
join and impossible to attribute. So the sweep walks
`encounter.source_session_ref` first and clears them explicitly.

⛔ AUDIT EVENTS ARE DELIBERATELY NOT DELETED. `audit_event` is a HASH-CHAINED log (Invariant
6): each row carries the hash of the one before it, and `GET /api/v1/audit/verify` walks the
chain. Removing entries from the middle breaks verification for every entry after them —
turning a tamper-evident log into one that reports tampering. The rows hold references and
action names, not clinical content, and a demo session's audit trail is exactly the kind of
thing an auditor should still be able to see. Retention beats tidiness here.

NEVER TOUCHES A CLINICAL RECORD. Every statement is scoped by `is_synthetic = true` AND the
`pat_guest_` prefix — two independent conditions, because this deletes cascading rows and the
cost of being wrong is unrecoverable. `tests/test_guest_sweep.py` asserts a mislabelled real
patient still cannot be swept.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.durable import Encounter, Patient
from app.db.models import ConsentRecord, IntakeSession, SubmittedBundle
from app.modules.encounter.guest import GUEST_PREFIX

log = get_logger(__name__)


def _cutoff(hours: float | None = None) -> datetime:
    ttl = settings.guest_ttl_hours if hours is None else hours
    return datetime.now(UTC) - timedelta(hours=ttl)


def _guest_filter():
    """TWO independent conditions, deliberately.

    `is_synthetic` is the cohort marker and `pat_guest_` is the ref the creator writes. Either
    alone would be enough in a correct database; requiring both means a single corrupted
    column cannot widen a cascading delete to a clinical record.
    """
    return (Patient.is_synthetic.is_(True), Patient.patient_ref.like(f"{GUEST_PREFIX}%"))


async def expired_guests(db: AsyncSession, *, hours: float | None = None) -> list[Patient]:
    return list(
        (
            await db.execute(
                select(Patient).where(*_guest_filter(), Patient.created_at < _cutoff(hours))
            )
        )
        .scalars()
        .all()
    )


async def purge_guest(db: AsyncSession, patient: Patient) -> dict[str, int]:
    """Delete one guest patient and everything attributable to it. The caller commits.

    Refuses anything that is not unambiguously a guest record, rather than trusting the
    caller to have filtered — this is a cascading delete and the guard belongs next to the
    statement that does the damage.
    """
    if not patient.is_synthetic or not patient.patient_ref.startswith(GUEST_PREFIX):
        raise ValueError(
            f"refusing to sweep {patient.patient_ref!r}: not a guest record "
            f"(is_synthetic={patient.is_synthetic})"
        )

    # The capture-side rows, found through the sessions this patient's encounters came from.
    session_refs = [
        ref
        for ref in (
            await db.execute(
                select(Encounter.source_session_ref).where(
                    Encounter.patient_id == patient.id,
                    Encounter.source_session_ref.is_not(None),
                )
            )
        )
        .scalars()
        .all()
        if ref
    ]

    removed: dict[str, int] = {}
    if session_refs:
        for model, name in (
            (ConsentRecord, "consent_record"),
            (IntakeSession, "intake_session"),
            (SubmittedBundle, "submitted_bundle"),
        ):
            result = await db.execute(
                delete(model).where(model.session_ref.in_(session_refs))
            )
            # CursorResult at runtime; the async Result stub does not expose rowcount.
            removed[name] = int(getattr(result, "rowcount", 0) or 0)

    # Everything else goes with the patient, by ON DELETE CASCADE.
    result = await db.execute(delete(Patient).where(Patient.id == patient.id))
    removed["patient"] = int(getattr(result, "rowcount", 0) or 0)
    await db.flush()
    return removed


async def sweep(
    db: AsyncSession, *, hours: float | None = None, dry_run: bool = False
) -> dict[str, Any]:
    """Delete every guest record older than the TTL. The caller commits."""
    ttl = settings.guest_ttl_hours if hours is None else hours
    victims = await expired_guests(db, hours=hours)

    if dry_run:
        return {
            "dryRun": True,
            "ttlHours": ttl,
            "cutoff": _cutoff(hours).isoformat(),
            "wouldRemove": [p.patient_ref for p in victims],
            "count": len(victims),
        }

    totals: dict[str, int] = {}
    swept: list[str] = []
    for patient in victims:
        ref = patient.patient_ref
        for table, n in (await purge_guest(db, patient)).items():
            totals[table] = totals.get(table, 0) + n
        swept.append(ref)

    if swept:
        log.info("guest.swept", count=len(swept), ttlHours=ttl, removed=totals)
    return {
        "dryRun": False,
        "ttlHours": ttl,
        "cutoff": _cutoff(hours).isoformat(),
        "swept": swept,
        "count": len(swept),
        "rowsRemoved": totals,
    }


async def sweep_on_create(db: AsyncSession) -> None:
    """A LAZY SWEEP, run when a new guest is created.

    Chosen over a scheduled job because this deployment has no scheduler and a cron service on
    the free tier is another thing to keep alive and another thing to forget. Guest creation is
    the one moment guest records are definitely being made, which makes it the natural place to
    clear the old ones — and it costs one indexed query when nothing has expired.

    Never raises: a failure to tidy up must not stop somebody starting a demo.
    """
    try:
        result = await sweep(db)
        if result["count"]:
            log.info("guest.lazy_sweep", **{k: result[k] for k in ("count", "rowsRemoved")})
    except Exception as exc:  # noqa: BLE001 - see the docstring
        log.warning("guest.lazy_sweep_failed", error=str(exc)[:200])


async def orphan_report(db: AsyncSession) -> dict[str, int]:
    """Capture-side rows whose owning encounter no longer exists.

    Used by the sweep test to prove nothing is left behind, and useful on its own: a non-zero
    count here means something deleted a patient without clearing the session rows.
    """
    live = select(Encounter.source_session_ref).where(Encounter.source_session_ref.is_not(None))
    out: dict[str, int] = {}
    for model, name in (
        (ConsentRecord, "consent_record"),
        (IntakeSession, "intake_session"),
        (SubmittedBundle, "submitted_bundle"),
    ):
        count = (
            await db.execute(
                select(func.count())
                .select_from(model)
                .where(model.session_ref.not_in(live))
            )
        ).scalar()
        out[name] = int(count or 0)
    return out

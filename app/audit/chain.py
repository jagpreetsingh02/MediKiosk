"""Append-only, hash-chained audit log. **Ported from SIH 25026 `app/audit/chain.py`.**

Changes on the way across (docs/PORTED.md): three columns added — `model_name`,
`model_version`, `prompt_hash` — so Invariant 6's "every AI call is written to the audit log"
is a property of the schema rather than of a convention; and the forbidden-key set widened to
cover the free-text clinical fields MediKiosk handles that the terminology service never saw.

Each row stores `prev_hash` and its own `hash` over `prev_hash + canonical(row)`. Any edit to
a historical row breaks every hash after it, and `/api/v1/audit/verify` reports the first
broken index.

**Privacy:** we record the search term, the actor, the purpose of use and a consent
*reference*. We never write bundle contents, patient names, or any identifier beyond the ABHA
reference the caller presented.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent

GENESIS_HASH = "0" * 64

#: Keys that must never reach an audit row, whatever a caller sends.
FORBIDDEN_KEYS = frozenset(
    {
        "name", "patient", "patientName", "birthDate", "address", "telecom",
        "identifier", "entry", "resource", "contained", "photo", "gender",
        # MediKiosk additions: this service handles narrative, so the blast radius is wider.
        "verbatim", "verbatim_translated", "transcript", "utterance", "value", "text",
        "chief_complaint", "symptom", "medication", "note", "ocr_text", "summary",
    }
)


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, row: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(row)).encode("utf-8")).hexdigest()


def scrub(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop anything that looks like patient content before it can be persisted."""
    if not payload:
        return payload
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key in FORBIDDEN_KEYS:
            clean[key] = "<redacted>"
        elif isinstance(value, dict):
            clean[key] = scrub(value)
        elif isinstance(value, list):
            clean[key] = f"<{len(value)} item(s)>"
        else:
            clean[key] = value
    return clean


def canonical_ts(value: Any) -> str:
    """Timestamps must hash identically before and after a database round-trip.

    SQLite drops the timezone on read, PostgreSQL keeps it. Both are normalised to naive UTC
    with microsecond precision so the chain verifies on either backend.
    """
    if isinstance(value, datetime):
        as_utc = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return as_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return str(value)


def row_payload(event: AuditEvent) -> dict[str, Any]:
    """The exact fields covered by the hash. Order-independent (canonical JSON sorts keys)."""
    return {
        "ts": canonical_ts(event.ts),
        "actor": event.actor,
        "actor_role": event.actor_role,
        "purpose_of_use": event.purpose_of_use,
        "abha_ref": event.abha_ref,
        "consent_ref": event.consent_ref,
        "action": event.action,
        "request_summary": event.request_summary,
        "response_summary": event.response_summary,
        "versions_used": event.versions_used,
        "outcome": event.outcome,
        "model_name": event.model_name,
        "model_version": event.model_version,
        "prompt_hash": event.prompt_hash,
    }


async def head_hash(session: AsyncSession) -> str:
    row = (
        (await session.execute(select(AuditEvent).order_by(desc(AuditEvent.id)).limit(1)))
        .scalars()
        .first()
    )
    return row.hash if row else GENESIS_HASH


async def record(
    session: AsyncSession,
    *,
    actor: str,
    actor_role: str,
    purpose_of_use: str,
    action: str,
    request_summary: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None,
    versions_used: dict[str, Any] | None = None,
    abha_ref: str | None = None,
    consent_ref: str | None = None,
    outcome: str = "success",
    model_name: str | None = None,
    model_version: str | None = None,
    prompt_hash: str | None = None,
) -> AuditEvent:
    prev = await head_hash(session)
    event = AuditEvent(
        prev_hash=prev,
        hash="",
        ts=datetime.now(UTC),
        actor=actor,
        actor_role=actor_role,
        purpose_of_use=purpose_of_use,
        abha_ref=abha_ref,
        consent_ref=consent_ref,
        action=action,
        request_summary=scrub(request_summary),
        response_summary=scrub(response_summary),
        versions_used=versions_used,
        outcome=outcome,
        model_name=model_name,
        model_version=model_version,
        prompt_hash=prompt_hash,
    )
    event.hash = compute_hash(prev, row_payload(event))
    session.add(event)
    await session.flush()
    return event


@dataclass(slots=True)
class ChainVerification:
    intact: bool
    checked: int
    first_broken_index: int | None = None
    first_broken_id: int | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intact": self.intact,
            "eventsChecked": self.checked,
            "firstBrokenIndex": self.first_broken_index,
            "firstBrokenEventId": self.first_broken_id,
            "detail": self.detail,
        }


async def verify_chain(session: AsyncSession) -> ChainVerification:
    """Walk the chain from genesis. Reports the first index where it breaks."""
    rows = (
        (await session.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars().all()
    )
    prev = GENESIS_HASH
    for index, event in enumerate(rows):
        if event.prev_hash != prev:
            return ChainVerification(
                intact=False, checked=index, first_broken_index=index, first_broken_id=event.id,
                detail=(
                    f"Event {event.id} declares prev_hash {event.prev_hash[:12]}… but the "
                    f"previous event hashes to {prev[:12]}…: a row was inserted or removed."
                ),
            )
        expected = compute_hash(prev, row_payload(event))
        if expected != event.hash:
            return ChainVerification(
                intact=False, checked=index, first_broken_index=index, first_broken_id=event.id,
                detail=(
                    f"Event {event.id} content does not match its stored hash: the row was "
                    "modified after it was written."
                ),
            )
        prev = event.hash
    return ChainVerification(intact=True, checked=len(rows))


async def count_events(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(AuditEvent.id)))).scalar_one())


def prompt_fingerprint(prompt: str) -> str:
    """SHA-256 of the exact prompt text. The prompt itself is never stored — it contains
    patient narrative — but the hash proves which prompt produced which output."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


async def record_ai_call(
    session: AsyncSession,
    *,
    actor: str,
    actor_role: str,
    action: str,
    model_name: str,
    model_version: str,
    prompt: str,
    abha_ref: str | None = None,
    consent_ref: str | None = None,
    outcome: str = "success",
    response_summary: dict[str, Any] | None = None,
) -> AuditEvent:
    """Invariant 6: no LLM call happens anywhere without a row landing here."""
    return await record(
        session,
        actor=actor,
        actor_role=actor_role,
        purpose_of_use="TREATMENT",
        action=action,
        abha_ref=abha_ref,
        consent_ref=consent_ref,
        response_summary=response_summary,
        outcome=outcome,
        model_name=model_name,
        model_version=model_version,
        prompt_hash=prompt_fingerprint(prompt),
    )

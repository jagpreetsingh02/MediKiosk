"""Session lifecycle and teardown — Invariant 6, second half. **Sessions die.**

Two stores, one interface. Redis when it is reachable, an in-process dict when it is not, so
a dead container costs you the demo's multi-worker capability and not the demo. The fallback
is loud in the logs and reported in `/about`; it is never silently assumed.

Purge is the point of this module. `purge()` deletes the session's clinical state from both
the cache and the database, and it is called from three places: on submit, on TTL expiry
(the sweeper), and on explicit patient revocation. What survives a purge is deliberate and
short: the consent record (proving consent was given is a legal requirement), the audit chain
(same), and any bundle a physician actually committed. Nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import SessionExpired
from app.core.logging import get_logger
from app.db.models import IntakeSession, RedFlagProposal, SessionDocument, SessionFact

log = get_logger(__name__)


class SessionStore(Protocol):
    kind: str

    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def put(self, key: str, value: dict[str, Any], ttl: int) -> None: ...
    async def drop(self, key: str) -> None: ...
    async def keys(self) -> list[str]: ...


class MemorySessionStore:
    """Single-process fallback. Correct for the demo, wrong for production, and says so."""

    kind = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[dict[str, Any], datetime]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires = entry
        if datetime.now(UTC) >= expires:
            del self._data[key]
            return None
        return value

    async def put(self, key: str, value: dict[str, Any], ttl: int) -> None:
        self._data[key] = (value, datetime.now(UTC) + timedelta(seconds=ttl))

    async def drop(self, key: str) -> None:
        self._data.pop(key, None)

    async def keys(self) -> list[str]:
        now = datetime.now(UTC)
        return [k for k, (_, exp) in self._data.items() if exp > now]


class RedisSessionStore:
    """Redis with a real TTL, so an abandoned session expires even if nothing sweeps."""

    kind = "redis"

    def __init__(self, client: Any) -> None:
        self._redis = client

    async def get(self, key: str) -> dict[str, Any] | None:
        raw = await self._redis.get(f"medikiosk:session:{key}")
        return json.loads(raw) if raw else None

    async def put(self, key: str, value: dict[str, Any], ttl: int) -> None:
        await self._redis.set(f"medikiosk:session:{key}", json.dumps(value), ex=ttl)

    async def drop(self, key: str) -> None:
        await self._redis.delete(f"medikiosk:session:{key}")

    async def keys(self) -> list[str]:
        found = await self._redis.keys("medikiosk:session:*")
        return [
            k.decode().split(":")[-1] if isinstance(k, bytes) else k.split(":")[-1] for k in found
        ]


_store: SessionStore | None = None


async def get_store() -> SessionStore:
    """Resolve the store once. Redis if it answers a ping, memory otherwise."""
    global _store
    if _store is not None:
        return _store
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(settings.redis_url, socket_connect_timeout=1.0)
        await client.ping()
        _store = RedisSessionStore(client)
        log.info("session.store", kind="redis", url=settings.redis_url)
    except Exception as exc:
        if not settings.session_store_allow_memory_fallback:
            raise
        _store = MemorySessionStore()
        log.warning(
            "session.store_fallback",
            kind="memory",
            reason=str(exc)[:120],
            note="single-process only; never use this configuration in production",
        )
    return _store


def reset_store() -> None:
    """Test hook. Never called by the application."""
    global _store
    _store = None


@dataclass(slots=True)
class PurgeResult:
    session_ref: str
    facts_deleted: int
    documents_deleted: int
    proposals_deleted: int
    cache_cleared: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionRef": self.session_ref,
            "factsDeleted": self.facts_deleted,
            "documentsDeleted": self.documents_deleted,
            "proposalsDeleted": self.proposals_deleted,
            "cacheCleared": self.cache_cleared,
            "reason": self.reason,
            "survives": [
                "consent_record (proving consent was given is a legal requirement)",
                "audit_event (the hash chain must not have holes)",
                "submitted_bundle (only if a physician committed it)",
            ],
        }


async def purge(db: AsyncSession, session_ref: str, *, reason: str = "submit") -> PurgeResult:
    """Delete every trace of the patient's session data. Idempotent."""
    store = await get_store()
    await store.drop(session_ref)

    row = (
        (await db.execute(select(IntakeSession).where(IntakeSession.session_ref == session_ref)))
        .scalars()
        .first()
    )

    if row is None:
        return PurgeResult(session_ref, 0, 0, 0, True, reason)

    facts = len(
        (await db.execute(select(SessionFact.id).where(SessionFact.session_id == row.id)))
        .scalars()
        .all()
    )
    documents = len(
        (await db.execute(select(SessionDocument.id).where(SessionDocument.session_id == row.id)))
        .scalars()
        .all()
    )
    proposals = len(
        (await db.execute(select(RedFlagProposal.id).where(RedFlagProposal.session_id == row.id)))
        .scalars()
        .all()
    )

    await db.execute(delete(SessionFact).where(SessionFact.session_id == row.id))
    await db.execute(delete(SessionDocument).where(SessionDocument.session_id == row.id))
    await db.execute(delete(RedFlagProposal).where(RedFlagProposal.session_id == row.id))

    row.purged_at = datetime.now(UTC)
    row.status = "purged"
    # The dialogue state carries the transcript. It goes too.
    row.state_json = None
    await db.flush()

    log.info(
        "session.purged",
        session=session_ref,
        reason=reason,
        facts=facts,
        documents=documents,
        proposals=proposals,
    )
    return PurgeResult(session_ref, facts, documents, proposals, True, reason)


async def sweep_expired(db: AsyncSession) -> list[PurgeResult]:
    """Purge every session past its TTL. Called on a timer and on startup."""
    now = datetime.now(UTC)
    rows = (
        (
            await db.execute(
                select(IntakeSession).where(
                    IntakeSession.purged_at.is_(None),
                    IntakeSession.expires_at.is_not(None),
                    IntakeSession.expires_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    results = [await purge(db, row.session_ref, reason="ttl_expiry") for row in rows]
    if results:
        log.info("session.sweep", purged=len(results))
    return results


async def assert_live(db: AsyncSession, session_ref: str) -> IntakeSession:
    """Load a session, refusing an expired or purged one rather than resurrecting it."""
    row = (
        (await db.execute(select(IntakeSession).where(IntakeSession.session_ref == session_ref)))
        .scalars()
        .first()
    )
    if row is None:
        raise SessionExpired(f"Session {session_ref} does not exist.")
    if row.purged_at is not None:
        raise SessionExpired(
            f"Session {session_ref} has been purged. Session data is deleted on submit and "
            "on TTL expiry, and is not recoverable — that is the design, not a fault."
        )
    if row.expires_at is not None and datetime.now(UTC) >= row.expires_at.replace(
        tzinfo=row.expires_at.tzinfo or UTC
    ):
        await purge(db, session_ref, reason="ttl_expiry")
        raise SessionExpired(f"Session {session_ref} expired and has been purged.")
    return row

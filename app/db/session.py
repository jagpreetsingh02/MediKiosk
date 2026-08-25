"""Async engine and session factory. One engine per process."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

log = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    # Second of the two enforcement points (the other is startup). A caller that builds an
    # engine without going through `lifespan` — a script, the eval runner, a REPL — must not
    # be able to reach a local file either.
    settings.require_postgres()

    kwargs: dict[str, object] = {"echo": settings.db_echo, "future": True}
    if settings.is_sqlite:
        # SQLite has no pool semantics worth configuring, and file locking bites under the
        # default pool when the eval runner and the API share a database file.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # REMOTE POSTGRES IS A NETWORK, AND THE NUMBERS ARE NOT SMALL.
        #
        # Measured against Supabase from a developer laptop: 118 ms for a single query on
        # a warm pooled connection, and 824 ms to open a new one (TLS handshake plus auth
        # across the internet). A request that makes eight round-trips therefore costs
        # about a second, and paying the 824 ms again mid-demo because the pool was empty
        # is the difference between "responsive" and "broken".
        #
        # So the pool is sized to keep connections warm rather than to save memory, and
        # recycled well inside the provider's idle timeout so a checkout rarely finds a
        # dead socket. `pool_pre_ping` stays: it costs one round-trip, and the failure it
        # prevents — a stale connection surfacing as a 500 mid-interview — is far worse
        # than 118 ms.
        kwargs["pool_pre_ping"] = True
        # THE CEILING IS PER PROCESS, AND THE BUDGET IS NOT LARGE.
        #
        # Supabase gives this project `max_connections = 60`, three of which are reserved
        # for superusers and about five of which Supabase itself consumes (PostgREST,
        # pg_cron, pg_net, the metrics exporter). That leaves roughly 52 for the
        # application. At the previous 10 + 10 a single process held 16 idle connections
        # and could claim 20, so three instances — a developer, a demo, a stale process
        # nobody noticed — exhausted the budget and new connections began timing out
        # during TLS/auth. That is not a hypothetical: it is what produced the [Errno 60]
        # startup crash on the direct endpoint.
        #
        # 5 + 5 gives a hard ceiling of 10 per process, so five concurrent instances still
        # fit. The kiosk serves one patient at a time and the workspace one clinician, so
        # five warm connections is ample for either.
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 5
        kwargs["pool_recycle"] = 280
        kwargs["pool_timeout"] = 30

        # A BOUNDED CONNECT, so a wrong network is diagnosed in seconds not minutes.
        #
        # Without this each attempt waits out the OS TCP timeout — about 60 seconds — so the
        # five retries below took roughly five minutes to reach the fatal error. Measured
        # live on a network that blocks port 5432 outbound. Ten seconds is far longer than a
        # healthy connect (which is ~800ms cold, and ~140ms warm) and short enough that the
        # whole retry ladder resolves in well under a minute.
        connect_args: dict[str, object] = {"timeout": 10.0}

        if settings.is_transaction_pooler:
            # TRANSACTION-MODE POOLING CANNOT HOLD A PREPARED STATEMENT.
            #
            # It hands a different backend connection to every transaction, so a statement
            # prepared in one is gone by the next. asyncpg prepares and caches every query
            # by default, which surfaces as `InvalidSQLStatementNameError: prepared
            # statement "__asyncpg_stmt_1__" does not exist` — intermittently, under load,
            # which is the worst way to find out.
            #
            # SESSION mode (the runtime default) does not need this: one backend per client
            # for the life of the connection, so prepared statements behave normally. This
            # branch exists only for a deployment that deliberately chooses 6543.
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0

        kwargs["connect_args"] = connect_args
    engine = create_async_engine(settings.database_url, **kwargs)  # type: ignore[arg-type]
    if not settings.is_sqlite:
        _stamp_every_connection(engine)
    return engine


#: How long the SERVER waits before terminating one of our idle connections.
#:
#: This is the only mechanism that can reap an orphan. `pool_recycle` is client-side and
#: only fires when a connection is checked OUT of the pool, so it is powerless over a
#: connection whose process is gone — which is how a connection was observed sitting idle
#: for 87041 seconds (24 hours), holding a slot in a 60-connection budget.
IDLE_SESSION_TIMEOUT = "10min"


def _stamp_every_connection(engine: AsyncEngine) -> None:
    """Set `idle_session_timeout` and a real `application_name` on each new connection.

    WHY NOT `ALTER ROLE postgres SET idle_session_timeout` — the obvious answer, and the
    wrong one here. This application connects as `postgres`, but so does Supabase's own
    `pg_net` extension, and one of the long-idle connections observed belongs to it. A role
    setting would reap Supabase's infrastructure along with our orphans. The blast radius
    is not ours to take.

    WHY NOT `server_settings` on connect — tried first, and it silently does not work
    through the pooler: Supavisor swallows startup parameters, so `idle_session_timeout`
    came back as 0 and `application_name` as "Supavisor". A `SET` issued after the
    connection is established does stick, because session mode gives us one backend for the
    life of the connection.

    The `application_name` is not cosmetic either. Our connections previously appeared in
    `pg_stat_activity` with an empty name, indistinguishable from anything else on the
    `postgres` role, which is a large part of why the connection budget was hard to reason
    about in the first place.
    """
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        # asyncpg's DBAPI shim exposes the raw connection; `.exec_driver_sql` is not
        # available on a raw connect event, so the driver's own cursor is used.
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"set idle_session_timeout = '{IDLE_SESSION_TIMEOUT}'")
            cursor.execute(f"set application_name = '{settings.app_name}-api'")
        finally:
            cursor.close()


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits on clean exit, rolls back on any exception."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all() -> None:
    """Create tables directly. TESTS ONLY — Alembic owns every real schema.

    This used to run for any SQLite database, which meant a mis-set DATABASE_URL produced a
    fully-formed local schema and an application that looked completely healthy. It is now
    unreachable outside the test suite.
    """
    if not settings.testing:
        raise RuntimeError(
            "create_all() is test-only. A real schema is built by `alembic upgrade head`; "
            "calling this against Postgres papers over a missing migration."
        )
    from app.db import durable, models  # noqa: F401  (imports register the mappers)

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


from app.db.base import Base  # noqa: E402  (circular-safe: Base has no app imports)


async def wait_for_database(attempts: int = 5, base_delay: float = 0.75) -> None:
    """Open one connection at startup, retrying with exponential backoff.

    TWO JOBS, AND THE SECOND IS THE ONE THAT SHOWS UP IN A DEMO.

    First, it fails loudly and by name. A database that is briefly unreachable used to take
    the whole process down on the first attempt with a bare `TimeoutError [Errno 60]` and no
    indication of which endpoint had not answered. On a venue network nobody controls, one
    transient failure should not be the difference between a working demo and a dead one.

    Second, it pays the cold-connect cost once, here, instead of making the first real
    request pay it. Opening a connection to Supabase costs roughly 800 ms of TCP, TLS and
    auth; without this the first patient to touch the kiosk waits for it. The connection is
    returned to the pool, so the request that follows finds it warm.

    Backoff is 0.75s, 1.5s, 3s, 6s — about eleven seconds of patience in total, which is
    long enough to ride out a Wi-Fi handover and short enough that a genuinely wrong
    endpoint is reported quickly.
    """
    engine = get_engine()
    last: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
            if attempt > 1:
                log.info("startup.database.recovered", attempt=attempt)
            return
        except Exception as exc:  # noqa: BLE001 — re-raised below with context
            last = exc
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            log.warning(
                "startup.database.retry",
                attempt=attempt,
                of=attempts,
                retry_in_s=round(delay, 2),
                host=settings.database_host,
                error=type(exc).__name__,
            )
            await asyncio.sleep(delay)

    raise RuntimeError(
        f"Could not reach the database at {settings.database_host} "
        f"({settings.database_backend}) after {attempts} attempts. "
        f"Last error: {type(last).__name__}: {last}. "
        "If this is the direct endpoint (db.<ref>.supabase.co) note that it is IPv6-only — "
        "on an IPv4-only network it will never connect. Use the session-mode pooler "
        "(aws-N-<region>.pooler.supabase.com:5432) for the application runtime; see "
        "docs/SUPABASE.md."
    ) from last

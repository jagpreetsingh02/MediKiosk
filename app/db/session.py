"""Async engine and session factory. One engine per process."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


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
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 10
        kwargs["pool_recycle"] = 280
        kwargs["pool_timeout"] = 30

        if settings.is_pooled:
            # SUPABASE'S POOLER CANNOT HOLD A PREPARED STATEMENT.
            #
            # The transaction-mode pooler hands a different backend connection to every
            # transaction, so a statement prepared in one is gone by the next. asyncpg
            # prepares and caches every query by default, which surfaces as
            # `InvalidSQLStatementNameError: prepared statement "__asyncpg_stmt_1__" does
            # not exist` — intermittently, under load, which is the worst way to find out.
            #
            # Disabling the cache is what makes the pooler usable. Note this costs a parse
            # per statement, which is exactly why migrations use the direct endpoint
            # instead of paying it (see alembic/env.py).
            kwargs["connect_args"] = {
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            }
    return create_async_engine(settings.database_url, **kwargs)  # type: ignore[arg-type]


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

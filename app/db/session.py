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
    kwargs: dict[str, object] = {"echo": settings.db_echo, "future": True}
    if settings.is_sqlite:
        # SQLite has no pool semantics worth configuring, and file locking bites under the
        # default pool when the eval runner and the API share a database file.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
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
    """Create tables directly. Used by tests and by the one-command demo; Alembic owns prod."""
    from app.db import models  # noqa: F401  (import registers the mappers)

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


from app.db.base import Base  # noqa: E402  (circular-safe: Base has no app imports)

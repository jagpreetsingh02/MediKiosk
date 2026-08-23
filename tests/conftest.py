"""Shared fixtures. Every test runs on SQLite in memory: no Docker, no network, no Redis."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LLM_BACKEND", "offline")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
async def db_session() -> AsyncIterator:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.base import Base
    from app.db import models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def seeded_session(db_session):
    from app.terminology.store import seed_all

    await seed_all(db_session)
    await db_session.commit()
    return db_session


@pytest.fixture
def ledger():
    from app.contracts.record import FactLedger

    return FactLedger("sess_test", consent_scopes={"history", "documents", "voice"})


@pytest.fixture
def machine(ledger):
    from app.modules.dialogue.machine import DialogueMachine, DialogueState

    state = DialogueState(session_id="sess_test", language="en")
    return DialogueMachine(state, ledger)

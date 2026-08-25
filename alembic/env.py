"""Alembic environment. The URL comes from settings, never from alembic.ini."""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings

# Both halves of the schema, or Alembic silently emits half a database. `durable` was
# missing here, so the thirteen longitudinal tables — patient, encounter, clinical_fact and
# the rest — existed only because `create_all()` runs against SQLite at startup. On any real
# Postgres they would simply not have been created, and the patient memory would have been
# empty with nothing in the logs to say why.
from app.db import durable, models  # noqa: F401  (imports register the mappers)
from app.db.base import Base

# MIGRATIONS RUN AGAINST THE DIRECT ENDPOINT, NOT THE POOLER.
#
# Alembic's DDL and its version-table bookkeeping want a real session on one backend
# connection. Supabase's transaction-mode pooler hands out a different backend per
# transaction and cannot carry prepared statements between them, so a migration run through
# it fails partway with `prepared statement "__asyncpg_stmt_N__" does not exist` — after
# some DDL has already committed, which is the worst possible place to stop.
#
# `MIGRATION_DATABASE_URL` exists for the deployment where the app runs pooled: point the
# app at the pooler and this at the direct endpoint. When it is unset (the normal case, and
# the case on this machine, where the direct IPv6 endpoint is reachable) migrations use the
# same URL as the app.
MIGRATION_URL = os.environ.get("MIGRATION_DATABASE_URL") or settings.database_url

# The same Postgres-or-nothing rule the app enforces. Running migrations against a local
# SQLite file produces a perfectly migrated database that no deployment will ever read.
if not settings.testing and not MIGRATION_URL.startswith(
    ("postgresql", "postgres+", "postgres:")
):
    raise SystemExit(
        "Refusing to migrate: MIGRATION_DATABASE_URL / DATABASE_URL does not resolve to "
        "PostgreSQL. Set it to the Supabase DIRECT connection string (port 5432, not the "
        "6543 pooler) — see docs/SUPABASE.md."
    )

config = context.config
config.set_main_option("sqlalchemy.url", MIGRATION_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=MIGRATION_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())

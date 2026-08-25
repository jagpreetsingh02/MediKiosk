"""Migrations must describe the models. Both halves of them.

This is the test that would have caught the bug this file was written for: `alembic/env.py`
imported `app.db.models` and not `app.db.durable`, so `alembic upgrade head` built the capture
tables and none of the thirteen longitudinal ones. On SQLite nothing complained, because
`create_all()` runs at startup and quietly made them anyway. On any database not built by
`create_all()` — Supabase included — the entire patient memory would have been missing, with
nothing in the logs to say why.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _alembic(*args: str, db: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "DATABASE_URL": f"sqlite+aiosqlite:///{db}",
            # The sanctioned escape hatch, and the reason it exists. This test proves the
            # migrations build the whole schema, which it does against a throwaway SQLite
            # file so the suite needs no network. `alembic/env.py` refuses a non-Postgres
            # URL for exactly the reason this test guards against — a migration run against
            # the wrong database — so the test has to say out loud that it is the suite.
            "TESTING": "1",
            "HOME": str(Path.home()),
        },
        capture_output=True,
        text=True,
    )


def test_alembic_metadata_covers_both_halves_of_the_schema() -> None:
    """The import bug itself, pinned. `Base.metadata` must know the durable tables."""
    from app.db import durable, models  # noqa: F401
    from app.db.base import Base

    tables = set(Base.metadata.tables)
    capture = {"intake_session", "session_fact", "session_document", "consent_record"}
    longitudinal = {
        "patient",
        "patient_identifier",
        "encounter",
        "clinical_fact",
        "source_evidence",
        "document_record",
        "extracted_entity",
        "medication_event",
        "observation_event",
        "timeline_event",
        "contradiction_record",
        "red_flag_event",
        "physician_decision",
    }
    assert capture <= tables, f"capture tables missing: {sorted(capture - tables)}"
    assert longitudinal <= tables, f"durable tables missing: {sorted(longitudinal - tables)}"


def test_alembic_env_imports_the_durable_models() -> None:
    """A future edit that drops the import would silently empty the patient memory again."""
    source = (PROJECT_ROOT / "alembic" / "env.py").read_text()
    assert "durable" in source, (
        "alembic/env.py must import app.db.durable, or `alembic upgrade head` builds only "
        "the capture half of the schema"
    )


def test_migrations_build_the_whole_schema_and_reverse_cleanly(tmp_path) -> None:
    """`upgrade head` then `downgrade base` — on a database create_all() never touched."""
    db = tmp_path / "migrations.db"

    up = _alembic("upgrade", "head", db=db)
    assert up.returncode == 0, up.stderr

    import sqlite3

    with sqlite3.connect(db) as conn:
        built = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "patient" in built and "encounter" in built and "clinical_fact" in built, (
        f"migrations did not build the longitudinal schema; got {sorted(built)}"
    )

    down = _alembic("downgrade", "base", db=db)
    assert down.returncode == 0, down.stderr


def test_no_model_has_drifted_away_from_a_migration(tmp_path) -> None:
    """`alembic check`. A model changed without a revision fails the build, not the demo."""
    db = tmp_path / "drift.db"
    assert _alembic("upgrade", "head", db=db).returncode == 0

    check = _alembic("check", db=db)
    assert check.returncode == 0, (
        "A model has changed with no migration to match. Run:\n"
        "  alembic revision --autogenerate -m '<what changed>'\n\n" + check.stdout + check.stderr
    )


def test_the_rls_migration_does_not_assume_supabase_roles() -> None:
    """`anon` and `authenticated` exist on Supabase and nowhere else.

    Revoking from a role that does not exist is a hard error, so the first version of
    this migration aborted `alembic upgrade head` on every database except Supabase —
    a local Postgres, CI, a reviewer's container. Verified by actually running it
    against Postgres 16, where it failed with `role "anon" does not exist`.
    """
    source = (
        PROJECT_ROOT / "alembic" / "versions" / "fdb61bb8d5ef_lock_every_table_behind_rls.py"
    ).read_text()
    assert "pg_roles" in source, (
        "the RLS migration must check a role exists before revoking from it"
    )
    # The REVOKE must be conditional on what the probe found, never unconditional.
    assert "REVOKE ALL ON public.{table} FROM anon, authenticated" not in source


def test_rls_is_enabled_for_every_table_the_schema_owns() -> None:
    """The lockdown must not drift behind the schema: a table added without being
    listed here is a table published to the internet by PostgREST."""
    import importlib.util

    from app.db import durable, models  # noqa: F401
    from app.db.base import Base

    spec = importlib.util.spec_from_file_location(
        "rls_migration",
        PROJECT_ROOT / "alembic" / "versions" / "fdb61bb8d5ef_lock_every_table_behind_rls.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    locked = set(module.TABLES)
    owned = set(Base.metadata.tables)
    missing = owned - locked
    assert not missing, (
        f"these tables have no RLS lockdown and would be readable over PostgREST: "
        f"{sorted(missing)}"
    )

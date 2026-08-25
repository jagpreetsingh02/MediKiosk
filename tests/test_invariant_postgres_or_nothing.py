"""The database fallback cannot come back.

The recurring failure this file exists to prevent is not a crash. It is a *success*: the
application starts, the browser works, a whole consultation is recorded — into a local SQLite
file, while the Supabase tables everyone is watching stay empty. Nothing fails, nothing warns,
and the bug is visible only as absence. That failure mode has three separate causes and this
module pins the fix for each:

  1. `database_url` had a SQLite default, so a missing or misspelled DATABASE_URL still
     produced a working application.
  2. The Postgres check was opt-in, behind a REQUIRE_SUPABASE flag that defaulted to off.
  3. The check was skipped whenever `environment == "test"` — an ordinary config value that a
     developer could set in `.env` and disable the guard for their whole machine.

The tests below fail the build if any of the three returns. They deliberately assert on the
*absence* of a capability, which is the only way to test that something cannot happen.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


#: The environment keys that can make these tests pass for the wrong reason. `conftest.py`
#: sets TESTING=1 and a SQLite DATABASE_URL for the whole session — which is correct for
#: every other test and fatal here, because it is precisely the exemption under test.
_MASKED = ("TESTING", "DATABASE_URL", "ENVIRONMENT", "REQUIRE_SUPABASE")


@pytest.fixture(autouse=True)
def _unconfigured_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test here reasons about a *fresh* process, so the suite's own configuration
    has to be out of the way. Without this the tests assert nothing: `Settings` reads the
    real environment, finds the TESTING=1 that conftest set, and takes the early return."""
    for key in _MASKED:
        monkeypatch.delenv(key, raising=False)


def _settings(**overrides: object) -> Settings:
    """Settings built with neither `.env` nor the suite's environment, so the developer's
    real DATABASE_URL — a live Supabase URL — cannot make these pass by accident."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_there_is_no_database_url_default() -> None:
    """The single line that caused the bug. An unset DATABASE_URL must connect to nothing."""
    assert _settings().database_url == "", (
        "database_url has grown a default again. A default is what let a missing "
        "DATABASE_URL produce a working application writing to the wrong place."
    )


def test_missing_database_url_aborts() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        _settings().require_postgres()


def test_sqlite_is_refused_outside_the_test_suite() -> None:
    """The heart of it: a dev or demo run cannot reach SQLite, by any spelling."""
    for url in (
        "sqlite+aiosqlite:///./medikiosk.db",
        "sqlite+aiosqlite:///:memory:",
        "sqlite:///./medikiosk.db",
    ):
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            _settings(database_url=url).require_postgres()


def test_the_only_escape_hatch_is_the_testing_flag() -> None:
    """`TESTING=1` permits SQLite. Nothing else does — in particular not `environment`.

    The second assertion is the one that matters: the old guard exempted
    `environment == "test"`, so anyone who set that in `.env` silently disabled it.
    """
    _settings(database_url="sqlite+aiosqlite:///:memory:", testing=True).require_postgres()

    with pytest.raises(RuntimeError):
        _settings(
            database_url="sqlite+aiosqlite:///:memory:", environment="test"
        ).require_postgres()


def test_postgres_urls_are_accepted() -> None:
    for url in (
        "postgresql+asyncpg://u:p@db.example.supabase.co:5432/postgres",
        "postgresql+asyncpg://u:p@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
    ):
        _settings(database_url=url).require_postgres()


def test_pooled_connections_are_detected() -> None:
    """Whether we are on the pooler decides whether prepared statements must be disabled.

    Getting this wrong does not fail at startup — it fails intermittently under load with
    `prepared statement "__asyncpg_stmt_N__" does not exist`, which is a far more expensive
    way to learn the same fact.
    """
    direct = _settings(database_url="postgresql+asyncpg://u:p@db.x.supabase.co:5432/postgres")
    # 5432 on a pooler host is SESSION mode — the runtime's endpoint.
    pooled = _settings(
        database_url="postgresql+asyncpg://u:p@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    )
    assert not direct.is_pooled
    assert pooled.is_pooled
    assert "direct" in direct.database_backend
    assert "session mode" in pooled.database_backend

    # Session mode keeps prepared statements; only transaction mode must give them up.
    txn = _settings(
        database_url="postgresql+asyncpg://u:p@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
    )
    assert not pooled.is_transaction_pooler, "5432 is session mode, not transaction mode"
    assert txn.is_transaction_pooler
    assert "transaction mode" in txn.database_backend


def test_the_logged_host_never_carries_the_password() -> None:
    """Startup logs the host so it is obvious which database is live. It must not log more."""
    secret = "hunter2SUPERSECRET"
    s = _settings(
        database_url=f"postgresql+asyncpg://postgres:{secret}@db.x.supabase.co:5432/postgres"
    )
    assert s.database_host == "db.x.supabase.co:5432"
    assert secret not in s.database_host
    assert secret not in s.database_backend


def test_create_all_is_unreachable_outside_the_test_suite() -> None:
    """`create_all()` against a real database papers over a missing migration.

    It used to run for any SQLite URL, which is how a mis-set DATABASE_URL produced a
    fully-formed local schema and an application that looked completely healthy.
    """
    import asyncio

    from app.core import config as config_module
    from app.db.session import create_all

    original = config_module.settings.testing
    try:
        config_module.settings.testing = False
        with pytest.raises(RuntimeError, match="test-only"):
            asyncio.run(create_all())
    finally:
        config_module.settings.testing = original


def test_alembic_refuses_a_non_postgres_url() -> None:
    """Migrations against SQLite produce a perfectly migrated database nobody will read."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=PROJECT_ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "DATABASE_URL": "sqlite+aiosqlite:///./should-never-be-built.db",
            "HOME": str(Path.home()),
            # Deliberately NO TESTING=1 — this asserts the refusal, not the exemption.
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "alembic ran against SQLite without TESTING=1"
    assert "Refusing to migrate" in (result.stderr + result.stdout)
    assert not (PROJECT_ROOT / "should-never-be-built.db").exists()

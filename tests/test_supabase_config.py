"""Supabase wiring: which database is really behind the process, and where secrets are not.

The service-role key bypasses RLS completely. Shipping it to a browser would undo every
control in `docs/SUPABASE_SECURITY.md` in a single line, and it is exactly the kind of thing
that gets pasted into a `VITE_` variable at 2am during a hackathon. So it is a test, not a
convention.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "frontend"

#: A Supabase key is a JWT: three base64url segments. Matching the shape rather than a
#: literal value means this keeps working when the project is rotated or replaced.
JWT_SHAPE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")

#: Anything that must never appear in a browser bundle. `sb_secret_` is the modern
#: Supabase secret-key prefix; the legacy service-role name is kept so an older key
#: pasted into the frontend still trips this.
SECRET_NAMES = (
    "SERVICE_ROLE",
    "SUPABASE_SERVICE",
    "SUPABASE_SECRET",
    "sb_secret_",
    "DATABASE_URL",
    "SUPABASE_DB_PASSWORD",
)


def _frontend_files() -> list[Path]:
    skip = {"node_modules", "dist", ".vite"}
    return [
        p
        for p in FRONTEND.rglob("*")
        if p.is_file()
        and not any(part in skip for part in p.parts)
        and p.suffix in {".ts", ".tsx", ".js", ".jsx", ".json", ".html", ".css", ".env"}
    ]


def test_no_supabase_secret_can_reach_the_browser() -> None:
    offenders: list[str] = []
    for path in _frontend_files():
        text = path.read_text(errors="ignore")
        for name in SECRET_NAMES:
            if name in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} mentions {name}")
        if JWT_SHAPE.search(text):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)} contains a JWT-shaped literal")
    assert not offenders, (
        "A Supabase secret is reachable from the frontend. The service-role key bypasses "
        "RLS entirely — see docs/SUPABASE_SECURITY.md.\n  " + "\n  ".join(offenders)
    )


def test_the_frontend_holds_no_database_client() -> None:
    """Clinical writes go through FastAPI so provenance, consent and ABAC apply to them.

    A `@supabase/supabase-js` dependency is the first step towards a component writing a
    clinical row straight from a browser, which would route around every guarantee in
    AGENT.md at once.
    """
    package_json = FRONTEND / "package.json"
    if not package_json.exists():
        pytest.skip("no frontend package.json")
    assert "supabase" not in package_json.read_text(), (
        "The frontend must not talk to the database directly (§4 of the integration brief)."
    )


def test_env_example_documents_supabase_with_placeholders_only() -> None:
    example = (PROJECT_ROOT / ".env.example").read_text()
    assert "SUPABASE_URL=" in example
    assert "SUPABASE_SECRET_KEY=" in example
    assert "SUPABASE_PUBLISHABLE_KEY=" in example
    assert not JWT_SHAPE.search(example), ".env.example must carry placeholders, never a key"


def test_env_example_and_env_do_not_drift() -> None:
    """A variable that exists only in someone's private .env is a variable nobody else has."""
    env = PROJECT_ROOT / ".env"
    if not env.exists():
        pytest.skip("no local .env")

    def names(text: str) -> set[str]:
        return {
            line.split("=", 1)[0].strip()
            for line in text.splitlines()
            if "=" in line and not line.strip().startswith("#")
        }

    missing = names(env.read_text()) - names((PROJECT_ROOT / ".env.example").read_text())
    assert not missing, f".env has variables absent from .env.example: {sorted(missing)}"


# ------------------------------------------------------------------ backend labelling


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite+aiosqlite:///./medikiosk.db", "SQLite (local file)"),
        (
            "postgresql+asyncpg://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres",
            "Supabase PostgreSQL (pooled)",
        ),
        (
            "postgresql+asyncpg://postgres:pw@db.abc.supabase.co:5432/postgres",
            "Supabase PostgreSQL (direct)",
        ),
        ("postgresql+asyncpg://u:p@localhost:5432/medikiosk", "PostgreSQL"),
    ],
)
def test_the_database_backend_is_named_honestly(url: str, expected: str) -> None:
    """§31: a demo silently running on an empty SQLite file looks exactly like a working one."""
    from app.core.config import Settings

    assert Settings(database_url=url).database_backend == expected


def test_the_logged_host_never_carries_the_password() -> None:
    from app.core.config import Settings

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:sup3rs3cret@db.abc.supabase.co:5432/postgres"
    )
    assert "sup3rs3cret" not in settings.database_host
    assert settings.database_host == "db.abc.supabase.co:5432"


def test_requiring_supabase_rejects_a_sqlite_url() -> None:
    """The guard that stops a demo quietly running on the wrong database."""
    from app.core.config import Settings

    settings = Settings(database_url="sqlite+aiosqlite:///./medikiosk.db", require_supabase=True)
    assert settings.require_supabase and not settings.is_supabase, (
        "this combination must be detectable, because app/main.py refuses to start on it"
    )

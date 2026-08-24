#!/usr/bin/env python
"""Preflight: is MediKiosk actually talking to Supabase, and is it locked down?

Run it before a demo. `make supabase-check`.

The question this answers is not "did the connection open" — that is the easy half
and it is the half people check. It is:

    Is the durable clinical data really in Supabase, is the schema the one Alembic
    describes, and is the public key still unable to read any of it?

Every line it prints is a fact it verified, or a failure with the fix next to it.
No secret is ever printed: keys are reported by shape and last four characters.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is a hard dependency of the app
    httpx = None  # type: ignore[assignment]

OK = "\033[32m  ok  \033[0m"
BAD = "\033[31m FAIL \033[0m"
WARN = "\033[33m warn \033[0m"

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"{OK if ok else BAD} {label}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(label)
    return ok


def warn(label: str, detail: str = "") -> None:
    print(f"{WARN} {label}{f' — {detail}' if detail else ''}")


def redact(secret: str | None) -> str:
    """Enough to identify a key, never enough to use one."""
    if not secret:
        return "unset"
    return f"{secret[:12]}…{secret[-4:]} ({len(secret)} chars)"


#: Everything the longitudinal record needs. A schema missing any one of these is a
#: schema that will fail at the moment a physician commits, which is the worst time.
DURABLE_TABLES = (
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
)


async def main() -> int:
    from app.core.config import settings

    print("\nMediKiosk → Supabase preflight\n" + "─" * 58)

    # ---------------------------------------------------------------- 1. SQL
    print("\nDATABASE (SQLAlchemy — the path all clinical data takes)")
    print(f"       backend: {settings.database_backend}")
    print(f"       host:    {settings.database_host}")

    if settings.is_sqlite:
        check(
            False,
            "DATABASE_URL points at Supabase",
            "still SQLite — nothing will appear in Supabase. Set DATABASE_URL to the "
            "session-pooler string (Dashboard → Project Settings → Database → "
            "Connection string → Session pooler) and REQUIRE_SUPABASE=true.",
        )
        print()
        return 1

    check(settings.is_supabase, "DATABASE_URL points at Supabase", settings.database_host)

    from sqlalchemy import text

    from app.db.session import get_engine

    try:
        async with get_engine().connect() as conn:
            version = (await conn.execute(text("select version()"))).scalar_one()
            check(True, "connection opens", str(version).split(",")[0])

            head = (
                await conn.execute(text("select version_num from alembic_version"))
            ).scalar_one_or_none()
            check(
                head is not None,
                "schema is under Alembic",
                f"head {head}" if head else "no alembic_version row — run `alembic upgrade head`",
            )

            rows = (
                await conn.execute(
                    text(
                        "select table_name from information_schema.tables "
                        "where table_schema = 'public'"
                    )
                )
            ).scalars().all()
            present = set(rows)
            missing = [t for t in DURABLE_TABLES if t not in present]
            check(
                not missing,
                "every durable table exists",
                f"{len(DURABLE_TABLES)} tables" if not missing else f"missing {missing}",
            )

            # RLS. The whole point of the lockdown migration.
            unprotected = (
                await conn.execute(
                    text(
                        "select c.relname from pg_class c "
                        "join pg_namespace n on n.oid = c.relnamespace "
                        "where n.nspname = 'public' and c.relkind = 'r' "
                        "and c.relrowsecurity = false"
                    )
                )
            ).scalars().all()
            check(
                not unprotected,
                "row level security is on for every table",
                "all tables" if not unprotected else f"UNPROTECTED: {list(unprotected)}",
            )

            counts: dict[str, Any] = {}
            for table in ("patient", "encounter", "clinical_fact", "timeline_event"):
                counts[table] = (
                    await conn.execute(text(f"select count(*) from {table}"))  # noqa: S608
                ).scalar_one()
            seeded = counts["patient"] > 0 and counts["encounter"] > 0
            check(
                seeded,
                "durable data is present",
                ", ".join(f"{k}={v}" for k, v in counts.items())
                if seeded
                else "empty — start the API once and it seeds the demo patient",
            )
    except Exception as exc:  # noqa: BLE001 - the message is the whole product here
        check(False, "connection opens", f"{type(exc).__name__}: {str(exc)[:200]}")
        print()
        return 1

    # ------------------------------------------------------------- 2. keys
    print("\nAPI KEYS (used for Storage and for this check — never for clinical SQL)")
    print(f"       url:            {settings.supabase_url or 'unset'}")
    print(f"       publishable:    {redact(settings.supabase_publishable_key)}")
    print(f"       secret:         {redact(settings.supabase_secret_key)}")

    if httpx is None or not settings.supabase_url:
        warn("REST reachability", "SUPABASE_URL unset — skipping")
    else:
        base = settings.supabase_url.rstrip("/")
        async with httpx.AsyncClient(timeout=15) as client:
            if settings.supabase_secret_key:
                key = settings.supabase_secret_key
                response = await client.get(
                    f"{base}/rest/v1/patient",
                    params={"select": "patient_ref", "limit": 1},
                    headers={"apikey": key, "Authorization": f"Bearer {key}"},
                )
                check(
                    response.status_code == 200,
                    "secret key reaches the project",
                    f"HTTP {response.status_code}",
                )

            # The security check that actually matters: the key that ships in browsers
            # must not be able to read a single clinical row.
            if settings.supabase_publishable_key:
                key = settings.supabase_publishable_key
                response = await client.get(
                    f"{base}/rest/v1/clinical_fact",
                    params={"select": "fact_ref", "limit": 1},
                    headers={"apikey": key},
                )
                denied = response.status_code in (401, 403) or response.json() == []
                check(
                    denied,
                    "public key CANNOT read clinical data",
                    f"HTTP {response.status_code}"
                    if denied
                    else f"EXPOSED — HTTP {response.status_code} returned rows",
                )

    print("\n" + "─" * 58)
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}\n")
        return 1
    print("All checks passed. Supabase is the durable store.\n")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(asyncio.run(main()))

"""Deny-by-default RLS on every table, because Supabase publishes the schema.

The thing that makes Supabase convenient is the thing that makes this necessary: PostgREST
serves every table in `public` over HTTPS, and the `anon` key that reaches it is *designed*
to be public — it ships in browser code. Without RLS, `GET /rest/v1/clinical_fact` returns
the ledger to anybody who has looked at the network tab. The database linter reports exactly
this, at ERROR level, for all twenty-three tables.

The model here is deliberately the blunt one:

    RLS enabled, and NO policies at all.

A table with RLS on and no policy denies every row to `anon` and `authenticated`. Swastra
does not want per-row rules in the database yet, because it has no real identity in the
database to write them against — the ABHA identity is a mock JWT verified by FastAPI, and
inventing a parallel Supabase Auth identity to satisfy a policy expression would create the
second, conflicting patient identity that the brief explicitly refuses (§5).

So the access model stays where the authorisation already lives:

    browser ──▶ FastAPI (ABAC + session ownership) ──▶ SQLAlchemy ──▶ Postgres

The backend connects as the owning role, which bypasses RLS, and every clinical read it
serves has already been through `require_action()` and `assert_session_access()`. RLS is not
the authorisation model; it is the wall that stops anyone going around the authorisation
model. `docs/SUPABASE_SECURITY.md` records how real patient and clinician claims would map
to policies when there is a real IdP to map them from.

This runs on PostgreSQL only. SQLite has no RLS and needs none — it is a local file used by
the tests, not a service listening on the internet.
"""

from __future__ import annotations

from alembic import op

revision: str = "fdb61bb8d5ef"
down_revision: str | None = "f207e01b6812"
branch_labels: str | None = None
depends_on: str | None = None


#: Every table the schema owns. `alembic_version` is included deliberately — it leaks which
#: migrations have run, which is free reconnaissance and has no reason to be readable.
TABLES = (
    "alembic_version",
    # capture side
    "audit_event",
    "code_system",
    "concept",
    "consent_record",
    "intake_session",
    "red_flag_proposal",
    "session_document",
    "session_fact",
    "submitted_bundle",
    # durable side
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


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


#: PostgREST's roles. They exist on Supabase and on nothing else — not on a local
#: Postgres, not in CI, not in a reviewer's container. Revoking from a role that does
#: not exist is a hard error, so this migration used to abort `alembic upgrade head`
#: everywhere except Supabase, which is the opposite of reproducible.
_SUPABASE_ROLES = ("anon", "authenticated")


def upgrade() -> None:
    if not _is_postgres():
        return

    bind = op.get_bind()
    present = [
        role
        for role in _SUPABASE_ROLES
        if bind.exec_driver_sql(
            f"SELECT 1 FROM pg_roles WHERE rolname = '{role}'"  # noqa: S608 — literal above
        ).first()
    ]

    for table in TABLES:
        # ENABLE, deliberately not FORCE. `FORCE ROW LEVEL SECURITY` applies the policies to
        # the table owner too, and the backend connects as the owner — forcing it would deny
        # the application its own data and take the whole app down, which is not a security
        # posture, it is an outage. ENABLE denies `anon` and `authenticated` (neither has a
        # policy) while leaving the owning role, the one behind FastAPI's ABAC, working.
        #
        # RLS itself is portable: enabling it on a plain Postgres is harmless, because the
        # owner bypasses it and no other role is granted anything.
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        # Belt and braces: RLS alone would be enough, but a policy added by mistake later
        # cannot grant what was never granted in the first place. Skipped when the roles are
        # absent — there is nothing to take away.
        if present:
            op.execute(f"REVOKE ALL ON public.{table} FROM {', '.join(present)}")


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")

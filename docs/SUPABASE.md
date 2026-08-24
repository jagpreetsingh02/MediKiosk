# Supabase as the durable store

*How MediKiosk connects, which connection string to use, and who owns the schema.*

---

## What Supabase is, and is not, in this system

| | |
|---|---|
| **Is** | The durable longitudinal store — patients, encounters, confirmed facts and their evidence, medications, observations, timeline, documents, decisions, audit |
| **Is not** | An identity provider. ABHA identity stays a mock JWT verified by FastAPI (`docs/SUPABASE_SECURITY.md` explains why introducing Supabase Auth would be actively harmful here) |
| **Is not** | A client-side database. The React app has no Supabase client and no credential; every clinical write goes through FastAPI so provenance, consent and ABAC apply |

The capture side does **not** become durable on arrival. That separation is the whole
architecture and it is unchanged by moving to Postgres:

```
IntakeSession (temporary)  ──physician confirms──▶  Encounter (durable, in Supabase)
        └────────────────── purged ◀────────── only after promotion succeeds
```

---

## Connecting

Set two variables:

```bash
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
REQUIRE_SUPABASE=true
```

`REQUIRE_SUPABASE=true` makes the app **refuse to start** if `DATABASE_URL` is not a Supabase
URL. Without it, a mistyped variable falls back to the local SQLite file and the demo comes up
looking perfectly healthy with an empty patient history — the worst possible failure, because
nothing tells you it happened. On startup the backend now logs which database it is on:

```
startup.database backend='Supabase PostgreSQL (pooled)' host='aws-0-ap-south-1.pooler.supabase.com:5432'
```

Host only. The URL carries the password and never reaches the logs.

### Which connection string — and why the pooler

Supabase offers two. Take the **session pooler** (port 5432 via `...pooler.supabase.com`):

| | Direct (`db.<ref>.supabase.co`) | **Session pooler** |
|---|---|---|
| IPv4 | Not available on the free tier | Works |
| Connection limit | Low, and every FastAPI worker holds a pool | Designed for many short-lived clients |
| Prepared statements | Fine | Fine in *session* mode |
| Verdict | Fails on IPv4-only networks — including most conference Wi-Fi | **Use this** |

Avoid the **transaction** pooler (port 6543) with SQLAlchemy + asyncpg: asyncpg uses prepared
statements, and transaction mode does not keep them across statements. It fails in a way that
looks like random query corruption, which is a terrible thing to debug during a demo.

`asyncpg` is already the driver the codebase expects — the URL scheme is
`postgresql+asyncpg`, and `app/db/session.py` sets `pool_pre_ping=True` for non-SQLite
engines, which matters on a pooler that can drop idle connections.

---

## The schema is owned by Alembic

**One source of truth. Alembic, not the dashboard.**

```bash
alembic upgrade head
```

Three revisions:

| Revision | What |
|---|---|
| `9b8e1f47140d` | The capture schema — sessions, facts, documents, consent, audit, terminology |
| `f207e01b6812` | The durable longitudinal schema — the thirteen patient-memory tables |
| `fdb61bb8d5ef` | Deny-by-default RLS on every table (`docs/SUPABASE_SECURITY.md`) |

`f207e01b6812` exists because of a real bug: `alembic/env.py` imported `app.db.models` and
never `app.db.durable`, so `Base.metadata` held only the capture half. On SQLite nothing
complained — `create_all()` runs at startup and quietly built the rest. On Supabase, the
entire patient memory would simply not have existed, with nothing in the logs to say why.

Two tests hold that shut: `tests/test_migrations.py` asserts the metadata covers both halves,
and runs `alembic check` so a model that drifts from its migration fails the build.

`create_all()` is now **SQLite-only**. On Postgres the app logs `mode='alembic'` and creates
nothing, because a `create_all()` on a real database papers over exactly the missing-migration
bug described above.

### If the schema was applied out-of-band

The tables were first created on this project by running Alembic's own generated DDL
(`alembic upgrade base:head --sql`) and stamping `alembic_version` to match. That keeps a
single history: a subsequent `alembic upgrade head` against the same project is a no-op
rather than a conflict.

---

## SQLite after Supabase

SQLite stays, for one job: **fast isolated unit tests**. `pytest` builds an in-memory database
per test and needs no network, which is why the suite runs in seconds. It is not a fallback
for the demo — see `REQUIRE_SUPABASE` above.

---

## Not done yet

Stated plainly, because a half-integrated database is easy to mistake for a finished one:

- **Documents** are stored as bytes in `document_record.content`, not in Supabase Storage.
  The evidence drawer works; the bucket migration is not done. Design in
  `docs/SUPABASE_SECURITY.md`.
- **pgvector** is available (0.8.2) and deliberately unused. Similar-encounter retrieval is
  deterministic set intersection over recorded features, which is explainable and, on one
  patient's handful of visits, no worse. Embeddings would be a regression in explainability
  for no measured gain.
- **RLS has no policies**, by design. The reasoning and the production path are in
  `docs/SUPABASE_SECURITY.md`.

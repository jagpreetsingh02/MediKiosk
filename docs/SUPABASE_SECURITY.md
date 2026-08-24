# Supabase security model

*What protects MediKiosk's data today, what does not, and what would have to change before
this touched a real patient.*

Last reviewed 2026-08-24, against project `behevbfnhciglrmrdouj`.

---

## The one-line version

**Authorisation lives in FastAPI. RLS is the wall that stops anyone walking around FastAPI.**

```
browser ──▶ FastAPI ──▶ SQLAlchemy ──▶ Supabase Postgres
             │
             ├── ABAC          config/policy.yaml, require_action()
             ├── ownership     assert_session_access(), _resolve()
             └── consent       FactLedger.consent_scopes
```

Nothing in the browser holds a database credential. The React app talks to FastAPI over the
same mock-ABHA bearer token it has always used, and FastAPI is the only thing with a
connection string.

---

## Why RLS was not optional

Supabase publishes every table in `public` through PostgREST, and the `anon` key that reaches
it is **designed to be public** — it is meant to ship in browser code. So the moment the
schema existed, `GET /rest/v1/clinical_fact` was a valid, unauthenticated request for the
entire fact ledger. The database linter reported it at ERROR level on all 23 tables.

That is not a theoretical exposure. It bypasses every check in the diagram above, because it
never reaches the diagram.

### What was done

Migration `fdb61bb8d5ef` enables RLS on all 23 tables and creates **no policies**:

```sql
ALTER TABLE public.<t> ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.<t> FROM anon, authenticated;
```

A table with RLS on and no policy denies every row to `anon` and `authenticated`. Verified:

| Check | Result |
|---|---|
| Tables with RLS enabled | **23 / 23** |
| Grants remaining to `anon` / `authenticated` | **0** |
| Policies | **0** — deliberately |
| Linter ERRORs | **0** (was 23) |

`ENABLE`, deliberately **not** `FORCE`. `FORCE ROW LEVEL SECURITY` applies policies to the
table owner as well, and the backend connects as the owner — forcing it would deny the
application its own data. That is not a security posture, it is an outage.

The remaining linter output is INFO-level `rls_enabled_no_policy` on each table. That is the
intended state, not an outstanding finding: no policy *is* the policy.

---

## Why there are no per-row policies yet

An RLS policy needs an identity in the database to write itself against — typically
`auth.uid()` from Supabase Auth. MediKiosk's identity is a **mock ABHA JWT** minted by
`app/auth/mock_idp.py` and verified by FastAPI. It is not a Supabase Auth user and there is no
`auth.users` row behind it.

Introducing Supabase Auth purely to satisfy a policy expression would create a second patient
identity system running alongside the ABHA one — which §5 of the integration brief explicitly
refuses, and which is a genuinely bad idea: two identity systems that disagree about who a
patient is, is worse than one that is honestly a mock.

So the ownership rules stay in the application, where they are tested:

| Rule | Where | Test |
|---|---|---|
| A patient reaches only their own session | `assert_session_access()` in `app/api/deps.py` | `tests/test_authorization.py` |
| A patient reaches only their own record | `_resolve()` in `app/api/routes_patient.py` | `tests/test_longitudinal.py` |
| Only a clinician commits | ABAC `summary.commit` | `tests/test_api_end_to_end.py` |
| A nurse sees priority, not the narrative | ABAC `redflag.read` without `summary.read` | `config/policy.yaml` |

---

## What production would need

This section is the honest part. None of the below is implemented.

1. **Real ABDM identity.** Replace the mock IdP with ABDM, so a patient's ABHA number is
   established by an authority rather than asserted by a token this repo mints.
2. **Map claims into Postgres.** Either issue Supabase-compatible JWTs carrying `abha_ref` and
   `role`, or exchange the ABDM token for one. Then the policies become writable:

   ```sql
   -- illustrative only; not applied
   CREATE POLICY patient_reads_own_encounters ON encounter FOR SELECT
     USING (patient_id IN (
       SELECT id FROM patient WHERE abha_ref = auth.jwt() ->> 'abha_ref'
     ));

   CREATE POLICY clinician_reads_assigned ON encounter FOR SELECT
     USING (auth.jwt() ->> 'role' = 'clinician');
   ```

   Note that even then, the clinician policy is the hard one: "a clinician may read any
   patient" is what the demo does and is *not* acceptable in production. It needs a
   care-relationship table, which does not exist yet.
3. **Defence in depth, not replacement.** The FastAPI checks stay. RLS would become a second
   independent layer, which is the point of it.
4. **A non-owner application role.** The backend currently connects as the owning role, which
   bypasses RLS. Production should connect as a dedicated role with explicit grants, so RLS
   applies to the application too and a bug in FastAPI cannot leak across patients.

---

## Secrets

| Variable | Where it may appear | Where it must never appear |
|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | Backend environment only | Anywhere under `frontend/`, any `VITE_*` var, any committed file |
| `DATABASE_URL` | Backend environment only | Same |
| `SUPABASE_ANON_KEY` | Public by design — but unused here | — |

`tests/test_supabase_config.py::test_no_supabase_secret_can_reach_the_browser` scans
`frontend/` and fails the build on a hit. The service-role key bypasses RLS completely, so
shipping it to a browser would undo everything on this page in one line.

MediKiosk's frontend does not use the Supabase JS client at all, and should not start: clinical
writes go through FastAPI so that provenance, consent and ABAC apply to every one of them
(§4 of the brief).

---

## Storage

Documents are currently stored as bytes in `document_record.content`, not in Supabase Storage.
That is a deliberate carry-over, not an oversight — see `docs/adr/` — and it keeps the evidence
drawer working with no bucket configuration. If it moves to Storage, the bucket must be
**private**, addressed as `patient_id/encounter_id/document_id/original.ext`, and served to the
physician through short-lived signed URLs minted by the backend. Never a public bucket: a
prescription is clinical data even when it is synthetic.

## Audio

Raw microphone audio is **not stored**, durably or otherwise. The record keeps the transcript
as `SourceEvidence.verbatim`, which is what click-to-source needs. This is a decision, recorded
here because the brief asked for it to be explicit rather than silent.

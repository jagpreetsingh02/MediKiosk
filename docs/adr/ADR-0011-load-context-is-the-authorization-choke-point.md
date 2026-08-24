# ADR-0011 — Session authorization lives in `load_context()`, not on the routes

**Context.** Until this slice, a session reference in a URL was the entire access control
story for the capture side. `load_context(db, session_ref)` took no identity and asked nobody's
permission, and all 24 route handlers that used it inherited that. A patient token could read,
answer into, upload documents to, and generate a summary from any other patient's session by
guessing or observing a reference. The patient-memory routes added in the previous phase did
check ownership — in their own `_resolve()` — which made the gap easier to miss, because the
new surface looked authorised while the older one underneath it was not.

The obvious fix is a FastAPI dependency on each route: `dependencies=[Depends(owns_session)]`.
It is idiomatic, it reads well, and it has the same failure mode as the bug it replaces — the
26th route forgets it, and nothing fails.

**Decision.** Enforce ownership inside `load_context()`, which every path into a session's
facts already runs through. `identity` is keyword-only with no default; a default would be a
bypass. `tests/test_authorization.py` scans the source tree for a call site that omits it,
mirroring the treatment `record_fact()` gets in `tests/test_invariant_provenance.py`.

The rule itself:

| Role | Reaches |
|---|---|
| `patient` | only sessions whose `abha_ref` equals the token's |
| `clinician`, `triage_nurse`, `auditor` | any session — reviewing one you did not create *is* the job, and ABAC actions are what constrain them |
| `anonymous` | nothing, unless `AUTH_REQUIRED=false` |

**Alternatives.** A per-route dependency (rejected above). Middleware that parses the session
reference out of the path (couples authorisation to URL shape, and silently stops working the
day a route takes the reference in a body). Checking in each handler (the status quo, which is
what produced the hole).

**Consequences.** `load_context()` now has an authorisation responsibility as well as a
loading one, which is a genuine cost: the name no longer describes everything it does. That is
accepted for the same reason `record_fact()` validates rather than just writing — a guarantee
that depends on every caller remembering is not a guarantee. The demo exemption for
`anonymous` is real and is stated in `/about` rather than hidden; a jury asking "what happens
with auth on" gets a test as the answer, not a claim.

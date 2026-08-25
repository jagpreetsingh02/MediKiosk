# ADR-0014 — Split hosting: static frontend on Vercel, Dockerized backend on Render

**Context.** V1 needed a public URL. The frontend is a static Vite build with no server-side
rendering requirement — Vercel is the obvious host. The backend is a different matter: it
needs Tesseract (a system binary, not a Python package), a long-lived async connection pool to
Supabase, and a self-referencing HTTP call for the stub HIS push. None of that fits a
serverless function well, and Vercel does not run arbitrary system binaries in its Python
runtime at all.

**Decision.** Split the deploy across two platforms:

* **Vercel** — the frontend only, as a static build (`framework: vite`, `outputDirectory:
  dist`). `frontend/vercel.json` rewrites `/api/*`, `/mock-idp/*`, and `/about` to the Render
  backend, so the browser only ever talks to one origin and nothing in `shared/api.ts` needed
  to change — it was already calling relative paths for exactly this reason (see its own
  comment about CORS and venue kiosks).
* **Render, web service, `runtime: docker`** — built from the repo's existing `Dockerfile`,
  unchanged. Free tier, Singapore region (closest to the Supabase project's `ap-northeast-2`,
  though still a cross-region hop either way).
* **Database stays Supabase**, reached over the same session-mode pooler the runtime already
  uses (see ADR-0011's neighbour, `docs/SUPABASE.md`) — not Render's free Postgres, which is
  1 GB and expires in 30 days, i.e. wrong for a durable store on any timeline longer than a
  single demo.

**Why not Render's native (non-Docker) Python runtime.** Tried first, since it was reachable
through more tooling. It fails hard: `apt-get install tesseract-ocr` in the build command
returns `Read-only file system` — Render's native build environment does not run as a user
that can write to `/var/lib/apt`. There is no build-time system-package escape hatch for
native runtimes on Render; Docker is the only path to a system binary. This was verified by
attempting it and reading the actual build failure, not inferred from documentation.

**Two more decisions this forced, both real bugs caught by trying the deploy rather than
assuming it would work:**

1. **`HIS_FHIR_ENDPOINT` cannot stay `http://localhost:8000/...`.** It is a real `httpx` call
   the process makes to itself (`app/modules/consent/his_push.py`) to simulate the hospital
   push. Render assigns the listen port via `$PORT`, which is not reliably 8000. The start
   command now computes both the bind port and this self-referencing URL from the same
   `${PORT:-8000}`, so they cannot drift apart:
   `export HIS_FHIR_ENDPOINT="http://127.0.0.1:${PORT:-8000}/api/v1/stub-his/Bundle"; uvicorn ...`

2. **`AUTH_REQUIRED=true` breaks the kiosk.** `.env.example` calls this "true in any deployed
   environment," which is the right instinct for a token-gated API but wrong for this
   product's actual shape: `POST /api/v1/sessions` resolves `CurrentIdentity` unconditionally,
   before any policy check, and a patient has no token yet at that point — the kiosk intake is
   *designed* to start anonymous, gated by `config/policy.yaml`'s per-action rules rather than
   by a login wall. Setting it `true` returned 401 on the very first call the kiosk makes and
   was caught immediately by testing the deployed URL directly, not left for a demo to find.
   Reverted to `false`, matching local dev and every test that has ever exercised this path.

**Consequences.**

* Two things to keep in sync instead of one: the Render URL in `frontend/vercel.json`, and the
  Vercel origin in Render's `CORS_ORIGINS`. Both are plain config, not secrets, so this is a
  redeploy, not a re-architecture, if either changes.
* Render's free tier sleeps the backend after inactivity. Cold start after a sleep is
  30–60 seconds. This is a real, demoable-around constraint, not a bug — `docs/DEMO-DAY.md`
  §0 says to warm it with a plain `curl /health` a couple of minutes before presenting.
  Session state (`SESSION_STORE_ALLOW_MEMORY_FALLBACK=true`, no Redis provisioned) does not
  survive a cold sleep either; an abandoned kiosk session across a long gap simply expires,
  which is the same behaviour `sweep_expired` already gives it locally.
* No git integration exists yet between this GitHub account and Vercel (the account's GitHub
  App was never installed), so the first frontend deploy has to go through Vercel's
  "Import Git Repository" flow once, by hand, in the dashboard — a one-time browser action
  that authorizes the app and installs the git-based auto-deploy this ADR otherwise assumes.
  Render's side already auto-deploys on push to `main`, since that connection existed from the
  service's creation.

**Alternatives considered.** A single Node/Python monolith on one platform (rejected — no
platform here runs a system-dependency-bearing Python server and serves a static SPA equally
well; picking one over the other means either fighting Tesseract's absence or losing Vercel's
build/CDN pipeline for no reason). Installing a static Tesseract binary by hand at build time
on Render's native runtime, bypassing `apt` (rejected — fragile, unverified against the exact
binary already tested, and solves a problem Docker already solves correctly).

# Swastra current-code audit

Date: 24 August 2026  
Requirement source: `/Users/jagpreet/Downloads/SIH26047_CODEX_HANDOFF_FULL_CONTEXT_AND_AUDIT.md`

## Verdict

The repository is a strong single-encounter intake implementation. It has a real adaptive state machine, source-linked facts, deterministic red flags, OCR, a traceable draft summary, a physician current-encounter screen, FHIR preview/commit, consent/purge, audit, and extensive tests. It does not yet implement the handoff's defining longitudinal patient memory.

## Architecture and flow

- React 18/Vite/TypeScript routes: landing, kiosk, physician, demo.
- FastAPI/Pydantic/async SQLAlchemy backend.
- SQLite by default, optional Postgres/Redis.
- Temporary `IntakeSession`, `SessionFact`, and `SessionDocument` rows; durable consent, audit, terminology, and submitted FHIR bundle JSON.
- Kiosk: language -> mock ABHA -> consent -> adaptive interview -> documents -> patient review.
- Physician: queue -> draft summary -> source/conflicts/red flags/per-session document timeline -> edit -> FHIR preview -> whole-encounter commit.

## Data-lifecycle finding

`app/db/models.py` explicitly states that session facts/documents are purged and that the committed FHIR JSON bundle is the only durable clinical artifact. New sessions do not reconstruct prior encounters by patient. Therefore medication history, recurrence, trends, and historical similarity cannot work as required.

## Real, mocked, and absent

Real: adaptive dialogue, provenance validation, deterministic safety rules, OCR/entity extraction, summary traceability, consent/purge, FHIR generation, audit chain, evaluation.

Mock/stub: ABHA/OTP/staff identity, HIS receiver, synthetic fixtures, small terminology subsets.

Absent: patient/encounter longitudinal repository, prior-visit queries, similarity/trends, original scan viewer, connected OCR verification queue, per-fact accept/reject, production ABDM/vendor HIS.

## Material defects and risks

- Many session/dialogue/document endpoints have neither `require_action` nor patient ownership checks; anonymous use is allowed by default.
- Browser speech maps reported confidence `0` to `0.7`, weakening the low-confidence safety path.
- Uploaded document bytes/pages are not persisted; the physician source panel draws a box on a blank outline.
- The physician OCR verification component is not populated by the normal data-loading path.
- Red-flag decisions are evaluated, but `RedFlagProposal` rows are not written.
- FHIR provenance is not emitted for every clinical resource; AYUSH coding helper is not wired.
- Docker Compose does not deploy the frontend.

## Verification

Ruff, mypy and TypeScript passed. Pytest passed 200 tests. The strict offline evaluation passed 50 development and 12 held-out scripts. `make check` itself was not hermetic in this environment because `LLM_BACKEND=auto` selected Groq from an available key and retried an unavailable network; `LLM_BACKEND=offline` passed.

The complete quantified analysis is in `docs/GAP_ANALYSIS.md`; the proposed end state and implementation sequence are in `docs/TARGET_ARCHITECTURE.md` and `docs/MIGRATION_PLAN.md`.


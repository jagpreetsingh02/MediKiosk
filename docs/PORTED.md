# What was ported from SIH 25026, what was adapted, what was left behind

Source repo: `../NAMASTE` — the NAMASTE ↔ ICD-11 TM2 FHIR R4 terminology micro-service built
for SIH 2025 PS 25026. Read at commit `HEAD` on 2026-08-23.

The rule applied throughout: **port the guarantee, not the feature.** A component came across
if the *invariant it enforces* is also an invariant here. Where the 25026 version enforced
something Swastra does not need (ICD-11 release pinning across a WHO API), the enforcement
mechanism came across and the domain content did not.

---

## Ported essentially unchanged

| Component | 25026 path | Swastra path | Change on the way across |
|---|---|---|---|
| Hash-chained audit log | `app/audit/chain.py` | `app/audit/chain.py` | Three columns added (`model_name`, `model_version`, `prompt_hash`) and folded into `row_payload()` so they are covered by the hash; new `record_ai_call()` helper; `FORBIDDEN_KEYS` widened for narrative content. |
| ABAC policy evaluator | `app/auth/policy.py` | `app/auth/policy.py` | Code unchanged. `config/policy.yaml` rewritten for clinical-intake roles. |
| Caller identity / JWT decode | `app/auth/identity.py` | `app/auth/identity.py` | Added a `demographics` claim so the kiosk can pre-fill age and gender from the ABHA token instead of asking an elderly patient to type them. |
| Closed-vocabulary guard | `app/terminology/guard.py` | `app/terminology/guard.py` | Verbatim. Still no `force` parameter, still the only place a `Coding` is constructed. |
| FHIR `OperationOutcome` builders | `app/fhir/outcomes.py` | `app/fhir/outcomes.py` | Base exception renamed `TerminologyError` → `SwastraError`. |
| Domain error hierarchy | `app/core/errors.py` | `app/core/errors.py` | Base renamed; Swastra invariant errors added (`ProvenanceError`, `DiagnosisAttempt`, `TraceabilityError`, `DeEscalationAttempt`, `ConsentRequired`). |
| Settings pattern | `app/core/config.py` | `app/core/config.py` | Same `pydantic-settings` + `@lru_cache` shape and the same "nothing hardcoded at a call site" rule. Contents are Swastra's. |
| `AuditEvent`, `CodeSystem`, `Concept` tables | `app/db/models.py` | `app/db/models.py` | Structurally identical, so the ported chain code needed no changes. |
| Docker compose stack | `docker-compose.yml` | `docker-compose.yml` | Same four-service shape (API + `pgvector/pgvector:pg16` + Redis + `whoicd/icd-api`). |

## Adapted

| Component | What changed and why |
|---|---|
| **Mock ABHA IdP** (`app/auth/mock_idp.py`) | 25026 only needed staff tokens. Swastra is patient-facing, so a two-step ABHA login was added: `POST /mock-idp/abha/request-otp` then `/verify-otp`, returning a `patient`-role token carrying a pseudonymous `abha_ref` (SHA-256 of the address, truncated) plus demographics. The demo OTP is the constant `123456` — a random OTP printed to a server log is a demo failure waiting to happen. Still labelled `mock: true` in the token, in `/about`, and behind a permanent banner in the kiosk UI. |
| **Terminology store** (`app/terminology/store.py`) | 25026 ingested ICD-11 over HTTP and NAMASTE from an Excel release, with pg_trgm fuzzy search. Swastra needs *a loaded table for the guard to verify against*, not the release pipeline, so this is the ingestion half only, reading JSON from `data/terminology/`. Fuzzy matching was deliberately dropped: it would add a Postgres dependency to a code path whose correct answer is very often "unmapped". |
| **FHIR model imports** (`app/fhir/r4.py`) | ADR-0002 carries across intact (build with R4B models, stamp `fhirVersion 4.0.1`). The *resource list* is different: 25026 emitted terminology resources (ConceptMap, ValueSet), Swastra emits a clinical document (Composition-led Bundle, Condition, MedicationStatement, AllergyIntolerance, Observation, Consent, DocumentReference, Provenance, Flag). |
| **`emit_coding()` callers** | Wrapped in a new `app/terminology/sidecar.py`. The sidecar adds a rule 25026 did not need: only an **exact** normalised match is auto-applied. Near matches stay unmapped rather than picking between them. |

## Left behind deliberately

| Not ported | Why |
|---|---|
| ConceptMap / `$translate` engine, dual-coding validation | Swastra maps a patient-reported term to at most one code. There is no NAMASTE↔ICD-11 translation surface here, so the mapping engine, the `Mapping`/`Candidate` tier split and the review queue would be dead code. |
| WHO ICD-11 API client (`app/clients/icd.py`) | The demo runs against a seeded local table. The `whoicd/icd-api` container is still in `docker-compose.yml` for when the ingestion pipeline is pointed at it. |
| Embedding / pgvector candidate layer | Its job was suggesting *mappings* for human review. Swastra's coding sidecar deliberately refuses to suggest — unmapped is the answer. |
| Transliteration rules (`data/translit-rules.yaml`) | Built for matching Devanagari/Tamil/Arabic term spellings against a terminology index. Swastra matches free text against a small option set instead. Worth revisiting if the problem list grows. |
| `dashboard/` React app | Different product. The physician surface here is built fresh. |
| Alembic migration history | Swastra's schema shares only three tables. A fresh initial migration was cleaner than porting one that mostly describes ConceptMap. |

## Honest note on the reuse claim

Roughly **1,100 lines** came across as working code — the audit chain, the guard, the ABAC
evaluator, identity, error hierarchy, FHIR outcome builders and the compose stack. That is a
real head start on the compliance spine, and it is the part of a hackathon build that is
least fun to write twice.

What did **not** come across, and is worth stating plainly: the terminology *content* is a
small hand-seeded demo subset (24 ICD-11 concepts, 15 NAMASTE, 65 Dashavidha), not the full
NAMASTE release the 25026 service ingested. The ingestion path is the same; the data volume
is not. Anything measuring coding coverage should say so.

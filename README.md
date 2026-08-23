# MediKiosk

**Patient-facing clinical intake for SIH26047** — All India Institute of Ayurveda, Ministry of Ayush.

A patient walks up before their OPD consultation. They authenticate with an ABHA ID, pick a
language, give consent, then record their medical history by **speaking or tapping —
interchangeably, at any point**. They scan their existing paper prescriptions and lab reports.
By the time they enter the consultation room, the physician's screen already shows a structured,
**source-linked** clinical history and a chronological timeline of their prior records, ready to
be reviewed, edited and confirmed.

> **MediKiosk produces a history. It never produces a diagnosis.** No endpoint returns an
> assessment, a differential, or a disease probability. The physician diagnoses.

---

## Run it

```bash
make setup     # python3.12 venv + pip + npm  (no uv, no poetry, no Docker)
make demo      # API on :8000, kiosk and physician screen on :5173
```

| | |
|---|---|
| Kiosk (patient) | http://127.0.0.1:5173/ |
| Physician review | http://127.0.0.1:5173/physician |
| API docs | http://127.0.0.1:8000/docs |
| **What is mocked** | http://127.0.0.1:8000/about |

**Demo login** — patient: any listed ABHA address, OTP `123456`. Staff: any name, role
`clinician`.

Everything runs on SQLite with an in-process session store and a rule-based extractor, so it
works with no Docker, no network and no API key. `docker compose up` gives the full stack
(FastAPI + `pgvector/pgvector:pg16` + Redis + WHO `whoicd/icd-api`).

---

## The six invariants

Architectural, not aspirational. Each is enforced in code and each has a test that fails the
build if violated.

1. **Never diagnoses.** `ClinicalHistory` has no assessment-shaped field, and every outbound
   payload is scanned.
2. **Provenance or nothing.** Every fact carries the verbatim utterance or document span it came
   from, plus a confidence and a tier — `stated` / `confirmed` / `document`. There is no fourth
   tier. A field with no source is `not_asked` or `declined`, never inferred. Enforced by one
   choke point, `record_fact()`, which has no bypass.
3. **Red flags escalate, never de-escalate.** `Priority` has no member below `ROUTINE`. An LLM
   may propose a candidate flag; the deterministic rules decide. Every proposal is logged,
   fired or not.
4. **The physician is the committer.** Nothing reaches the HIS or the ABHA record until a
   physician explicitly confirms. Every summary line is click-to-source.
5. **Codes are retrieved, never generated.** Every code comes from a version-pinned CodeSystem.
   Unmapped is a first-class 200, never a guess.
6. **Consent gates everything, and sessions die.** Granular, revocable, audio-explained consent;
   session data purged on submit and on TTL expiry; every AI call in a hash-chained audit log.

---

## Measured results

`make eval` reproduces all of this. Full methodology and caveats: **[docs/EVALUATION.md](docs/EVALUATION.md)**.

| Metric | Target | Development (n=50) | **Held-out (n=12)** |
|---|---|---|---|
| Hallucination rate | **0**, hard-enforced | **0.0000** | **0.0000** |
| Unsourced summary claims | **0**, hard-enforced | **0** | **0** |
| Red-flag sensitivity | **≥ 0.98** | **1.0000** | **1.0000** |
| Priority under-calls | 0 | **0** | **0** |
| Extraction accuracy | tracked | 1.0000 | **0.9048** |
| History completeness | tracked | 0.9928 | **0.9695** |

The 12 held-out scripts were written *after* the extraction lexicon was tuned and are never
tuned against. **Extraction drops 9.5 points on unseen phrasing; the safety metrics do not move
at all** — because those come from rules and structure, not from the extractor.

---

## Architecture

Four modules, matching the problem statement's own structure, independently testable.

**Module A — conversational history engine.** A *deterministic state machine* walking a clinical
ontology (chief complaint → SOCRATES HPI → past medical/surgical → drugs & allergy → family →
personal → review of systems). 51 questions in YAML. The LLM does exactly two jobs — extract
slot values, and smooth prose — and **never decides what to ask next**. Every question is
answerable by speech or by tap, and the patient can switch mid-answer.

**Module B — document digitisation.** Upload → OCR → clinical entity extraction → chronological
ordering → out-of-range flagging. An `OCRBackend` protocol with two implementations, benchmarked
against ground truth rather than argued about. Handwriting goes to a low-confidence lane that
**cannot** reach the record without a human.

**Module C — summary generator.** Deterministic template assembly. After generation, every
clinical claim must resolve to a `record_fact()` entry or generation **fails** — no
half-verified summary.

**Module D — consent, privacy, ABDM.** Mock ABHA auth, granular consent, FHIR R4 push with a
`Provenance` resource per clinical resource, hash-chained audit, session teardown.

Roughly 1,100 lines of the compliance spine were **ported from the SIH 25026 NAMASTE↔ICD-11
service** — the audit chain, the ABAC evaluator, the mock IdP, and the closed-vocabulary
`emit_coding()` guard. See **[docs/PORTED.md](docs/PORTED.md)** for exactly what came across,
what was adapted, and what was left behind.

---

## Documentation

| | |
|---|---|
| **[UPDATE.md](UPDATE.md)** | Build status, measured numbers, known gaps, what I would do next |
| **[AGENT.md](AGENT.md)** | The invariants, the rule-or-LLM policy, layout and conventions |
| **[docs/EVALUATION.md](docs/EVALUATION.md)** | Methodology, the held-out gap, and the bugs the harness caught |
| **[docs/PORTED.md](docs/PORTED.md)** | What was reused from SIH 25026 |
| **[docs/adr/](docs/adr/)** | Ten architecture decision records |

## Out of scope

No diagnosis, triage-to-specialty routing, or treatment suggestion. No real patient data —
synthetic fixtures only. No kiosk hardware integration. No production ABDM credentials; the mock
IdP stands in and says so. No hospital HIS vendor integration beyond a documented FHIR endpoint
with a stub receiver.

# SIH26047 — MediKiosk build brief for Claude Code

Paste this as your opening message in a fresh Claude Code session, in an empty repo.
Then let it work phase by phase. Do not let it jump ahead.

---

## MISSION

Build **MediKiosk**, a patient-facing clinical intake platform for Smart India Hackathon 2026
problem statement SIH26047, posed by the All India Institute of Ayurveda (Ministry of Ayush).

A patient walks up before their OPD consultation. They authenticate with an ABHA ID, pick a
language, give consent, then record their medical history by **speaking naturally or tapping**
— whichever they prefer, interchangeably, at any point. They scan their existing paper
prescriptions and lab reports. By the time they enter the consultation room, the physician's
screen already shows a structured, source-linked clinical history and a chronological timeline
of their prior records, ready to be reviewed, edited and confirmed.

The problem being solved: Indian government OPDs see 4,000–10,000 patients a day at 2–5
minutes of consultation each. History-taking — which yields the correct diagnosis in 70–80%
of cases — gets compressed to nothing. AYUSH settings are worse, because Ayurvedic intake
(Dashavidha Pariksha) is a far larger framework than allopathic intake.

**Timeline: a working vertical slice must demo at the SRM internal hackathon in September 2026.**
Prioritise a narrow path that fully works over a wide path that half works.

---

## NON-NEGOTIABLE INVARIANTS

These are architectural, not aspirational. Enforce each one in code, with a test that fails if
it is violated. If a feature request conflicts with an invariant, stop and raise it.

1. **The system never diagnoses.** It produces a *history*, never an assessment, differential,
   or disease probability. No endpoint returns a candidate diagnosis. The physician diagnoses.

2. **Provenance or nothing.** Every field in the clinical record carries the verbatim patient
   utterance (or document span) it came from, plus a confidence and a tier:
   `stated` (patient said it) / `confirmed` (patient affirmed a direct question) /
   `document` (extracted from an uploaded record, with page and bounding box).
   There is no fourth tier. A field with no source is `not_asked` or `declined` — never inferred,
   never filled in from what "usually" accompanies a symptom.
   Implement this as a single choke point: `record_fact()`. Nothing writes to the history
   except through it, and it rejects any fact lacking a source span.

3. **Red flags escalate, never de-escalate.** Emergency symptom detection is recall-biased and
   additive only. It can move a patient up the queue; it can never move one down or mark
   anyone "low priority". The *decision* is a deterministic rule set over extracted symptoms.
   An LLM may propose a candidate flag; the rules decide. Log every proposal, fired or not.

4. **The physician is the committer.** The generated summary is a draft. Nothing reaches the
   HIS or the ABHA record until a physician explicitly confirms. Every summary line is
   click-to-source: clicking it plays/shows the exact utterance behind it.

5. **Codes are retrieved, never generated.** Any coded output (problem list, AYUSH parameters)
   comes from a version-pinned CodeSystem. Unmapped is a valid, first-class result — a 200,
   not an error, and never a guess.

6. **Consent gates everything, and sessions die.** No capture begins without granular, revocable,
   audio-explained consent. Session data is purged on submit and on TTL expiry. Every AI call
   is written to a hash-chained audit log with model name, version and prompt hash.

---

## REUSE THIS — DO NOT REBUILD IT

I have a working codebase from SIH 2025 (PS 25026, NAMASTE ↔ ICD-11 TM2 terminology service).
I will point you at the path. Port these in as libraries, do not reimplement:

- **Mock ABHA IdP** and the ABAC policy layer → becomes Module D's auth
- **Hash-chained audit log** → becomes the compliance spine
- **FHIR emission** (`fhir.resources` R4B models stamped `fhirVersion 4.0.1`, per ADR-0002)
  → becomes the HIS push
- **Terminology client with the closed-vocabulary `emit_coding()` guard** → becomes the coding
  sidecar for the problem list and Dashavidha parameters
- **Docker compose stack** (FastAPI + `pgvector/pgvector:pg16` + Redis + WHO `whoicd/icd-api`)

First task of Phase 0 is to read that repo and write `docs/PORTED.md` listing exactly what came
across, what was adapted, and what was left behind.

---

## ARCHITECTURE

Four modules, matching the problem statement's own structure. Keep them independently testable
with no cross-imports except through defined interfaces.

**Module A — Conversational history engine.** A *deterministic state machine* walking a clinical
history ontology (chief complaint → HPI via SOCRATES → past medical/surgical → drug & allergy →
family → personal → review of systems). The LLM does exactly two jobs: extract slot values from
an utterance, and phrase the next question naturally. **The LLM never decides what to ask next.**
Every question is answerable by speech or by tap, and the patient can switch modes mid-answer.

**Module B — Document digitisation.** Upload → OCR → clinical entity extraction (diagnoses,
medications with dosage, investigations with value + reference range, procedures) →
chronological ordering → out-of-range flagging. Define an `OCRBackend` protocol and ship two
implementations so they can be benchmarked against each other rather than argued about.
Handwritten input goes to a separate low-confidence lane that is always surfaced for human
verification — never silently merged into the record.

**Module C — Summary generator.** Synthesises Modules A and B into one physician-ready summary
in standard clinical format. Deterministic template assembly; the LLM only smooths prose within
a section, and cannot introduce a token that is not traceable to a recorded fact. Validate this:
after generation, every clinical claim in the summary must resolve to a `record_fact()` entry,
or generation fails.

**Module D — Consent, privacy, ABDM.** ABHA auth, granular consent, FHIR R4 push to HIS,
audit chain, session teardown.

---

## STACK AND ENVIRONMENT

- Python 3.12, **plain `venv` + `pip`** (no uv, no poetry — match my existing setup)
- FastAPI, SQLAlchemy + Alembic, Postgres via `pgvector/pgvector:pg16`, Redis for session state
- Keep the data layer dialect-aware so tests run on SQLite without Docker
- React + Vite frontend, two separate surfaces: **kiosk** (huge touch targets, icon-driven,
  audio prompts, usable by a first-time non-literate elderly patient with zero training) and
  **physician review** (dense, fast, keyboard-driven)
- LLM: Groq (key already in `.env`). All LLM output is JSON validated against a Pydantic model;
  a parse failure is a hard failure, never a silent fallback to free text
- ASR/TTS: define a `SpeechBackend` protocol. Ship an offline implementation first so the demo
  never depends on network. Add a Bhashini/AI4Bharat implementation behind the same interface —
  do not block the build on obtaining government API credentials
- `ruff` + `mypy` clean at every phase. Tests must pass before you move on
- **`git init` in Phase 0 and commit at every phase boundary.** I shipped last year's project
  with no git history; not repeating that
- One component per file, so I can customise pieces independently. UI especially

---

## BUILD PHASES

Do these in order. Each ends with a demo I can run in one command and a set of passing tests.
Stop at each boundary and show me what works before continuing.

**Phase 0 — Skeleton and contracts.** Repo, docker-compose, CI-less test harness, `CLAUDE.md`,
`docs/adr/`. Define the core Pydantic contract `ClinicalHistory` with the provenance tiers.
Implement `record_fact()` and its rejection tests. Port the 25026 components; write `PORTED.md`.

**Phase 1 — Deterministic dialogue, text only.** The history ontology and state machine. No AI
at all. Type answers, walk a full SOCRATES HPI plus ROS, get a complete structured record.
This must be exhaustively unit-tested — it is the spine, and it is the part that will still work
when a demo network drops.

**Phase 2 — Extraction layer.** LLM slot-filling with provenance. Free-text narration in,
structured facts out, each carrying its source span. Add the extraction-quality tests.

**Phase 3 — Voice.** ASR in, TTS out, language selection, dual-mode input, barge-in.
Automatic degradation: when ASR confidence drops below threshold, fall back to touch for that
question rather than guessing. Noisy-audio test fixtures required.

**Phase 4 — Documents.** OCR pipeline, entity extraction, timeline assembly, abnormal-value
flagging, the handwriting low-confidence lane.

**Phase 5 — Summary and physician screen.** Summary generation with the traceability check,
click-to-source UI, red-flag rule engine and the priority alert to triage staff.

**Phase 6 — ABDM and AYUSH mode.** Consent flow with audio explanation, FHIR bundle push,
audit chain, session purge. AYUSH extended interview capturing Dashavidha Pariksha
(Prakriti, Vikriti, Sara, Samhanana, Pramana, Satmya, Sattva, Ahara Shakti, Vyayama Shakti, Vaya)
and Ahara-Vihara, emitting coded output through the terminology sidecar.

---

## EVALUATION HARNESS — BUILD THIS, IT IS THE DIFFERENTIATOR

From Phase 2 onward, maintain `eval/` with a gold set of **50 synthetic patient scripts** —
written by me, covering multiple languages, low-literacy phrasing, rambling narration,
contradictory answers, and emergency presentations. Report on every run:

| Metric | Target |
|---|---|
| Hallucination rate (facts with no valid source span) | **0**, hard-enforced |
| Red-flag sensitivity on emergency scripts | ≥ 0.98 — false negatives are the only unacceptable error |
| History completeness vs gold | tracked, trending up |
| Extraction precision / recall per field | tracked per field |
| Time from session start to physician-ready summary | tracked |

Write `docs/EVALUATION.md` with the methodology and the current numbers. Almost no competing
team will report measured numbers; that is what wins the national screening round.

---

## OUT OF SCOPE — DO NOT BUILD

No diagnosis, triage-to-specialty routing, or treatment suggestion. No real patient data ever —
synthetic fixtures only. No kiosk hardware integration. No production ABDM sandbox credentials;
the mock IdP stands in. No hospital HIS vendor integration beyond a documented FHIR endpoint
with a stub receiver.

---

## HOW TO WORK WITH ME

- Read the whole brief before writing code. Ask about anything ambiguous rather than assuming.
- Work one phase at a time. Show me a running demo at each boundary and wait.
- Write an ADR for every non-obvious decision, in the style of ADR-0002 in my old repo.
- Prefer boring and deterministic over clever. Every place you reach for the LLM, first ask
  whether a rule would do the job — and say so in the commit message when you decide either way.
- If a phase is going to slip past the internal-hackathon deadline, tell me early and propose
  what to cut. A narrower working demo beats a broader broken one.

**Start with Phase 0. Show me the plan before you write files.**

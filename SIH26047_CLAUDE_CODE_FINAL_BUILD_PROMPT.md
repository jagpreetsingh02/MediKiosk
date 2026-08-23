# SIH26047 — MediKiosk
## Final Claude Code Build Prompt
### Upgrade the existing 28-question intake prototype into a hackathon-winning clinical intake platform

---

## 0. READ THIS FIRST

You are working on an **existing MediKiosk codebase** for **Smart India Hackathon 2026, Problem Statement SIH26047**.

The current website is **not empty**. It already has a basic patient intake flow where:

- the user answers approximately **28 fixed questions**;
- the answers are collected;
- the system creates a summary for the doctor.

That existing flow is the **baseline**, not the final product.

Your job is **not to rebuild the same form with better styling**.

Your job is to transform the current project into a **complete, convincing, safe, multilingual, interoperable clinical pre-consultation system** that demonstrates why this solution matters in a real OPD and why it is substantially better than a normal form or chatbot.

The core idea is:

> **A patient should be able to arrive before consultation, authenticate/give consent, speak or tap in their preferred language, undergo adaptive clinical history-taking, upload previous medical documents, and reach the doctor with a structured, source-linked, safety-checked history and chronological timeline already prepared for physician review.**

The system **assists history collection**.  
It **does not diagnose, prescribe, recommend treatment, or replace a physician**.

---

# 1. PRIMARY OBJECTIVE

Convert the existing fixed-question prototype into a **working vertical slice** with three clearly different surfaces:

1. **Patient Kiosk / Intake Surface**
   - low-friction;
   - multilingual;
   - voice + touch;
   - adaptive questions;
   - document upload;
   - consent-aware;
   - accessible to low-literacy and elderly users.

2. **Physician Review Surface**
   - fast and dense;
   - structured clinical history;
   - timeline of prior documents;
   - red-flag alerts;
   - confidence/provenance;
   - click-to-source evidence;
   - physician edit/confirm before data is committed.

3. **Evaluation / Demo Surface**
   - synthetic demo cases;
   - system metrics;
   - traceability checks;
   - red-flag evaluation;
   - latency/completeness metrics;
   - a one-click jury demo mode.

The current 28-question flow must be retained only as a **fallback/reference ontology**, not as the main user experience.

---

# 2. WHAT IS WRONG WITH THE CURRENT VERSION

The current version is effectively:

```text
Patient
  ↓
28 fixed questions
  ↓
Submit
  ↓
Doctor summary
```

That is too close to a normal CRUD/form project.

The upgraded version must become:

```text
Patient arrives
  ↓
Language selection
  ↓
Consent + identity/session
  ↓
Chief complaint in natural language
  ↓
Adaptive structured questioning
  ↓
Voice OR touch at every step
  ↓
Clinical facts stored with provenance
  ↓
Red-flag safety rules run continuously
  ↓
Old prescriptions/reports uploaded
  ↓
OCR + entity extraction + timeline
  ↓
Patient review / correction
  ↓
Doctor receives structured draft
  ↓
Doctor checks source evidence
  ↓
Doctor edits/confirms
  ↓
FHIR bundle prepared for HIS
  ↓
Audit trail + session teardown
```

The upgrade must make it obvious that this is a **clinical workflow product**, not just a questionnaire.

---

# 3. NON-NEGOTIABLE SAFETY AND ARCHITECTURAL INVARIANTS

These rules override all feature requests.

## 3.1 Never diagnose

The system may collect and structure symptoms, duration, severity, history, medications, allergies, investigations, explicitly stated prior conditions, prior document information and AYUSH intake parameters.

It must **never** output a diagnosis, likely disease, disease probability, differential diagnosis, treatment recommendation, medication recommendation, clinical reassurance such as "you are safe", or low-risk discharge advice.

The physician diagnoses.

## 3.2 Provenance or nothing

Every clinical fact must have a source. Create a single write path such as `record_fact(...)`. No clinical field can enter the structured record except through this function/service.

Each fact should store:

```text
fact_id
field_name
normalized_value
raw_value
source_type
source_text
source_id
source_page
source_bbox
confidence
provenance_tier
timestamp
confirmed_by_patient
confirmed_by_physician
```

Allowed provenance tiers:
- `stated`
- `confirmed`
- `document`

If there is no source:
- `not_asked`
- `declined`
- `unknown`

Do **not infer** missing facts.

## 3.3 Red flags only escalate

The system may detect predefined emergency warning patterns. It may flag, escalate, notify triage, or move a case upward in priority.

It must never downgrade urgency, label a patient "low risk", or tell a patient an emergency is ruled out.

Use a **deterministic rules engine** for final red-flag decisions. An LLM may extract symptoms or propose a candidate flag, but the rule engine decides whether the flag fires. Log every evaluation.

## 3.4 Physician is the committer

The generated doctor summary is always:

> **DRAFT — Requires physician review**

Nothing is considered final until a physician explicitly confirms it. FHIR/HIS push must be disabled until physician confirmation.

## 3.5 Codes are retrieved, never generated

If you emit terminology codes:
- retrieve them from a version-pinned CodeSystem;
- never ask an LLM to invent them;
- return `unmapped` when no validated mapping exists.

`unmapped` is a successful and valid result.

## 3.6 Consent gates capture

No audio, document processing, clinical fact storage, or external AI call should occur before the relevant consent is granted.

Consent should be granular, revocable, understandable, available as text and audio, and logged.

## 3.7 Synthetic data only

For development, testing, screenshots and demos, use synthetic patients and synthetic prescriptions/reports. Never put real patient records in the repo.

---

# 4. FIRST TASK — AUDIT THE EXISTING APP BEFORE CHANGING CODE

Do not immediately start rewriting.

First inspect the repository and produce:

```text
docs/CURRENT_STATE.md
```

It must include:

## 4.1 Existing functionality

Document:
- current frontend framework;
- current backend;
- database;
- current question flow;
- current 28 questions;
- summary generation logic;
- API routes;
- session/state handling;
- styling system;
- current dependencies;
- any AI integrations;
- existing tests.

## 4.2 Reuse map

Create a table:

| Existing component | Keep | Refactor | Replace | Reason |
|---|---:|---:|---:|---|
| 28-question form | | | | |
| Summary page | | | | |
| Backend models | | | | |
| UI components | | | | |
| AI service | | | | |

## 4.3 Gap analysis

Compare the current app against this prompt and mark every requirement:
- DONE
- PARTIAL
- MISSING
- BLOCKED

Do not delete working functionality unless the new architecture replaces it cleanly.

---

# 5. TARGET PRODUCT EXPERIENCE

The first screen should make the product immediately understandable.

Example:

```text
MediKiosk
Your health history, ready before you meet the doctor.

[ Start Intake ]

Speak or tap in your preferred language.
No diagnosis is made by this system.
```

Show a short visual 3-step explanation:

```text
1. Tell us what brings you here
2. Review your history and old records
3. Doctor receives a structured summary
```

Do not overwhelm the patient with technical words such as FHIR, ABHA, NLP or LLM.

---

# 6. LANGUAGE-FIRST EXPERIENCE

The language selector must be a major first-class feature.

Suggested initial demo support:
- English
- Hindi
- Tamil

The architecture must support adding more languages later.

Create a `SpeechBackend` abstraction and a `TranslationBackend` abstraction.

```text
SpeechBackend
├── OfflineSpeechBackend
└── BhashiniSpeechBackend
```

```text
TranslationBackend
├── Local/MockTranslationBackend
└── BhashiniTranslationBackend
```

The application must still demo if BHASHINI credentials or internet fail.

A patient can:
- hear the question;
- speak the answer;
- tap/select an answer;
- type if needed;
- switch between input modes at any question.

Never force the patient to restart because they switch modes.

---

# 7. ACCESSIBILITY / LOW-LITERACY MODE

Create an optional **Simple Mode / Assisted Mode** with:
- very large buttons;
- minimal text;
- icons;
- audio playback of every question;
- repeat-question button;
- slow-speech option;
- clear progress;
- high contrast;
- one question per screen;
- no dense forms;
- "I don't know";
- "Skip";
- "Ask attendant for help".

Do not rely only on typing.

---

# 8. REPLACE THE FIXED 28-QUESTION FORM WITH AN ADAPTIVE HISTORY ENGINE

The current 28 questions can remain as a structured ontology/reference, but the patient should no longer see all 28 in the same sequence.

Build a deterministic state machine.

High-level flow:

```text
Chief complaint
    ↓
Complaint-specific HPI
    ↓
SOCRATES when relevant
    ↓
Associated symptoms
    ↓
Past medical/surgical history
    ↓
Medication history
    ↓
Allergies
    ↓
Family history
    ↓
Personal history
    ↓
Review of systems
    ↓
Context-specific follow-ups
```

The LLM must **not** decide the next clinical topic.

The state machine decides what section/question comes next.

The LLM may only:
1. extract structured slot values from free speech/text;
2. rephrase the deterministic next question naturally.

---

# 9. SOCRATES-STYLE HISTORY

For pain/symptom complaints where appropriate, support:
- Site
- Onset
- Character
- Radiation
- Associated symptoms
- Timing/duration
- Exacerbating factors
- Relieving factors
- Severity

Do not mechanically ask irrelevant questions.

For example, if the patient says "I have a cough for three days", do not ask pain radiation.

Use complaint-aware branching.

---

# 10. SMART BRANCHING

Examples:

### Example A
Patient: "I have chest pain."

Activate:
- pain SOCRATES branch;
- cardiac/respiratory associated-symptom branch;
- deterministic red-flag evaluation.

### Example B
Patient: "I came for follow-up and I have no new complaints."

Do not force a full acute-pain flow.

### Example C
Patient explicitly says: "I have no allergies."

Store:
```text
allergies = none reported
provenance = confirmed
```

Do not ask the same question repeatedly.

---

# 11. CONTRADICTION HANDLING

If a patient says:

> "I don't take any medicines."

and later a document shows:

> Metformin 500 mg

do not silently overwrite either source.

Create:

```text
CONTRADICTION
Patient stated: no current medicines
Document extracted: Metformin 500 mg
```

Ask a clarification question where appropriate and surface unresolved contradictions to the doctor.

Store both source records.

Suggested model:

```text
Contradiction
fact_a_id
fact_b_id
status
resolution_source
resolved_by
```

---

# 12. CONTINUOUS RED-FLAG ENGINE

Do not wait until final submit.

Evaluate relevant red-flag rules as new facts arrive.

Patient-facing wording should remain conservative:

> **This response may require urgent staff attention. Please wait for a healthcare professional.**

Physician/triage view should show:

```text
RED FLAG
Rule: RF-RESP-003
Evidence:
- "I cannot breathe properly"
- onset: sudden
Source: patient statement
```

Never display a diagnostic label.

---

# 13. DOCUMENT UPLOAD AND OCR

Add a document intake step.

Allow:
- prescription image;
- lab report image/PDF;
- discharge summary;
- prior medical report.

Pipeline:

```text
Upload
  ↓
Document type detection
  ↓
OCR
  ↓
Entity extraction
  ↓
Confidence tagging
  ↓
Patient verification where needed
  ↓
Timeline event creation
```

Create an `OCRBackend` interface.

Initial implementation should work well with **printed documents**.

Handwriting must use a separate low-confidence lane and must never be silently merged into the record.

---

# 14. DOCUMENT ENTITY EXTRACTION

Extract only supported structured fields.

### Prescription
- medicine name;
- strength;
- frequency;
- duration;
- prescribing date if present.

### Lab report
- investigation name;
- value;
- unit;
- reference range;
- report date.

### Discharge/clinical document
- stated prior diagnosis;
- procedure;
- admission/discharge date;
- medication.

Every extracted entity must point to:
- document;
- page;
- source text;
- bounding box when available;
- confidence.

---

# 15. CHRONOLOGICAL MEDICAL TIMELINE

Create an interactive physician timeline.

Example:

```text
2024
│
├── Jan 12 — Prescription
│   Metformin 500 mg
│
2025
│
├── Aug 08 — Lab report
│   HbA1c: ...
│
2026
│
└── Aug 24 — Current intake
    Chief complaint: ...
```

Timeline cards should be clickable.

Clicking a timeline item should show:
- original document preview;
- extracted text;
- confidence;
- relevant structured facts.

---

# 16. PATIENT REVIEW BEFORE SUBMISSION

Before the session reaches the doctor, show the patient a simple review screen.

Example:

```text
You told us:

Main problem:
Chest discomfort

Started:
This morning

Medicines:
None reported

Allergies:
Penicillin

[Correct]
[Edit]
```

This is a patient-friendly confirmation screen, not the doctor summary.

Let the patient correct transcription mistakes.

---

# 17. PHYSICIAN DASHBOARD

Build a separate doctor surface.

It must feel completely different from the kiosk.

The doctor should be able to:
- read the summary;
- see missing fields;
- see declined/not-asked fields;
- inspect red flags;
- inspect contradictions;
- inspect source evidence;
- play/review relevant utterance if stored for demo;
- view original document area;
- edit any field;
- confirm a fact;
- reject an extracted fact;
- confirm final summary.

Suggested layout:

```text
┌────────────────────────────────────────────┐
│ Patient / Session       Priority / Status  │
├─────────────┬──────────────────────────────┤
│ Sections    │ Clinical Summary             │
│ Complaint   │                              │
│ HPI         │                              │
│ Past hx     │                              │
│ Drugs       │                              │
│ Allergies   │                              │
│ ROS         │                              │
│ Documents   │                              │
│ Timeline    │                              │
├─────────────┴──────────────────────────────┤
│ Source / Evidence Drawer                   │
└────────────────────────────────────────────┘
```

---

# 18. CLICK-TO-SOURCE SUMMARY

Every clinical line in the doctor summary must be clickable.

Example:

> Chest pain started this morning, severity 7/10.

Click it and open:

```text
Source: Patient speech
Original: "Since morning my chest is hurting... around seven out of ten."
Confidence: 0.94
Provenance: stated
Captured: 10:42
```

For document facts:

```text
Source: Prescription
Page: 1
Text: "Metformin 500 mg BD"
Bounding box: [...]
Confidence: 0.88
```

A summary claim without source evidence must fail validation.

---

# 19. STRUCTURED DOCTOR SUMMARY

Use deterministic section assembly.

Suggested sections:
1. Chief complaint
2. History of present illness
3. Associated symptoms
4. Past medical history
5. Past surgical history
6. Medication history
7. Allergy history
8. Family history
9. Personal history
10. Review of systems
11. Previous-record timeline highlights
12. Red-flag alerts
13. Information requiring verification
14. Unanswered/declined areas

The LLM may polish prose, but it must not introduce new facts.

Before summary output:

```text
summary_claim
    ↓
resolve to recorded fact(s)
    ↓
if no evidence
    ↓
FAIL GENERATION
```

---

# 20. CONFIDENCE AS A HUMAN-REVIEW TOOL

Use confidence to route verification, not hide data.

Example labels:
- High confidence
- Verify
- Low-confidence OCR

Low-confidence items should be visually obvious.

Never auto-delete them.

---

# 21. AYUSH MODE

Add a clear intake choice:

```text
Consultation type
[ General Clinical Intake ]
[ AYUSH / Ayurveda Intake ]
```

AYUSH mode should extend, not replace, general history.

Capture structured Dashavidha Pariksha fields such as:
- Prakriti
- Vikriti
- Sara
- Samhanana
- Pramana
- Satmya
- Sattva
- Ahara Shakti
- Vyayama Shakti
- Vaya

Also support Ahara-Vihara history.

Do not invent terminology codes. Retrieve and validate them; otherwise return `unmapped`.

---

# 22. ABHA / ABDM DEMO FLOW

Use a mock/demo integration unless production credentials already exist.

```text
Enter ABHA ID / Demo ABHA
  ↓
Mock verification
  ↓
Identity/session created
  ↓
Consent request
```

Do not make the entire product depend on unavailable sandbox credentials.

---

# 23. GRANULAR CONSENT

Create a real consent screen, not one checkbox.

Example:

```text
MediKiosk requests permission to:

[x] Collect today's symptom history
[x] Use microphone for this session
[x] Process uploaded medical documents
[x] Share the generated draft with the assigned doctor
[ ] Store audio after the session

[Listen to explanation]
[Continue]
```

Show the explanation in the selected language.

A denied optional permission must not break unrelated parts.

---

# 24. FHIR R4 / HIS INTEROPERABILITY

After physician confirmation, build a FHIR bundle representing supported information.

Possible resources:
- Patient
- Encounter
- Condition only when representing explicitly documented prior conditions, not AI diagnosis
- Observation
- AllergyIntolerance
- MedicationStatement
- QuestionnaireResponse where appropriate
- DocumentReference
- Provenance

Add a jury/developer view:

```text
[ View FHIR Bundle ]
[ Send to Demo HIS ]
```

A stub receiver is enough.

Show success only when it actually succeeds.

---

# 25. AUDIT TRAIL

Generate audit events for:
- consent granted/revoked;
- question asked;
- clinical fact recorded;
- fact edited;
- AI extraction call;
- OCR call;
- red flag proposed;
- red flag fired;
- doctor correction;
- physician confirmation;
- FHIR export;
- session purge.

Where practical, use a hash-chained log.

Expose `Audit chain: VALID` only in the evaluator/developer view.

---

# 26. SESSION PRIVACY / TEARDOWN

Sessions should have:
- TTL;
- explicit submit/end;
- purge state;
- revocable consent.

On completion, show that temporary capture data has been cleared according to policy.

---

# 27. CAREGIVER / ASSISTED INPUT MODE

Add:

```text
Who is answering?
[ Patient ]
[ Caregiver / Attendant ]
```

Facts must preserve `source_role = patient` or `source_role = caregiver`.

Do not present caregiver statements as direct patient statements.

---

# 28. INTERRUPTION AND RESUME

Support:
- accidental refresh recovery;
- session resume;
- timeout warning;
- secure restart;
- no loss of confirmed facts.

Do not keep sensitive data indefinitely.

---

# 29. QUESTION PROGRESS WITHOUT A FAKE PERCENTAGE

Because dialogue is adaptive, avoid "Question 12 of 28".

Use section-based progress:

```text
Complaint ✓
Current history ●
Past history
Medicines
Allergies
Review
```

---

# 30. ASK-LESS PRINCIPLE

Before asking a question, check whether the field is already stated, confirmed, or available in verified document data.

If yes, skip it or ask only for confirmation when necessary.

Track:
```text
questions_skipped_due_to_existing_fact
```

---

# 31. SUMMARY COMPLETENESS VIEW

On the physician screen show intake-data completeness:

```text
Chief complaint        Complete
HPI                    Complete
Medication history     Verify
Allergy history        Complete
Family history         Declined
ROS                     Partial
```

Do not imply diagnostic sufficiency.

---

# 32. MISSING / DECLINED ARE FIRST-CLASS STATES

These are different:
- No known allergy
- Allergy question not asked
- Patient declined to answer
- Patient does not know

Store and render them differently.

---

# 33. DEMO MODE — ABSOLUTELY BUILD THIS

Create `/demo` with synthetic cases.

At minimum:

### Demo 1 — Multilingual acute complaint
- Tamil or Hindi speech/text;
- adaptive questions;
- red-flag rule demonstrated if appropriate;
- structured doctor summary.

### Demo 2 — Document timeline
- upload synthetic printed prescription/report;
- OCR;
- extracted data;
- timeline;
- click-to-source.

### Demo 3 — Contradiction
- patient says no medicines;
- document contains a medicine;
- system surfaces contradiction.

### Demo 4 — AYUSH
- Dashavidha data capture;
- structured result;
- terminology retrieval/unmapped demonstration.

### Demo 5 — Normal non-red-flag flow
Prove the system does not over-alert every case.

Add a "Load synthetic demo case" button so judges do not have to manually type everything.

---

# 34. JURY MODE

Add an unobtrusive developer/jury drawer available only in demo mode.

It can show:
- current state-machine node;
- detected structured facts;
- provenance count;
- red-flag rules evaluated;
- FHIR resources generated;
- audit chain state;
- service backend currently in use;
- speech backend fallback status;
- latency.

This makes hidden engineering visible without polluting patient UX.

---

# 35. EVALUATION HARNESS

Create:

```text
eval/
```

Use synthetic cases only.

Start with at least 20 well-designed cases if 50 is not immediately feasible, then grow toward 50.

Cover:
- simple complaints;
- rambling descriptions;
- contradictory statements;
- multilingual phrasing;
- low-literacy phrasing;
- skipped questions;
- noisy ASR fixtures;
- printed documents;
- low-confidence OCR;
- emergency/red-flag cases;
- non-emergency cases.

## Hard safety metrics

```text
Unsupported summary claims = 0
Facts without provenance = 0
FHIR export before physician confirmation = 0
Clinical capture before required consent = 0
Generated terminology codes = 0
```

These should be enforced by tests.

## Quality metrics

Track:
- extraction precision;
- extraction recall;
- per-field accuracy;
- history section completeness vs gold;
- red-flag sensitivity;
- red-flag false-positive rate;
- ASR fallback frequency;
- OCR field accuracy;
- contradiction detection accuracy;
- average questions asked;
- questions avoided through adaptive branching;
- time to physician-ready draft;
- summary generation latency.

Create `docs/EVALUATION.md`.

Do not invent performance numbers. Display only measured results.

---

# 36. WINNING DIFFERENTIATORS TO MAKE OBVIOUS

A judge should understand these within two minutes:

1. **Not a fixed form** — question flow adapts.
2. **Not just a chatbot** — state machine and rules own the workflow.
3. **Every claim is traceable** — click summary lines to see exact evidence.
4. **Multilingual + multimodal** — speak or tap, switch anytime.
5. **Safety by construction** — no diagnosis, deterministic red flags, doctor confirmation, consent gates.
6. **Previous records become usable** — OCR + extraction + timeline + verification.
7. **Interoperability is real** — FHIR bundle + mock HIS receiver.
8. **AYUSH is first-class** — Dashavidha workflow, not one extra text box.
9. **The system is measured** — evaluation harness with real synthetic-test metrics.

---

# 37. VISUAL DESIGN DIRECTION

## Patient side
Use a calm healthcare-oriented design:
- large touch targets;
- minimal reading load;
- one obvious next action;
- multilingual-friendly;
- accessible;
- subtle progress.

Avoid:
- tiny text;
- dense navbars;
- many cards per screen;
- "AI magic" language;
- excessive animation;
- cyberpunk styling.

## Doctor side
Use an information-dense clinical review design:
- fast scanning;
- section hierarchy;
- keyboard-friendly;
- visible provenance/confidence;
- timeline;
- alerts;
- source drawer.

---

# 38. RECOMMENDED FRONTEND ROUTES

Adapt to the existing router when appropriate:

```text
/
 /start
 /language
 /consent
 /identity
 /intake
 /documents
 /review
 /complete

 /doctor
 /doctor/session/:id

 /demo
 /evaluation
```

---

# 39. RECOMMENDED DOMAIN MODELS

Cover these concepts:

```text
PatientSession
ConsentRecord
ClinicalFact
SourceEvidence
DialogueState
QuestionEvent
DocumentRecord
ExtractedDocumentEntity
TimelineEvent
Contradiction
RedFlagEvent
DraftSummary
SummaryClaim
PhysicianDecision
FHIRExport
AuditEvent
```

---

# 40. API CONTRACT DIRECTION

Possible endpoints:

```text
POST   /api/sessions
GET    /api/sessions/{id}

POST   /api/sessions/{id}/consent
POST   /api/sessions/{id}/consent/revoke

POST   /api/sessions/{id}/answers
GET    /api/sessions/{id}/next-question

POST   /api/sessions/{id}/speech/transcribe
POST   /api/sessions/{id}/speech/synthesize

POST   /api/sessions/{id}/documents
GET    /api/sessions/{id}/timeline

GET    /api/sessions/{id}/facts
GET    /api/sessions/{id}/contradictions
GET    /api/sessions/{id}/red-flags

POST   /api/sessions/{id}/summary/generate
GET    /api/sessions/{id}/summary

POST   /api/doctor/sessions/{id}/facts/{fact_id}/confirm
POST   /api/doctor/sessions/{id}/facts/{fact_id}/reject
POST   /api/doctor/sessions/{id}/summary/confirm

GET    /api/doctor/sessions/{id}/fhir
POST   /api/doctor/sessions/{id}/fhir/push

GET    /api/audit/{session_id}/verify

GET    /api/demo/cases
POST   /api/demo/cases/{case_id}/load
```

There must be **no diagnosis endpoint**.

---

# 41. SERVICE ABSTRACTIONS

Create clean boundaries:

```python
class SpeechBackend(Protocol):
    ...

class TranslationBackend(Protocol):
    ...

class OCRBackend(Protocol):
    ...

class LLMBackend(Protocol):
    ...

class IdentityProvider(Protocol):
    ...

class FHIRTransport(Protocol):
    ...

class TerminologyProvider(Protocol):
    ...
```

Ship demo-safe implementations for each.

---

# 42. OFFLINE / NETWORK FAILURE STRATEGY

A hackathon demo must not collapse because one API is down.

Required fallback behavior:

```text
BHASHINI unavailable
→ switch to offline/mock speech backend
→ keep intake working

LLM unavailable
→ deterministic question text
→ typed/touch input remains functional

OCR backend unavailable
→ document upload accepted
→ mark processing unavailable
→ core intake still works

FHIR receiver unavailable
→ generate/validate bundle locally
→ show pending push state
```

Do not silently fake success.

---

# 43. ERROR HANDLING

Patient-facing errors should be simple.

Bad:
```text
500 UnprocessableEntity PydanticValidationError
```

Good:
> We couldn't understand that answer. Please say it again or tap an option.

Keep technical detail in developer logs.

---

# 44. TESTS THAT MUST EXIST

## Provenance
- fact without source is rejected;
- summary claim without fact is rejected.

## Dialogue
- fixed ontology path works without AI;
- irrelevant branches are skipped;
- known facts are not repeatedly asked.

## Red flags
- emergency evidence can escalate;
- no rule can de-escalate;
- no diagnostic label appears.

## Consent
- no audio capture before microphone consent;
- no document processing before document consent;
- revocation stops future capture.

## Summary
- no unsupported claims;
- missing fields remain missing;
- declined remains declined.

## Codes
- unknown terminology returns unmapped;
- no arbitrary LLM-generated code passes validation.

## FHIR
- export blocked before physician confirmation;
- confirmed session produces valid supported bundle.

## OCR
- low-confidence extraction enters verification lane.

## Contradictions
- conflicting patient/document facts are both retained;
- unresolved conflict is visible to physician.

---

# 45. DEVELOPMENT PHASES

## Phase 0 — Audit and stabilize
Deliver:
- `docs/CURRENT_STATE.md`
- architecture map;
- tests for current functionality;
- refactor plan;
- working dev command.

Do not break the existing 28-question flow yet.

## Phase 1 — Domain model + provenance
Deliver:
- `ClinicalFact`;
- `SourceEvidence`;
- `record_fact()`;
- missing/declined states;
- unit tests.

## Phase 2 — Adaptive deterministic dialogue
Replace fixed sequence with state-machine branching. The current 28 questions become ontology/fallback/reusable prompts.

## Phase 3 — New patient UI
Deliver landing, language, consent, one-question-per-screen conversation, touch/text input, accessibility and patient review.

## Phase 4 — Voice + multilingual
Deliver backend protocols, offline/demo backend, BHASHINI adapter, speech/touch switching and low-confidence fallback.

## Phase 5 — Red flags + contradictions
Deliver deterministic rule engine, continuous evaluation, escalation alert and contradiction handling.

## Phase 6 — Documents + timeline
Deliver upload, OCR, printed-document extraction, confidence lane, interactive timeline and source preview.

## Phase 7 — Doctor dashboard
Deliver structured history, evidence drawer, click-to-source, edit/confirm/reject, completeness, red flags, contradictions and timeline.

## Phase 8 — Summary traceability
Deliver deterministic assembly, optional prose smoothing, hard provenance validation, draft status and physician confirmation.

## Phase 9 — AYUSH
Deliver AYUSH mode, Dashavidha, Ahara-Vihara, terminology retrieval and unmapped handling.

## Phase 10 — ABHA/FHIR/audit
Deliver mock ABHA, consent audit, FHIR bundle, demo HIS endpoint, audit chain and session teardown.

## Phase 11 — Evaluation + jury mode
Deliver synthetic gold cases, metrics, evaluation report, demo presets, jury drawer and polished 90-second demo.

---

# 46. MVP PRIORITY IF TIME IS SHORT

Prioritize this exact vertical slice:

```text
1. Language selection
2. Consent
3. Adaptive text/touch intake
4. One voice language working
5. Provenance-backed facts
6. Red-flag deterministic rule
7. One printed prescription OCR
8. Timeline
9. Doctor dashboard
10. Click-to-source summary
11. Physician confirmation
12. FHIR bundle preview
13. One-click demo case
14. Evaluation metrics from synthetic tests
```

Cut breadth before correctness.

---

# 47. 90-SECOND HACKATHON DEMO TARGET

## 0–10 sec
Open MediKiosk. Judge sees "Speak or tap in your preferred language." Select Tamil/Hindi/English.

## 10–30 sec
Patient gives a synthetic complaint. System transcribes, extracts facts, asks adaptive follow-ups and shows mode switching.

## 30–40 sec
Demonstrate one deterministic red-flag case or a normal-path case. If red flag, show "Healthcare staff attention requested." No diagnosis.

## 40–55 sec
Upload a synthetic printed prescription. Extract medicine/date/relevant entities and show timeline.

## 55–70 sec
Switch to doctor screen. Show structured summary, timeline, confidence, contradiction/red flag if present.

## 70–80 sec
Click one summary sentence and show the exact patient utterance/document source.

## 80–90 sec
Doctor confirms. Open FHIR preview. Show demo HIS acceptance and audit validity. Finish with measured evaluation metrics.

---

# 48. WHAT NOT TO BUILD

Do not waste time on:
- diagnosis prediction;
- treatment recommendation;
- symptom-to-specialty recommendation unless the official PS explicitly requires it;
- full hospital ERP;
- billing;
- appointment booking;
- pharmacy ordering;
- insurance claims;
- production-grade ABHA infrastructure if credentials are unavailable;
- kiosk hardware drivers;
- blockchain gimmicks;
- generic AI chatbot page;
- large analytics dashboards unrelated to intake;
- real patient data.

---

# 49. SUCCESS CRITERIA

- [ ] Original fixed 28-question sequence is no longer the default experience.
- [ ] Question flow changes based on patient answers.
- [ ] Full intake works without an LLM.
- [ ] Voice and touch can be switched mid-session.
- [ ] At least one multilingual voice path works.
- [ ] Consent is visible and enforced.
- [ ] Every stored clinical fact has provenance.
- [ ] Missing/declined/unknown are distinct.
- [ ] Red flags are deterministic and escalation-only.
- [ ] At least one printed document can be processed.
- [ ] Extracted document data has source/confidence.
- [ ] A chronological timeline exists.
- [ ] Contradictory information is not silently overwritten.
- [ ] Doctor sees a separate review dashboard.
- [ ] Summary lines are click-to-source.
- [ ] Summary is marked draft.
- [ ] Physician can confirm/reject facts.
- [ ] FHIR export is blocked until physician confirmation.
- [ ] A valid demo FHIR bundle can be viewed.
- [ ] AYUSH mode captures structured Dashavidha information.
- [ ] Terminology codes are validated/retrieved, never invented.
- [ ] Synthetic evaluation cases run automatically.
- [ ] No unsupported summary claim can pass tests.
- [ ] Demo mode can load a complete case in one click.
- [ ] The 90-second jury demo works even if external APIs fail.

---

# 50. HOW TO WORK ON THIS REPOSITORY

1. Read this entire prompt before editing.
2. Read the existing repository.
3. Read the original SIH26047 brief already supplied to you.
4. Produce `docs/CURRENT_STATE.md`.
5. Produce a concrete migration plan.
6. Preserve working pieces when they fit the new architecture.
7. Refactor rather than duplicate.
8. Keep components small and independently testable.
9. Add tests at the same time as features.
10. Run lint/typecheck/tests at each phase.
11. Commit at phase boundaries.
12. Never silently fake a successful external integration.
13. If a required credential is unavailable, implement the interface + mock/demo backend and continue.
14. Prefer deterministic logic for safety-critical workflow.
15. Use the LLM only where language flexibility adds value.
16. Do not introduce unsupported medical reasoning.
17. Use synthetic data in fixtures and screenshots.
18. Maintain a `docs/DECISIONS.md` or ADR directory for non-obvious architecture choices.

---

# 51. FIRST RESPONSE I EXPECT FROM YOU

Before writing code, respond with:

## A. Current-state audit
Tell me:
- what the current app already does;
- how the 28-question flow is implemented;
- where summary generation happens;
- current frontend/backend architecture;
- what can be reused.

## B. Gap table
For every major requirement:
```text
DONE / PARTIAL / MISSING / BLOCKED
```

## C. Implementation plan
Give the exact files/modules you plan to create, modify, remove or migrate.

## D. First vertical slice
Recommend the smallest upgrade that turns the existing form into something visibly different and more compelling.

Do **not** begin a full rewrite before showing this audit and plan.

---

# 52. PRODUCT POSITIONING TO KEEP IN MIND

MediKiosk should not be presented as:

> "An AI chatbot that asks medical questions."

It should be presented as:

> **A multilingual pre-consultation clinical intake layer that converts patient speech, touch responses and prior documents into a structured, source-verifiable history for physician review — with deterministic safety checks, consent controls, AYUSH support and standards-based interoperability.**

The winning story is not "we used AI."

The winning story is:

> **We reduce avoidable history-taking friction without taking clinical authority away from the doctor.**

Build the product so that this is visible in the demo, architecture and evaluation — not only written on a slide.

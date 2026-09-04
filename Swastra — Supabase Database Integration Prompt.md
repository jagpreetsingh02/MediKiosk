# Swastra — Supabase Database Integration

The Swastra project will now use **Supabase PostgreSQL as its primary persistent database**.

The Supabase project is already connected/available in this Claude Code environment.

Do not create a new Supabase project.

Do not throw away working Swastra code.

Do not restart the application architecture.

Your job is to inspect the existing persistence layer and safely migrate/extend it so that **Supabase becomes the durable database for Swastra's longitudinal patient-memory architecture**.

---

# 1. FIRST — INSPECT BEFORE MODIFYING

Before making database changes, inspect:

- current SQLAlchemy models;
- current SQLite configuration;
- current Postgres configuration;
- Alembic setup;
- current session tables;
- current consent tables;
- current audit tables;
- current submitted FHIR bundle storage;
- Redis/in-memory session state;
- any pgvector configuration;
- existing migrations;
- existing Supabase connection/configuration;
- environment variables already provided by the connected Supabase setup.

Report briefly:

```text
Current database:
Current ORM:
Current migration system:
Current durable tables:
Current temporary/session tables:
Current Supabase connection status:
Database work already completed in the current phase:
```

Do not assume.

Inspect the actual repository and connected Supabase project.

---

# 2. DATABASE ROLE IN MEDIKIOSK

Supabase should be the **durable longitudinal clinical store**.

It should store confirmed structured information such as:

```text
Patient
    ↓
Encounter
    ↓
Clinical facts
Source evidence
Documents
Medication events
Observations
Timeline events
Contradictions
Red-flag events
Physician decisions
FHIR exports
Consent/audit records
```

Supabase should **not automatically become permanent storage for every temporary artifact**.

Keep the separation:

```text
TEMPORARY CAPTURE

raw audio
temporary ASR chunks
in-progress dialogue state
unconfirmed extraction
temporary OCR processing
temporary session cache

        ↓ physician confirmation

DURABLE SUPABASE RECORD

Patient
Encounter
Confirmed ClinicalFacts
SourceEvidence
Document metadata/references
MedicationEvents
ObservationEvents
TimelineEvents
PhysicianDecision
FHIR export metadata
Audit records
```

---

# 3. SUPABASE IS THE LONGITUDINAL MEMORY

The application must support:

```text
Patient
│
├── Encounter 1
│
├── Encounter 2
│
├── Encounter 3
│
└── Current Encounter
```

When the same patient returns later, Swastra should be able to load:

- previous visits;
- previous structured symptoms;
- previous medications;
- previous uploaded records;
- laboratory history;
- previous physician-confirmed summaries;
- similar historical encounters;
- longitudinal timeline.

Do not use one summary JSON blob as the main patient record.

Use relational structured records.

---

# 4. DO NOT REPLACE THE BACKEND WITH DIRECT FRONTEND DATABASE WRITES

The existing FastAPI backend should remain the clinical/service boundary.

Preferred architecture:

```text
React frontend
      ↓
FastAPI backend
      ↓
SQLAlchemy/service layer
      ↓
Supabase PostgreSQL
```

Do not make the React frontend directly insert clinical records into Supabase tables just because the Supabase JavaScript client exists.

Clinical writes should continue to pass through backend validation, provenance, authorization and business rules.

---

# 5. SUPABASE AUTH

Do not automatically replace the current mock ABHA/authentication architecture with Supabase Auth.

Supabase is currently being adopted primarily as:

> **database + storage infrastructure**

Keep identity concerns separated.

Current/demo ABHA identity should remain conceptually distinct from database authentication.

If Supabase Auth is already being used somewhere, report it before changing anything.

Do not silently introduce a second conflicting patient identity system.

---

# 6. REQUIRED DURABLE TABLES

Inspect existing tables first.

Reuse/migrate them where appropriate.

Target conceptual schema:

## patients

```text
id UUID PK
created_at
updated_at
status
```

Do not store unnecessary identifying information in hackathon synthetic fixtures.

---

## patient_identifiers

```text
id UUID PK
patient_id FK
identifier_type
identifier_value / safe reference
issuer
is_primary
created_at
```

For demo ABHA:

```text
identifier_type = "ABHA_DEMO"
```

Do not put production credentials/secrets here.

---

## encounters

```text
id UUID PK
patient_id FK
capture_session_id nullable
encounter_type
consultation_type
started_at
ended_at
status
language
physician_confirmed_at
created_at
updated_at
```

Suggested statuses:

```text
draft
awaiting_physician
confirmed
cancelled
```

---

## clinical_facts

```text
id UUID PK
patient_id FK
encounter_id FK

field_name
normalized_value JSONB
raw_value

fact_state
provenance_tier
confidence nullable

created_at
patient_confirmed
physician_confirmed
superseded_by nullable
```

Fact states must distinguish:

```text
stated
confirmed
document
unknown
not_asked
declined
```

---

## source_evidence

```text
id UUID PK
clinical_fact_id FK
encounter_id FK

source_type
source_text
source_language

audio_reference nullable
document_id nullable
page_number nullable
bounding_box JSONB nullable

confidence nullable
created_at
```

A clinical fact must not become durable without valid provenance unless it represents a valid explicit state such as:

```text
unknown
declined
not_asked
```

---

# 7. DOCUMENT TABLES

## documents

```text
id UUID PK
patient_id FK
encounter_id FK

document_type
original_filename
mime_type
storage_reference
document_date nullable

ocr_status
verification_status

created_at
```

---

## extracted_document_entities

```text
id UUID PK
document_id FK
encounter_id FK

entity_type
normalized_value JSONB
raw_text

page_number
bounding_box JSONB
ocr_confidence
extraction_confidence

verification_status
verified_by nullable
created_at
```

Possible entity types:

```text
medication
lab_observation
procedure
historical_condition
date
```

Do not silently convert uncertain OCR entities into confirmed clinical facts.

---

# 8. MEDICATION HISTORY

Create/retain a structured medication event model.

## medication_events

```text
id UUID PK
patient_id FK
encounter_id FK
clinical_fact_id nullable
document_entity_id nullable

medication_name
strength nullable
frequency nullable
duration nullable

event_type
status
event_date nullable

source_type
created_at
```

Possible statuses:

```text
documented
historical
patient_reported_current
patient_reported_stopped
uncertain
```

Do not infer that:

```text
prescribed = currently taking
```

Those are different concepts.

---

# 9. OBSERVATIONS / LAB HISTORY

## observation_events

```text
id UUID PK
patient_id FK
encounter_id FK
document_entity_id nullable

observation_name
value
unit nullable
reference_range nullable
observed_at nullable

source_type
created_at
```

The doctor should eventually be able to retrieve:

```text
same observation
→ across dates
→ chronological trend
```

Do not generate values for missing dates.

---

# 10. TIMELINE

Create a durable timeline representation or projection.

Prefer deriving timeline items from structured events when practical rather than duplicating everything.

Conceptually:

```text
timeline event
├── encounter
├── prescription
├── medication
├── lab
├── document
├── procedure
├── AYUSH observation
└── alert
```

API should support something equivalent to:

```text
GET /api/patients/{patient_id}/timeline
```

with ordering by event date/time.

---

# 11. CONTRADICTIONS

Persist unresolved clinically relevant source conflicts.

## contradictions

```text
id UUID PK
patient_id FK
encounter_id FK

fact_a_id
fact_b_id

contradiction_type
status

resolution_text nullable
resolved_by nullable
resolved_at nullable

created_at
```

Never automatically overwrite one source with another.

---

# 12. RED-FLAG EVENTS

Persist the deterministic rule result.

## red_flag_events

```text
id UUID PK
patient_id FK
encounter_id FK

rule_id
rule_version
status

evidence_fact_ids JSONB
triggered_at

resolved_by nullable
resolution_note nullable
```

Do not store AI-generated disease predictions.

---

# 13. PHYSICIAN DECISIONS

## physician_decisions

```text
id UUID PK
patient_id FK
encounter_id FK

decision_type
decision_payload JSONB
physician_reference
created_at
```

Examples:

```text
fact_confirmed
fact_rejected
fact_edited
encounter_confirmed
```

---

# 14. FHIR EXPORTS

## fhir_exports

```text
id UUID PK
patient_id FK
encounter_id FK

fhir_version
bundle JSONB

status
target
external_reference nullable

created_at
pushed_at nullable
```

FHIR export must only be generated/finalized according to the existing physician-confirmation rule.

---

# 15. AUDIT DATA

Keep/extend the existing audit chain.

If existing `AuditEvent` tables are good, migrate rather than recreate them.

Audit:

```text
consent
fact creation
fact modification
OCR processing
physician confirmation
FHIR generation
FHIR push
session promotion
session purge
```

---

# 16. TEMPORARY CAPTURE SESSION

Do not make every temporary answer automatically durable.

Current `IntakeSession` / capture-session architecture may remain temporary.

Desired lifecycle:

```text
Temporary IntakeSession
        ↓
questions / voice / OCR
        ↓
Draft ClinicalFacts
        ↓
Patient review
        ↓
Doctor review
        ↓
Physician confirms
        ↓
BEGIN TRANSACTION

Create/update durable Patient
Create durable Encounter
Promote confirmed facts
Promote evidence
Promote medications
Promote observations
Promote document references
Persist physician decision
Generate/persist FHIR export metadata
Record audit event

COMMIT TRANSACTION
        ↓
Only after success:
purge temporary capture/session state
```

If durable promotion fails:

```text
ROLLBACK
```

and **do not purge the temporary session**.

---

# 17. SUPABASE STORAGE FOR DOCUMENTS

Because prescription/report images need to remain available for physician evidence, use Supabase Storage if appropriate.

Create/use a private bucket conceptually similar to:

```text
medical-documents
```

Do not make clinical documents public.

Object organization can use:

```text
patient_id/
    encounter_id/
        document_id/
            original.ext
```

Never expose the raw storage service key to the browser.

Access should use controlled backend access or short-lived signed URLs.

For hackathon demo records, use synthetic documents only.

---

# 18. SUPABASE STORAGE FOR RAW AUDIO

Do **not** permanently store raw microphone audio by default.

If audio is required temporarily:

```text
temporary audio
→ process
→ retain only according to consent/policy
→ delete after TTL/session completion
```

The durable longitudinal record should generally preserve:

```text
transcript/source evidence
```

rather than unnecessary permanent raw audio.

If existing click-to-source functionality requires audio, implement a clearly configurable retention policy.

Do not choose that policy silently.

Report the decision.

---

# 19. ROW LEVEL SECURITY

Because Supabase exposes PostgreSQL through its APIs, review RLS carefully.

Even if the FastAPI backend is currently the main data-access layer, configure secure defaults.

Do not leave sensitive tables publicly readable.

Review RLS for at least:

```text
patients
patient_identifiers
encounters
clinical_facts
source_evidence
documents
extracted_document_entities
medication_events
observation_events
contradictions
red_flag_events
physician_decisions
fhir_exports
```

Do not invent a production authorization model if the project still uses mock ABHA/staff auth.

Instead:

1. block unsafe anonymous direct access;
2. keep backend/service-role access controlled;
3. document how production patient/doctor claims would map to RLS later.

Create:

```text
docs/SUPABASE_SECURITY.md
```

explaining the current hackathon security model vs future production authorization.

---

# 20. SERVICE ROLE KEY

The Supabase service-role key must:

```text
NEVER
```

be shipped to React/Vite client code.

Check:

```text
frontend .env
VITE_* variables
bundled frontend source
git history/current tracked files
```

Backend-only secrets belong only in server environment variables.

Do not commit them.

---

# 21. ENVIRONMENT VARIABLES

Inspect what the connected Supabase setup already provides.

Do not duplicate credentials unnecessarily.

Document required variables in `.env.example` using placeholders only.

Potential variables may include:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABASE_URL
```

But only use what is actually necessary.

For SQLAlchemy, prefer the proper Supabase PostgreSQL connection string made available to this environment.

Do not print secrets to logs or documentation.

---

# 22. CONNECTION POOLING

Supabase may provide direct and pooled PostgreSQL connection options.

Inspect the connected project's recommended connection values.

Select the appropriate URL for the FastAPI/SQLAlchemy runtime.

Document why.

Ensure:

```text
SQLAlchemy async/sync driver
```

matches the actual connection approach.

Do not blindly copy connection strings into source code.

---

# 23. SQLALCHEMY

Prefer keeping SQLAlchemy if the existing backend already uses it.

Do not rewrite the backend around the Supabase Python SDK merely because Supabase is now the database.

Existing architecture:

```text
FastAPI
→ SQLAlchemy
→ PostgreSQL
```

is appropriate.

Use Supabase-specific SDK functionality where it provides real value, such as:

```text
Storage
```

rather than replacing the established ORM unnecessarily.

---

# 24. ALEMBIC / MIGRATIONS

Keep migrations reproducible.

If Alembic already exists:

```text
preserve it
```

Generate migrations for the new longitudinal schema.

Do not manually create production tables through random dashboard clicks without representing them in migrations.

If Supabase SQL migrations are also needed, define one source of truth and document it clearly.

Avoid two independent schema histories drifting apart.

---

# 25. PGVECTOR

Supabase PostgreSQL supports PostgreSQL extensions such as pgvector where enabled.

Do not introduce vector similarity immediately unless necessary.

First implement explainable deterministic historical retrieval using structured facts.

After that, if semantic retrieval materially improves the feature:

```text
enable vector extension
```

and create an encounter representation.

Vector search must remain:

```text
same patient only
```

for the historical-similarity feature.

Never use similarity as disease probability.

---

# 26. PATIENT HISTORY APIs

Once Supabase persistence is connected, implement/verify endpoints conceptually like:

```text
GET /api/patients/{patient_id}

GET /api/patients/{patient_id}/encounters

GET /api/patients/{patient_id}/timeline

GET /api/patients/{patient_id}/medications

GET /api/patients/{patient_id}/observations

GET /api/patients/{patient_id}/documents

GET /api/encounters/{encounter_id}

GET /api/encounters/{encounter_id}/similar
```

These APIs should query Supabase PostgreSQL through the backend data/repository layer.

---

# 27. OCR → SUPABASE FLOW

The visible OCR feature should ultimately work as:

```text
Patient uploads prescription
        ↓
Backend receives file
        ↓
Private Supabase Storage
        ↓
DocumentRecord created
        ↓
OCR
        ↓
ExtractedDocumentEntity
        ↓
Patient / physician verification
        ↓
MedicationEvent / ObservationEvent
        ↓
Timeline
        ↓
Future visits can retrieve it
```

This is critical.

Do not finish the Supabase migration while OCR data still disappears with the temporary session.

---

# 27A. FIX THE CAMERA / IMAGE CAPTURE BEFORE CALLING OCR COMPLETE

The current camera/OCR experience is not working properly in the actual app. Treat this as a blocking product bug, not a cosmetic issue.

The patient must be able to reliably do all three:

```text
[ Take Photo ]
[ Upload Image ]
[ Upload PDF ]
```

For **Take Photo**, implement and verify a real camera flow:

```text
Open camera
→ live preview
→ patient aligns prescription/report
→ Capture
→ show captured image preview
→ [ Retake ] [ Use Photo ]
→ preprocess image
→ upload
→ OCR
```

Requirements:

- use browser camera APIs correctly rather than a broken file-input simulation;
- prefer the rear/environment camera on phones/tablets when available;
- show a live camera preview before capture;
- preserve correct orientation;
- do not crop off the top/bottom of the prescription;
- allow **Retake** before upload;
- allow regular file upload as fallback if camera permission fails;
- show a clear permission error instead of silently failing;
- validate that an actual non-empty image was captured before calling OCR;
- avoid over-compressing the image before OCR;
- preprocess for OCR where useful: orientation correction, perspective correction/deskew, contrast normalization and document-edge crop;
- keep the original synthetic document image/reference for physician evidence, while OCR may operate on a processed copy.

Add a visible guide during capture, for example:

```text
Place the full prescription inside the frame.
Keep the page flat and text readable.
```

The feature is not DONE until I can physically open the running app, take a photo of a synthetic printed prescription, preview it correctly, submit it, and receive OCR output.

Add tests where practical for:

```text
camera permission denied → upload fallback remains available
empty capture → OCR is not called
captured image → preview shown before upload
retake → previous capture discarded
valid capture → document pipeline receives image bytes
```

---

# 27B. FIX OCR END-TO-END, NOT ONLY THE BACKEND

The OCR backend may already exist, but the current real user experience is not reliable enough.

Verify the complete chain in the running app:

```text
Take Photo / Upload
→ image reaches backend
→ OCR returns raw text
→ clinical entity extractor runs
→ medications/labs are returned
→ patient sees verification UI
→ confirmed entities are stored
→ doctor sees them
→ original source image can be opened
→ timeline contains the event
```

If any link in this chain is missing, classify OCR as PARTIAL.

For prescriptions, show extracted items in a review step:

```text
We found:

Metformin 500 mg
Twice daily
[ Confirm ] [ Edit ] [ Remove ]

Pantoprazole 40 mg
Low confidence — please verify
[ Confirm ] [ Edit ] [ Remove ]
```

Do not silently store low-confidence OCR results as confirmed facts.

---

# 27C. REMOVE THE EXTRA CONTINUE BUTTON FROM QUESTION ANSWERS

The current intake interaction has unnecessary friction: the patient selects an answer and then still has to press **Continue**.

Remove that extra step for normal answer choices.

Desired behavior for single-choice answers:

```text
Question appears
→ patient taps one answer
→ answer is immediately stored
→ provenance is recorded
→ red-flag rules run
→ next question appears automatically
```

There should be **no separate Continue button** after a normal single-choice tap.

For yes/no and option buttons:

```text
[ Yes ] [ No ] [ I don't know ] [ Prefer not to answer ]
```

One click must both select and submit.

For free-text answers:

- Enter/Send should submit the answer;
- do not require a second Continue click after Send;
- keep the input available until the request succeeds;
- show a lightweight saving/loading state so double taps do not create duplicate facts.

For multi-select questions only, a small explicit action such as **Done** is acceptable because the patient may need to choose more than one option. Do not use Continue universally.

---

# 27D. ADD A REAL BACK BUTTON FOR THE INTAKE FLOW

Add a clearly visible **Back** control on the patient intake screen.

Expected behavior:

```text
Current question
→ Back
→ previous answered question opens
→ previous answer is shown
→ patient can change it
→ new answer supersedes the old fact
→ downstream state is recalculated safely
```

Do not simply delete database rows without provenance.

When an answer is changed:

- retain the original fact as superseded/auditable where the existing architecture supports it;
- create/update the corrected fact through the same validated fact-writing path;
- rerun any red-flag/contradiction logic affected by the change;
- recalculate conditional question flow if the new answer changes branching;
- do not leave stale answers from branches that are no longer applicable without explicitly marking/superseding them.

The Back button should be disabled only when there is genuinely no previous question in the current encounter.

Do not make browser-back navigation the only way to edit an answer.

---

# 27E. FIX VOICE INPUT AND SPOKEN QUESTION OUTPUT END-TO-END

Voice is currently not working as a convincing product feature. In particular, no spoken question/audio can currently be heard reliably from the application.

Treat **speech input (ASR)** and **spoken output (TTS)** as two separate features and verify both in the actual browser.

## Speech input / ASR

Expected patient flow:

```text
[ microphone button ]
→ browser asks microphone permission if needed
→ listening state is visible
→ patient speaks
→ transcript appears
→ patient can confirm/correct if confidence is uncertain
→ answer is stored
→ next question appears
```

Required UI states:

```text
Ready
Listening…
Processing…
Could not hear clearly — Try again / Type instead
```

Do not fabricate ASR confidence. If the browser/provider does not provide a meaningful value:

```text
confidence = null
confidence_status = unavailable
```

## Spoken question output / TTS

Every patient-facing question should be capable of being spoken aloud in the selected language.

Expected flow:

```text
next question arrives
→ text renders
→ TTS audio is generated/selected
→ question can be heard through the device speaker
```

Provide:

```text
[ 🔊 Hear question ]
[ Replay ]
```

If browser autoplay policy prevents automatic playback, do not silently fail. Use a first user interaction to unlock audio and then either auto-play subsequent prompts where permitted or keep the visible **Hear question** button.

Investigate and fix all likely failure points:

- browser speech-synthesis voice list not loaded yet;
- selected language has no matching browser voice;
- volume/rate/pitch accidentally set incorrectly;
- generated audio URL/blob is invalid;
- `<audio>` element is not mounted/played;
- autoplay is blocked;
- audio context remains suspended;
- TTS backend returns audio but frontend never plays it;
- language code mismatch such as `hi` vs `hi-IN` or `ta` vs `ta-IN`;
- microphone and speaker permissions/state are confused;
- current UI exposes a voice icon that is not actually wired to ASR/TTS.

Use a provider abstraction so the rest of Swastra is not coupled to one service:

```text
SpeechToTextBackend
├── current browser/offline implementation
├── AI4Bharat / Hugging Face implementation where appropriate
└── BHASHINI adapter

TextToSpeechBackend
├── browser/offline implementation
├── Indic TTS implementation where appropriate
└── BHASHINI adapter
```

For the hackathon, prioritize one **fully working** multilingual voice path over many language buttons that do not work.

Minimum acceptance test:

```text
1. Select a supported language.
2. Press Hear question and clearly hear the question.
3. Press microphone and speak an answer.
4. See the transcript.
5. Submit/store without an extra Continue click.
6. Hear or replay the next question.
7. Switch to touch/text at any time without restarting the encounter.
```

If TTS or ASR fails, touch/text must continue working.

---

# 28. DOCTOR DASHBOARD → SUPABASE

The doctor view should load durable information from Supabase.

Doctor opens patient:

```text
Patient
├── Current Encounter
├── Prior Encounters
├── Timeline
├── Medication History
├── Investigations
├── Documents
├── Similar Past Encounters
├── Alerts
└── Summary
```

After refresh or backend restart, physician-confirmed historical data must still exist.

---

# 29. SYNTHETIC SEED DATA

Create a reproducible seed mechanism.

Do not manually insert random dashboard rows.

Seed one longitudinal demo patient.

Example:

```text
2024
Lab report

2025 Feb
Prescription

2025 Aug
Encounter:
abdominal pain
post-meal worsening
nausea

2026
Current intake
```

The seed should support the complete hackathon demonstration.

---

# 30. MIGRATION FROM EXISTING SQLITE DATA

Do not assume existing development data matters.

First inspect it.

If it is only synthetic/test data:

- preserve fixtures where useful;
- prefer reseeding Supabase over complicated one-time migration.

If important development records exist, report before migration.

Do not move real patient data.

---

# 31. SQLITE ROLE AFTER SUPABASE

Supabase PostgreSQL becomes the primary runtime durable database.

SQLite may remain only if useful for:

```text
fast isolated unit tests
```

The application must not silently use SQLite in production/demo when Supabase is expected.

Make database backend obvious in logs:

```text
Database backend: Supabase PostgreSQL
```

Do not print connection secrets.

---

# 32. OFFLINE DEMO CONSIDERATION

Supabase requires connectivity.

The app already aims to remain resilient to external-service failures.

Do not pretend Supabase is offline.

Instead establish a clear strategy:

```text
Normal hackathon demo:
Supabase PostgreSQL

Optional emergency fallback:
local seeded database
```

Only implement a fallback if it is simple and does not introduce dangerous synchronization logic.

Do not build complex bidirectional offline sync now.

The primary demo should use Supabase.

---

# 33. TESTS REQUIRED

Add tests for:

```text
patient persists in Supabase/Postgres
```

```text
one patient can have multiple encounters
```

```text
confirmed Encounter survives CaptureSession purge
```

```text
fact retains SourceEvidence
```

```text
verified OCR medication survives future session
```

```text
historical medication is retrievable
```

```text
timeline spans multiple encounters
```

```text
document metadata points to private storage object
```

```text
unauthorized direct data access is blocked
```

```text
service-role key never appears in frontend bundle/config
```

```text
physician confirmation transaction rolls back safely on failure
```

```text
temporary session is not purged if durable promotion fails
```

```text
similar historical retrieval never crosses patient IDs
```

Also add/verify interaction tests for:

```text
single-choice tap stores answer and auto-advances without Continue
Back returns to the previous question
editing a previous answer supersedes/recalculates safely
voice failure still leaves touch/text usable
TTS control produces playable audio for the supported demo language
camera capture produces a valid preview before OCR
OCR verification is reachable from the real intake UI
```

---

# 34. DO NOT CHANGE THESE SAFETY RULES

Supabase integration must not weaken existing architecture.

Maintain:

```text
No diagnosis
No treatment recommendations
Provenance for clinical facts
Deterministic red flags
Physician confirmation
Validated terminology only
Consent-gated capture
Synthetic hackathon data
```

---

# 35. IMPLEMENTATION PRIORITY

Do the Supabase work in this order:

## Phase S0 — Audit existing persistence

No modifications yet.

## Phase S1 — Connection

Make SQLAlchemy use Supabase PostgreSQL reliably.

## Phase S2 — Longitudinal schema

Patient/Encounter/ClinicalFact/SourceEvidence.

## Phase S3 — Confirmation transaction

Promote temporary session → durable Supabase Encounter.

## Phase S4 — Historical retrieval

Patient history/timeline APIs.

## Phase S5 — Documents

Private Supabase Storage + durable DocumentRecord.

## Phase S6 — OCR entities

Persist verified entities and medication/observation events.

## Phase S7 — Physician dashboard

Read longitudinal data from Supabase.

## Phase S8 — Security

RLS/security review + tests.

## Phase S9 — Demo data

Seed deterministic multi-visit synthetic patient.

---

# 36. DEFINITION OF DONE

Supabase integration is not "done" because:

```text
database connection succeeded
```

It is done when I can:

```text
1. Open synthetic patient
2. See previous encounters stored in Supabase
3. Start a new intake
4. Complete structured intake
5. Upload a prescription
6. OCR it
7. Verify a medication
8. Doctor opens the encounter
9. Doctor sees previous history + current visit
10. Doctor confirms
11. Temporary session is purged
12. Refresh/restart application
13. Confirmed Encounter still exists
14. Medication remains in patient history
15. Timeline still shows all visits
16. Original synthetic document remains securely retrievable
```

That is the actual acceptance test.

---

# 37. FIRST RESPONSE REQUIRED FROM YOU

Before editing persistence code, tell me:

### A. Current persistence architecture

Exact files, models and database paths.

### B. Supabase connection status

Confirm the connected project is reachable without exposing credentials.

### C. Existing work conflict

Tell me whether your current in-progress implementation has already created migrations/models that need adapting.

### D. Proposed Supabase schema

Map existing models → new/reused tables.

### E. Storage design

How prescription/report files will use private Supabase Storage.

### F. Security

How direct anonymous access will be prevented.

### G. Files to modify

Exact paths.

### H. Migration sequence

Small safe commits.

Then proceed with the implementation.

Do not restart the codebase and do not duplicate working clinical modules.
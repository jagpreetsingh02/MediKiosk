# Swastra — Immediate Implementation Prompt for Codex

You have already audited the current Swastra repository.

Now begin implementation.

Do **not** redesign the application into another chatbot and do **not** perform another general audit unless necessary to execute the work below.

The current product already has a good single-encounter foundation, but the visible application still does not communicate the real Swastra vision.

The immediate goal is to transform it from:

```text
Patient
→ chatbot-like questions
→ answers
→ doctor summary
```

into the first working version of:

```text
Patient identity
→ longitudinal clinical memory
→ new encounter
→ adaptive multilingual intake
→ prescription/report upload
→ OCR
→ structured clinical events
→ timeline
→ medication history
→ similar historical encounters
→ physician review
→ source verification
→ confirmation
```

---

# 1. IMPORTANT CORRECTION TO YOUR PREVIOUS AUDIT

I manually ran the current application.

There is **no visible/reachable patient-facing place where I can upload a prescription or report image for OCR**.

Therefore do not treat:

```text
OCR backend exists
```

as equivalent to:

```text
OCR feature works in the product
```

Separate the OCR feature into:

1. OCR backend
2. document upload API
3. patient upload UI
4. upload step connected to actual intake flow
5. document preview
6. OCR processing state
7. extracted entities
8. patient verification
9. physician verification
10. original-document evidence viewer
11. timeline integration
12. longitudinal persistence

The feature is considered complete only when all required user-facing pieces work together.

---

# 2. BEFORE IMPLEMENTING OCR UI

First determine exactly why the existing OCR functionality is invisible.

Inspect and report briefly:

* which upload component currently exists;
* which file contains it;
* whether it is mounted;
* what route displays it;
* what condition/state controls its visibility;
* whether it appears only in demo mode;
* whether frontend upload code exists at all;
* which API endpoint receives documents;
* how that endpoint connects to the OCR pipeline;
* where OCR entities are returned;
* why they currently do not appear properly in physician review.

Do not spend another full audit cycle on this.

Resolve the cause and proceed.

---

# 3. REMOVE THE GENERIC CHATBOT PRODUCT FEEL

Do not delete useful conversational components.

Change the product framing.

The patient should feel like they are completing a structured pre-consultation intake, not talking to ChatGPT.

Replace visual language such as:

```text
AI Assistant
Ask me anything
Chat with Swastra
```

with clinical-intake language such as:

```text
Today's Visit

Tell us what brings you here today.

You can speak, tap or type.
Your responses will be organized for your doctor.
```

Use section-based progress:

```text
Today's concern      ✓
Current symptoms     ●
Medical history
Medicines
Allergies
Previous records
Review
```

Do not show:

```text
Question 7 of 28
```

because the flow is adaptive.

---

# 4. PATIENT HOME / MEMORY SCREEN

Introduce a patient-level screen before starting a new encounter.

For the hackathon use synthetic patients.

Example:

```text
Welcome back

Patient: Demo Patient
ABHA: **** **** 1234

Clinical history

3 previous visits
2 prescriptions
1 laboratory report

[ Start New Visit ]

Recent history
--------------------------------
20 Aug 2025
Abdominal pain visit

14 Feb 2025
Prescription

03 Jun 2024
Laboratory report
```

This screen should immediately communicate:

> This patient already has history in Swastra.

Do not expose real patient information.

Use seeded synthetic data.

---

# 5. BUILD THE LONGITUDINAL CORE FIRST

Add durable models if they do not already exist.

Minimum required domain structure:

```text
Patient
PatientIdentifier

Encounter

ClinicalFact
SourceEvidence

DocumentRecord
ExtractedDocumentEntity

MedicationEvent
ObservationEvent

TimelineEvent

Contradiction

RedFlagEvent

PhysicianDecision
```

Relationship:

```text
Patient
    │
    ├── Encounter 1
    ├── Encounter 2
    ├── Encounter 3
    └── Current Encounter
```

Current `IntakeSession` should remain the temporary working/capture session.

Do NOT simply rename `IntakeSession` to `Encounter`.

Use:

```text
CaptureSession
      ↓
physician confirms
      ↓
transactionally promote
      ↓
Durable Encounter
      ↓
purge temporary capture data
```

---

# 6. AT PHYSICIAN CONFIRMATION

The commit operation should approximately be:

```text
Validate traceable draft
        ↓
Create/update Patient
        ↓
Create durable Encounter
        ↓
Persist confirmed ClinicalFacts
        ↓
Persist SourceEvidence
        ↓
Persist MedicationEvents
        ↓
Persist ObservationEvents
        ↓
Persist Document references
        ↓
Persist TimelineEvents
        ↓
Persist PhysicianDecision
        ↓
Generate immutable FHIR export
        ↓
Audit confirmation
        ↓
Purge temporary/session artifacts
```

This operation should be transactional.

Do not purge session facts before durable promotion succeeds.

---

# 7. ADD DOCUMENT UPLOAD TO THE REAL PATIENT FLOW

After the main symptom/history collection and before final patient review, add:

```text
Previous Medical Records

Do you have any records you would like
your doctor to review?

[ Take Photo ]
[ Upload Image ]
[ Upload PDF ]
[ Skip ]
```

Support initially:

```text
Prescription
Lab report
Discharge summary
Other medical report
```

Do not hide this behind demo-only routes.

---

# 8. UPLOAD UX

When the patient chooses a document:

```text
Upload Medical Record
```

Show:

```text
[ image/PDF preview ]

Document type:
Prescription

Status:
Processing...
```

Then:

```text
Reading document...
Extracting medical information...
Checking confidence...
```

Do not show raw developer logs.

---

# 9. OCR PIPELINE

Use the existing OCR backend where possible.

Flow:

```text
File upload
    ↓
OCR
    ↓
Raw text
    ↓
Clinical entity extraction
    ↓
Source spans / bounding boxes
    ↓
Confidence
    ↓
Verification
```

Do not rewrite working OCR unnecessarily.

---

# 10. PRESCRIPTION EXTRACTION

For prescriptions, attempt to extract:

```text
medicine name
strength
frequency
duration
prescription date
```

Only extract values actually present.

Example:

```text
We found:

Metformin
500 mg
Twice daily
30 days
Confidence: High

Pantoprazole
40 mg
Once daily
Confidence: Verify
```

---

# 11. OCR VERIFICATION SCREEN

OCR must never silently become truth.

Create:

```text
Review extracted information
```

Example:

```text
✓ Metformin 500 mg
  Twice daily
  High confidence

⚠ Pantoprazole 40 mg
  Once daily
  Please verify

[ Correct ]
[ Remove ]
[ Confirm ]
```

Low-confidence handwriting should always require verification.

---

# 12. ORIGINAL DOCUMENT EVIDENCE

The physician must be able to see what OCR came from.

Fix the existing evidence gap.

If policy permits within the synthetic demo:

Store an authorized synthetic document/page asset or durable evidence reference.

Doctor clicks:

```text
Metformin 500 mg
```

Evidence drawer opens:

```text
SOURCE

Prescription
20 Aug 2025
Page 1

[ ORIGINAL DOCUMENT IMAGE ]

Highlighted OCR region:
"Metformin 500 mg BD"

OCR confidence: 93%
```

A blank bounding-box viewer is not sufficient.

---

# 13. CREATE TIMELINE EVENTS FROM OCR

After verification:

```text
DocumentRecord
        ↓
ExtractedDocumentEntity
        ↓
MedicationEvent / ObservationEvent
        ↓
TimelineEvent
```

Example:

```text
20 Aug 2025

PRESCRIPTION

Metformin 500 mg
Twice daily

Source:
Prescription uploaded 20 Aug 2025
```

---

# 14. LONGITUDINAL TIMELINE

Build the physician timeline across encounters.

Not just current-session documents.

Example:

```text
2024

03 Jun
Lab Report
HbA1c recorded


2025

14 Feb
Prescription
Metformin 500 mg

20 Aug
Clinical Encounter
Abdominal pain


2026

24 Aug
Current Encounter
Abdominal pain for 3 days
```

Filters:

```text
All
Visits
Symptoms
Medicines
Labs
Documents
AYUSH
Alerts
```

---

# 15. MEDICATION HISTORY PANEL

Create a separate doctor-facing medication view.

Example:

```text
Medication History

Metformin 500 mg

14 Feb 2025
Found in prescription

20 Aug 2025
Patient reported continuing

24 Aug 2026
Patient reports no current medication

⚠ Needs reconciliation
```

Do not infer that a prescription means the medicine is still being taken.

Use status such as:

```text
historical
patient-reported-current
documented
stopped-reported
uncertain
```

---

# 16. CROSS-VISIT CONTRADICTIONS

Extend contradiction logic beyond the current encounter.

Example:

```text
Current statement:
"I don't take any medicines."

Historical evidence:
Metformin 500 mg prescription

Status:
Needs medication reconciliation
```

Do not automatically decide which source is correct.

---

# 17. SIMILAR PAST ENCOUNTERS

Build an explainable historical retrieval feature.

Only compare:

```text
current encounter
```

with:

```text
the same patient's confirmed prior encounters
```

Start with deterministic shared-feature retrieval.

Do **not** add embeddings first unless deterministic retrieval is insufficient.

Example:

```text
Similar Previous Visit

20 Aug 2025

Shared:
✓ abdominal pain
✓ worse after food
✓ nausea

Similarity:
High historical similarity

[ Open Encounter ]
```

Do not use:

```text
92% probability
```

unless clearly labeled as a non-clinical similarity score.

Never predict disease.

---

# 18. CURRENT ENCOUNTER + HISTORY SIDE BY SIDE

Doctor view should communicate:

```text
TODAY
```

versus:

```text
HISTORY
```

Example:

```text
CURRENT VISIT                         RELEVANT HISTORY

Abdominal pain                       20 Aug 2025
3 days                               Abdominal pain
Worse after meals                    Worse after meals

Current medicines                    Medicine documented:
None reported                        Metformin 500 mg

                                     [ Open previous visit ]
```

This should become a major jury-visible feature.

---

# 19. CLICK-TO-SOURCE EVERYWHERE

Current-session speech evidence already exists partially.

Extend it.

A doctor should be able to click:

```text
"Pain started three days ago"
```

and see:

```text
PATIENT SOURCE

Original:
"I've had this stomach pain for about three days."

Input:
Voice

Language:
Hindi

Confidence:
...

Encounter:
24 Aug 2026
```

For document-derived facts, show original document evidence.

For previous encounters, show prior source evidence.

---

# 20. VOICE CONFIDENCE BUG MUST BE FIXED

Your audit found browser confidence `0` being converted into an invented `0.7`.

Remove that behavior.

Never manufacture ASR confidence.

If confidence is unavailable:

```text
confidence = null
confidence_status = unavailable
```

If low:

```text
I couldn't hear that clearly.

[ Speak again ]
[ Type instead ]
[ Select answer ]
```

Particularly verify uncertain:

```text
allergies
medications
red-flag symptoms
```

---

# 21. AUTHORIZATION MUST BE FIXED

Before exposing persistent patient history:

* enforce patient/session ownership;
* enforce doctor role;
* enforce authorization on session routes;
* enforce authorization on dialogue routes;
* enforce authorization on document routes;
* remove unsafe anonymous defaults where not explicitly demo-only.

For demo:

Use clearly labeled synthetic/demo authentication if production ABHA is unavailable.

---

# 22. RED FLAGS

Preserve the deterministic rule engine.

Persist:

```text
rule evaluated
evidence
whether fired
timestamp
```

Rules may escalate attention.

Never tell patient:

```text
You are safe
```

or generate a diagnosis.

---

# 23. SUMMARY

Keep the current traceable deterministic summary system.

But move it from:

```text
THE final product
```

to:

```text
one view inside physician clinical memory
```

Doctor navigation should eventually include:

```text
Overview
Current Visit
Timeline
Medications
Investigations
Documents
Similar Visits
Alerts
Summary
```

Summary:

```text
DRAFT — Requires physician confirmation
```

---

# 24. DEMO PATIENT

Seed one synthetic patient with history.

Example conceptual dataset:

```text
Patient:
Demo Patient

2024
Lab report

2025 Feb
Prescription containing Metformin

2025 Aug
Encounter:
abdominal pain
post-meal worsening
nausea

2026 Aug
Current encounter:
similar abdominal symptoms
```

This allows one demo to show:

```text
longitudinal history
OCR
medication history
recurrence
similar encounter
new intake
source evidence
physician confirmation
```

---

# 25. THE FIRST VERTICAL SLICE

Do not implement everything in the entire vision before showing progress.

Build this exact slice first:

```text
1. Durable Patient model
2. Durable Encounter model
3. Durable ClinicalFact + SourceEvidence
4. Seed patient with two historical encounters
5. Patient history/home view
6. New intake using existing question engine
7. Visible prescription upload
8. Existing OCR pipeline connected to UI
9. OCR verification
10. Promote medication entity into durable history
11. Cross-encounter timeline
12. Physician view showing current + history
13. Deterministic similar-encounter retrieval
14. Click-to-source
15. Physician confirmation creates third durable encounter
16. Temporary session purge only after successful promotion
```

Stop after this slice and show me the complete working flow before implementing further breadth.

---

# 26. REQUIRED TESTS FOR THIS SLICE

Add tests proving:

```text
Patient can have multiple Encounters
```

```text
confirmed Encounter survives session purge
```

```text
unconfirmed session data is purged
```

```text
document upload endpoint works
```

```text
OCR result reaches verification UI/data contract
```

```text
verified medication creates MedicationEvent
```

```text
historical medication remains historical
unless explicitly confirmed current
```

```text
timeline returns events across multiple encounters
```

```text
similar encounter retrieval only searches same patient
```

```text
similarity result contains explainable shared features
```

```text
summary claim still resolves to source
```

```text
unauthorized patient/session access fails
```

```text
unknown ASR confidence is never converted
into fabricated confidence
```

---

# 27. DO NOT IMPLEMENT YET

Unless needed for this slice, postpone:

```text
production ABHA
production HIS vendor integration
all Indian languages
advanced embeddings
handwriting perfection
large analytics systems
diagnostic prediction
treatment recommendation
billing
appointments
pharmacy
insurance
```

---

# 28. VISUAL SUCCESS CONDITION

When I open the app after this phase, it should **not immediately look like a chatbot project**.

I should see:

```text
MEDIKIOSK

Patient Clinical Memory

Previous visits
Prescriptions
Reports

[ Start New Visit ]
```

Then during the visit:

```text
Today's Visit
Speak / Tap / Type
```

Then:

```text
Add Previous Records
[ Take Photo ]
[ Upload Image ]
[ Upload PDF ]
```

Then doctor:

```text
Patient Overview

Current Encounter
Longitudinal Timeline
Medications
Documents
Similar Past Encounters
Alerts
Summary
```

That visible transformation is required.

---

# 29. IMPLEMENTATION STYLE

* Reuse good existing components.
* Refactor instead of duplicating.
* Keep external providers behind interfaces.
* Keep clinical state deterministic.
* Keep LLM use bounded.
* Preserve source evidence.
* Use synthetic data.
* Add migrations rather than destructive schema hacks.
* Update tests with implementation.
* Do not report a feature DONE until it works end-to-end from the actual UI.

---

# 30. RESPONSE REQUIRED BEFORE YOU START EDITING

Before modifying files, give me a short implementation preview containing:

### A. Why OCR is currently not visible

Exact file/route/state cause.

### B. Files to modify

Exact paths.

### C. Database migration

Tables/columns to add.

### D. Existing components to reuse

Especially OCR, state machine, summary and physician UI.

### E. Implementation order

In small commits.

### F. Risks

Anything likely to break existing functionality.

Then begin implementation of the vertical slice.

Do not perform another broad research phase.

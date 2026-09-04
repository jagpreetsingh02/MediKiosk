# Swastra migration plan

Date: 24 August 2026

## Ordered plan

1. **Safety patch:** enforce authenticated role/action and subject ownership on every session/dialogue/document/bundle route; stop manufacturing ASR confidence.
2. **Longitudinal schema:** add Patient, Encounter, durable ClinicalFact/SourceEvidence, MedicationEvent, ObservationEvent, DocumentRecord, TimelineEvent, PhysicianDecision, and FHIRExport migrations.
3. **Promotion service:** atomically convert a physician-confirmed capture session into durable encounter data before teardown.
4. **Patient APIs:** add patient lookup, encounters, timeline, medications, observations, documents, and encounter detail routes.
5. **First multi-visit fixture:** seed one synthetic patient with two historical encounters and supporting documents.
6. **Physician cockpit:** query durable current/prior events; add longitudinal timeline, medication view, original evidence, and fact accept/reject.
7. **Recurrence/similarity:** start with deterministic shared features, same-patient only, with evidence IDs and clear “historical similarity” labeling.
8. **Document verification:** deliver pending OCR entities to the physician UI, prevent repeat decisions, and define authorized raw-page retention.
9. **FHIR/AYUSH:** cover semantically valid resources and Provenance consistently; wire validated Dashavidha coding and timeline events.
10. **Evaluation:** add ownership/ABAC, promotion-before-purge, cross-visit timeline, medication contradiction, recurrence relevance, raw-source resolution, and end-to-end browser tests.

## First vertical slice

Demonstrate one synthetic patient with two historical encounters and a new current intake. The doctor sees a lifetime timeline, medication history, one similar prior episode with shared evidence, and click-to-source. Confirmation creates the third durable encounter and a FHIR preview, then purges temporary capture.

## Expected files for implementation

- `app/db/models.py` and `alembic/versions/*_longitudinal_core.py`
- `app/modules/longitudinal/` (new)
- `app/api/routes_patients.py` and `app/api/routes_encounters.py` (new)
- `app/api/routes_physician.py`, `app/api/routes_session.py`, `app/api/routes_documents.py`
- `app/modules/consent/session.py`, `app/fhir/bundle.py`
- `frontend/src/physician/PhysicianApp.tsx`, `TimelineView.tsx`, new medication/similarity panels
- `frontend/src/shared/api.ts`
- synthetic fixtures, API/invariant tests, and browser e2e tests

No production implementation changes are authorized by this audit; pause for owner approval after review.

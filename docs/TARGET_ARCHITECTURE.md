# MediKiosk target architecture

Date: 24 August 2026

## Architectural decision

Keep the working intake/compliance spine. Add a durable longitudinal domain beside the temporary capture session; do not turn `IntakeSession` into both.

```text
Patient kiosk                 Physician cockpit                Demo/evaluation
      |                              |                               |
      +------------------------------+-------------------------------+
                                     |
                              FastAPI boundaries
                                     |
        +----------------------------+----------------------------+
        | capture | longitudinal | documents | safety | FHIR/audit |
        +----------------------------+----------------------------+
                     |                              |
        temporary session store          durable clinical store
        audio/transcript scratch          Patient -> Encounter[]
        unconfirmed facts                 Facts + Evidence
        OCR intermediates                 Medication/Observation events
                                            Timeline/Decisions/Exports
```

## Durable domain

Add Patient, PatientIdentifier, Encounter, ClinicalFact, SourceEvidence, DocumentRecord, DocumentPage/reference, MedicationEvent, ObservationEvent, TimelineEvent, Contradiction, RedFlagEvent, PhysicianDecision, FHIRExport, and similarity representation/link models.

## Confirmation boundary

Physician confirmation must be one transaction:

1. validate the draft and fact decisions;
2. write immutable durable encounter facts/events/evidence;
3. create a FHIR preview/export record;
4. record physician decision and audit event;
5. optionally transmit to the labeled HIS adapter;
6. purge temporary capture data according to consent/TTL.

If durable promotion fails, purge must not run.

## Query boundaries

- Patient history/timeline reads only confirmed durable events.
- Similarity compares only the same patient's encounters and returns shared fact IDs/reasons.
- Medication status is event-derived and may be current, historical, or uncertain; never infer adherence.
- Document evidence resolves to an authorized retained page/span or explicitly records that the raw page was purged.
- No diagnosis endpoint, disease probability, or treatment suggestion.

## Reuse

Reuse the kiosk, ontology/machine, `record_fact()` validation, OCR adapters/parser, rules, summary traceability, consent/audit/terminology components, FHIR builder, and most physician components. Replace the persistence projection and extend the physician navigation to timeline, medications, investigations, documents, similar encounters, alerts, evidence, and summary.


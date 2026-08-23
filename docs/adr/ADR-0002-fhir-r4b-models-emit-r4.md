# ADR-0002 — Build with `fhir.resources` R4B models, stamp `fhirVersion 4.0.1`

*Carried across from the SIH 25026 repo, where this decision was first made. Restated here
because the resource list is different and the reasoning needed re-checking against it.*

**Context.** ABDM's IG (`ndhm.in`) is FHIR R4, so `4.0.1` is what must appear on the wire. The
`fhir.resources` package no longer ships Pydantic-v2 models for 4.0.1, and this codebase pins
Pydantic v2 throughout.

**Decision.** Build with `fhir.resources.R4B` (4.3.0) models and stamp `fhirVersion: 4.0.1`.
For every resource MediKiosk emits — Composition, Condition, MedicationStatement,
AllergyIntolerance, Observation, Patient, Consent, DocumentReference, Provenance, Flag,
OperationOutcome — R4B is structurally identical to R4. `app/fhir/r4.py` is the single import
point, and `R4B_ONLY_ELEMENTS` records the elements that exist in R4B but not 4.0.1 so a test
can scan serialised output for them.

**Alternatives.** Pin `fhir.resources` 6.x with Pydantic v1 (abandons the validation layer the
whole contracts module rests on); hand-write R4 JSON (explicitly ruled out — the point of the
library is that it validates); emit R4B and say so (does not satisfy the ABDM IG).

**Consequences.** The claim on the wire has to be verified rather than trusted, which is what
`tests/test_fhir_r4_surface.py` is for. The 25026 repo's version of this ADR covered
ConceptMap and ValueSet; those are not emitted here, and the R5-vocabulary-leak concern it
recorded does not apply to MediKiosk at all.

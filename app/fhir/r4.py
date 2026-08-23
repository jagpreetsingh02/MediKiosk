"""Single import point for FHIR model classes. **Ported from SIH 25026 `app/fhir/r4.py`.**

We emit **FHIR R4** on the wire (ABDM IG `ndhm.in`, fhirVersion 4.0.1). The `fhir.resources`
package no longer ships pydantic-v2 models for 4.0.1, so we build with its R4B (4.3.0) models,
which are structurally identical for every resource we emit. See docs/adr/ADR-0002 (carried
across from the 25026 repo) and `tests/test_fhir_r4_surface.py`, which asserts we never emit
an element that does not exist in 4.0.1.

The resource list differs from 25026: that service emitted terminology resources
(ConceptMap, ValueSet, CodeSystem); MediKiosk emits a *clinical document* — a Composition-led
Bundle. Coding and CodeableConcept carry across unchanged because the closed-vocabulary guard
does.
"""
from __future__ import annotations

from fhir.resources.R4B.allergyintolerance import AllergyIntolerance
from fhir.resources.R4B.bundle import Bundle, BundleEntry, BundleEntryRequest
from fhir.resources.R4B.capabilitystatement import CapabilityStatement
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.codesystem import CodeSystem, CodeSystemConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.composition import Composition, CompositionSection
from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.consent import Consent, ConsentProvision, ConsentProvisionData
from fhir.resources.R4B.documentreference import (
    DocumentReference,
    DocumentReferenceContent,
)
from fhir.resources.R4B.flag import Flag
from fhir.resources.R4B.humanname import HumanName
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.medicationstatement import MedicationStatement
from fhir.resources.R4B.narrative import Narrative
from fhir.resources.R4B.observation import Observation, ObservationReferenceRange
from fhir.resources.R4B.operationoutcome import OperationOutcome, OperationOutcomeIssue
from fhir.resources.R4B.patient import Patient
from fhir.resources.R4B.period import Period
from fhir.resources.R4B.procedure import Procedure
from fhir.resources.R4B.provenance import Provenance, ProvenanceAgent
from fhir.resources.R4B.quantity import Quantity
from fhir.resources.R4B.reference import Reference

FHIR_VERSION = "4.0.1"

#: Elements that exist in R4B but NOT in R4 4.0.1. Emitting one would make the claim on the
#: wire a lie. `tests/test_fhir_r4_surface.py` scans serialised output for these.
R4B_ONLY_ELEMENTS = frozenset(
    {
        "Composition.attester.mode.coding",  # R4B loosened the type; value shape unchanged
        "Observation.referenceRange.normalValue",
        "MedicationStatement.adherence",
    }
)

__all__ = [
    "FHIR_VERSION",
    "R4B_ONLY_ELEMENTS",
    "AllergyIntolerance",
    "Bundle",
    "BundleEntry",
    "BundleEntryRequest",
    "CapabilityStatement",
    "CodeSystem",
    "CodeSystemConcept",
    "CodeableConcept",
    "Coding",
    "Composition",
    "CompositionSection",
    "Condition",
    "Consent",
    "ConsentProvision",
    "ConsentProvisionData",
    "DocumentReference",
    "DocumentReferenceContent",
    "Flag",
    "HumanName",
    "Identifier",
    "MedicationStatement",
    "Narrative",
    "Observation",
    "ObservationReferenceRange",
    "OperationOutcome",
    "OperationOutcomeIssue",
    "Patient",
    "Period",
    "Procedure",
    "Provenance",
    "ProvenanceAgent",
    "Quantity",
    "Reference",
]

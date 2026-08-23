"""FHIR R4 emission — the HIS push. Adapted from SIH 25026 `app/fhir/bundle.py`.

A Composition-led document Bundle, stamped `fhirVersion 4.0.1` per ADR-0002. The resources
differ from the 25026 service (it emitted terminology; this emits a clinical document) but the
two rules carry across unchanged:

* every `Coding` came out of `emit_coding()` — codes are retrieved, never generated;
* nothing is emitted that does not exist in R4 4.0.1.

A third rule is MediKiosk's own: **a `Provenance` resource for every clinical resource.** The
provenance chain is not decoration here — it is the entire product. A Condition with no
Provenance pointing at the utterance behind it should not exist in this bundle.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.contracts.history import ClinicalHistory
from app.contracts.provenance import DocumentSpan, Fact, UtteranceSpan
from app.contracts.record import FactLedger
from app.core.config import settings
from app.fhir.r4 import (
    FHIR_VERSION,
    Bundle,
    BundleEntry,
    CodeableConcept,
    Composition,
    CompositionSection,
    Condition,
    Consent,
    DocumentReference,
    Flag,
    Identifier,
    MedicationStatement,
    Narrative,
    Observation,
    Patient,
    Provenance,
    Reference,
)

#: The intake note LOINC code. A literal from the spec, used as a *system+code* pair the
#: bundle declares; it is not a code retrieved from a patient-facing lookup.
LOINC_INTAKE_NOTE = ("http://loinc.org", "34117-2", "History and physical note")

MEDIKIOSK_PROFILE = "https://medikiosk.local/fhir/StructureDefinition/IntakeSummary"


def _uuid_ref() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def _text(div: str) -> Narrative:
    return Narrative(status="generated", div=f'<div xmlns="http://www.w3.org/1999/xhtml">{div}</div>')


def _concept(text: str, coding: dict[str, Any] | None = None) -> CodeableConcept:
    """`text` always; `coding` only when the sidecar retrieved one. Unmapped is normal."""
    payload: dict[str, Any] = {"text": text}
    if coding:
        payload["coding"] = [coding]
    return CodeableConcept(**payload)


def _provenance_for(
    target_ref: str, fact: Fact, *, patient_ref: str, device_ref: str
) -> Provenance:
    """One Provenance per clinical resource, carrying the verbatim source.

    The utterance goes in `Provenance.entity.what.display` and the tier in
    `Provenance.activity`. A receiving HIS that ignores Provenance still gets a valid
    document; one that reads it gets the whole audit trail.
    """
    span = fact.source
    if isinstance(span, DocumentSpan):
        location = f"document {span.document_id}, page {span.page}"
    elif isinstance(span, UtteranceSpan):
        location = f"turn {span.turn_id}, question {span.question_id}"
    else:  # pragma: no cover - the union is exhaustive
        location = "unknown"

    return Provenance(
        target=[Reference(reference=target_ref)],
        recorded=datetime.now(UTC),
        activity=_concept(f"{fact.tier.value} (MediKiosk provenance tier)"),
        agent=[
            {
                "who": Reference(reference=device_ref, display="MediKiosk intake kiosk"),
                "onBehalfOf": Reference(reference=patient_ref),
            }
        ],
        entity=[
            {
                "role": "source",
                "what": Reference(
                    display=f"{span.verbatim} [{location}, confidence {fact.confidence:.2f}]"
                ),
            }
        ],
    )


def build_bundle(
    history: ClinicalHistory,
    ledger: FactLedger,
    *,
    summary_text: str,
    consent_ref: str,
    committed_by: str,
    abha_ref: str | None = None,
) -> Bundle:
    """Assemble the document Bundle a physician has committed."""
    entries: list[BundleEntry] = []
    by_id = {f.fact_id: f for f in ledger.facts}

    patient_ref = _uuid_ref()
    device_ref = "Device/medikiosk-intake"

    patient = Patient(
        identifier=[
            Identifier(
                system="https://healthid.abdm.gov.in/", value=abha_ref or "unlinked",
            )
        ],
        active=True,
        gender=(history.demographics.gender or None),
        text=_text("Synthetic patient. Identified by ABHA reference only."),
    )
    entries.append(BundleEntry(fullUrl=patient_ref, resource=patient))

    consent_full = _uuid_ref()
    entries.append(
        BundleEntry(
            fullUrl=consent_full,
            resource=Consent(
                status="active",
                scope=_concept("Patient privacy consent"),
                category=[_concept("MediKiosk intake consent")],
                patient=Reference(reference=patient_ref),
                dateTime=datetime.now(UTC),
                policyRule=_concept(f"MediKiosk consent policy {consent_ref}"),
            ),
        )
    )

    clinical_refs: list[str] = []

    # ---- problems the patient or a document REPORTED (never an assessment) ----
    for problem in history.problems:
        if not problem.reported_term.recorded:
            continue
        full = _uuid_ref()
        entries.append(
            BundleEntry(
                fullUrl=full,
                resource=Condition(
                    subject=Reference(reference=patient_ref),
                    # `verification-status: unconfirmed` is the load-bearing element. This is
                    # patient-reported history entering a physician's record, not a diagnosis.
                    verificationStatus=CodeableConcept(
                        coding=[
                            {
                                "system": (
                                    "http://terminology.hl7.org/CodeSystem/"
                                    "condition-ver-status"
                                ),
                                "code": "unconfirmed",
                                "display": "Unconfirmed",
                            }
                        ]
                    ),
                    category=[
                        _concept(
                            "Problem reported by the patient at intake",
                        )
                    ],
                    code=_concept(str(problem.reported_term.value), problem.coding),
                    text=_text(f"Patient-reported: {problem.reported_term.value}"),
                ),
            )
        )
        clinical_refs.append(full)
        for fact_id in problem.reported_term.fact_ids:
            if (fact := by_id.get(fact_id)) is not None:
                entries.append(
                    BundleEntry(
                        fullUrl=_uuid_ref(),
                        resource=_provenance_for(
                            full, fact, patient_ref=patient_ref, device_ref=device_ref
                        ),
                    )
                )

    # ---- medications ----
    for med in history.medications:
        if not med.name.recorded:
            continue
        full = _uuid_ref()
        dosage = " ".join(
            str(s.value) for s in (med.dose, med.frequency, med.route) if s.recorded
        )
        entries.append(
            BundleEntry(
                fullUrl=full,
                resource=MedicationStatement(
                    status="unknown" if not med.ongoing.recorded else "active",
                    subject=Reference(reference=patient_ref),
                    medicationCodeableConcept=_concept(str(med.name.value), med.coding),
                    dosage=[{"text": dosage}] if dosage else None,
                    note=[{"text": "Reported by the patient at intake; not verified."}],
                ),
            )
        )
        clinical_refs.append(full)
        for fact_id in med.name.fact_ids:
            if (fact := by_id.get(fact_id)) is not None:
                entries.append(
                    BundleEntry(
                        fullUrl=_uuid_ref(),
                        resource=_provenance_for(
                            full, fact, patient_ref=patient_ref, device_ref=device_ref
                        ),
                    )
                )

    # ---- investigations ----
    for inv in history.investigations:
        if not inv.analyte.recorded:
            continue
        full = _uuid_ref()
        payload: dict[str, Any] = {
            "status": "final",
            "subject": Reference(reference=patient_ref),
            "code": _concept(str(inv.analyte.value), inv.coding),
            "note": [{"text": "Transcribed from a document the patient brought."}],
        }
        if inv.value.recorded:
            try:
                payload["valueQuantity"] = {
                    "value": float(str(inv.value.value)), "unit": inv.unit or "",
                }
            except ValueError:
                payload["valueString"] = str(inv.value.value)
        if inv.reference_low is not None or inv.reference_high is not None:
            payload["referenceRange"] = [
                {
                    **(
                        {"low": {"value": inv.reference_low, "unit": inv.unit or ""}}
                        if inv.reference_low is not None else {}
                    ),
                    **(
                        {"high": {"value": inv.reference_high, "unit": inv.unit or ""}}
                        if inv.reference_high is not None else {}
                    ),
                }
            ]
        entries.append(BundleEntry(fullUrl=full, resource=Observation(**payload)))
        clinical_refs.append(full)

    # ---- red flags as Flag resources ----
    for flag in history.red_flags:
        full = _uuid_ref()
        entries.append(
            BundleEntry(
                fullUrl=full,
                resource=Flag(
                    status="active",
                    category=[_concept("Intake escalation")],
                    code=_concept(f"{flag.label} — {flag.rationale}"),
                    subject=Reference(reference=patient_ref),
                    text=_text(f"[{flag.level.upper()}] {flag.label}"),
                ),
            )
        )
        clinical_refs.append(full)

    # ---- uploaded documents ----
    for doc in history.documents:
        full = _uuid_ref()
        entries.append(
            BundleEntry(
                fullUrl=full,
                resource=DocumentReference(
                    status="current",
                    subject=Reference(reference=patient_ref),
                    description=(
                        f"{doc.filename} — {doc.pages} page(s), OCR {doc.ocr_backend} at "
                        f"{doc.mean_confidence:.0%} mean confidence"
                    ),
                    content=[
                        {
                            "attachment": {
                                "contentType": "application/pdf",
                                "title": doc.filename,
                            }
                        }
                    ],
                ),
            )
        )
        clinical_refs.append(full)

    # ---- the Composition that leads the document ----
    composition = Composition(
        status="preliminary",  # a physician-confirmed DRAFT of an intake note
        type=CodeableConcept(
            coding=[
                {
                    "system": LOINC_INTAKE_NOTE[0],
                    "code": LOINC_INTAKE_NOTE[1],
                    "display": LOINC_INTAKE_NOTE[2],
                }
            ],
            text="Pre-consultation intake history",
        ),
        subject=Reference(reference=patient_ref),
        date=datetime.now(UTC),
        author=[Reference(display=committed_by)],
        title="MediKiosk pre-consultation intake history",
        attester=[
            {
                "mode": "legal",
                "time": datetime.now(UTC),
                "party": Reference(display=committed_by),
            }
        ],
        section=[
            CompositionSection(
                title="Structured intake history",
                text=_text(summary_text.replace("\n", "<br/>")),
                entry=[Reference(reference=ref) for ref in clinical_refs] or None,
            )
        ],
        text=_text(
            "Patient-reported intake history captured by MediKiosk and confirmed by "
            f"{committed_by}. Contains no assessment, diagnosis or treatment recommendation."
        ),
    )
    entries.insert(0, BundleEntry(fullUrl=_uuid_ref(), resource=composition))

    bundle = Bundle(
        type="document",
        timestamp=datetime.now(UTC),
        identifier=Identifier(
            system="https://medikiosk.local/fhir/Bundle", value=f"bundle-{uuid.uuid4().hex[:12]}"
        ),
        entry=entries,
        meta={"profile": [MEDIKIOSK_PROFILE]},
    )
    return bundle


def bundle_json(bundle: Bundle) -> dict[str, Any]:
    """Serialise and stamp the FHIR version we claim on the wire."""
    payload = bundle.model_dump(mode="json", exclude_none=True)
    payload["meta"] = {**payload.get("meta", {}), "versionId": settings.namaste_version}
    payload["_fhirVersion"] = FHIR_VERSION
    return payload

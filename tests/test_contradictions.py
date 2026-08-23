"""Contradiction detection — two sources disagree and neither is discarded.

The build brief is explicit that a patient saying "no medicines" while holding a prescription
for metformin must surface as a conflict rather than one source quietly winning. These tests
pin that, and pin the thing that would be worse than not detecting it at all: auto-resolving.
"""
from __future__ import annotations

from app.contracts.contradictions import detect, load_rules
from app.contracts.projection import project
from app.contracts.record import FactLedger
from app.modules.dialogue.ontology import load_ontology
from app.modules.documents.pipeline import ingest
from tests.helpers import tap

FIXTURE = "data/fixtures/documents/prescription.pdf"


def _with_prescription(ledger: FactLedger, project_root) -> None:
    ingest(
        ledger,
        (project_root / FIXTURE).read_bytes(),
        filename="prescription.pdf",
        media_type="application/pdf",
        known_paths=load_ontology().known_paths,
        backend_name="textlayer",
        sex="female",
    )


def test_rules_load(project_root) -> None:
    rules = load_rules()
    assert rules.denials
    assert all(rule.id.startswith("CX-") for rule in rules.denials)


def test_denying_medicines_while_holding_a_prescription_is_a_conflict(project_root) -> None:
    ledger = FactLedger("s1")
    tap(ledger, "drug_allergy.taking_medicines", False)
    _with_prescription(ledger, project_root)

    found = detect(ledger)
    med = [c for c in found if c.rule_id == "CX-MED-01"]
    assert med, "the classic case must be detected"
    assert med[0].patient_side.value is False
    assert "METFORMIN" in " ".join(c.document_side.verbatim.upper() for c in med)


def test_neither_source_is_discarded(project_root) -> None:
    """The whole point. Both facts stay in the ledger and both stay active."""
    ledger = FactLedger("s1")
    tap(ledger, "drug_allergy.taking_medicines", False)
    _with_prescription(ledger, project_root)

    found = detect(ledger)
    assert found
    active = {f.fact_id for f in ledger.active_facts()}
    for conflict in found:
        assert conflict.patient_side.fact_id in active
        assert conflict.document_side.fact_id in active


def test_conflicts_are_never_auto_resolved(project_root) -> None:
    ledger = FactLedger("s1")
    tap(ledger, "drug_allergy.taking_medicines", False)
    _with_prescription(ledger, project_root)
    assert all(c.status == "open" for c in detect(ledger))
    assert all(c.resolved_by is None for c in detect(ledger))


def test_a_consistent_patient_produces_no_conflicts(project_root) -> None:
    """Guards against a detector that fires on everybody."""
    ledger = FactLedger("s1")
    tap(ledger, "drug_allergy.taking_medicines", True)
    tap(ledger, "past_medical.conditions", ["diabetes"])
    tap(ledger, "past_surgical.any", True)
    _with_prescription(ledger, project_root)
    assert detect(ledger) == []


def test_no_documents_means_no_conflicts() -> None:
    ledger = FactLedger("s1")
    tap(ledger, "drug_allergy.taking_medicines", False)
    tap(ledger, "past_medical.conditions", ["none"])
    assert detect(ledger) == []


def test_denying_conditions_conflicts_with_a_documented_diagnosis(project_root) -> None:
    ledger = FactLedger("s1")
    tap(ledger, "past_medical.conditions", ["none"])
    _with_prescription(ledger, project_root)
    assert any(c.rule_id == "CX-PMH-01" for c in detect(ledger))


def test_every_conflict_carries_both_verbatims(project_root) -> None:
    """A conflict a physician cannot read the evidence for is not actionable."""
    ledger = FactLedger("s1")
    tap(ledger, "drug_allergy.taking_medicines", False)
    tap(ledger, "past_medical.conditions", ["none"])
    _with_prescription(ledger, project_root)
    for conflict in detect(ledger):
        assert conflict.patient_side.verbatim.strip()
        assert conflict.document_side.verbatim.strip()
        assert conflict.document_side.origin


def test_conflicts_reach_the_projected_history(project_root) -> None:
    ledger = FactLedger("s1")
    tap(ledger, "drug_allergy.taking_medicines", False)
    _with_prescription(ledger, project_root)
    history = project(ledger)
    assert history.contradictions
    assert history.contradictions[0]["patientSide"]["verbatim"] == "No"


def test_a_boolean_renders_as_a_word_not_a_python_literal() -> None:
    """`Ever admitted: False` is Python leaking onto a clinical screen."""
    ledger = FactLedger("s1")
    tap(ledger, "past_medical.hospitalised", False)
    history = project(ledger)
    slot = history.past_medical.slots["past_medical.hospitalised"]
    assert slot.value == "No"

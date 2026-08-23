"""Invariant 2 — provenance or nothing. These tests are the invariant's teeth.

If any of them is ever deleted or relaxed, the guarantee MediKiosk makes to a physician —
"every line on this screen traces to something the patient actually said" — is gone.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.contracts.provenance import (
    BoundingBox,
    DocumentSpan,
    Fact,
    Modality,
    SourceTier,
    UtteranceSpan,
)
from app.contracts.record import record_fact, utterance_span
from app.core.errors import ProvenanceError, ValidationError

#: Modules allowed to construct a Fact directly. Exactly one, plus the tests.
FACT_CONSTRUCTION_ALLOWED = {"app/contracts/record.py"}


def test_fact_is_constructed_only_inside_record_fact(project_root: Path) -> None:
    """Scan the source tree. `Fact(` anywhere else is a hole in the choke point."""
    offenders: list[str] = []
    for path in (project_root / "app").rglob("*.py"):
        rel = path.relative_to(project_root).as_posix()
        if rel in FACT_CONSTRUCTION_ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Fact"
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "Fact() must only be constructed inside record_fact(). Found direct construction at: "
        + ", ".join(offenders)
    )


def test_record_fact_has_no_bypass_parameter() -> None:
    """A `force`/`skip_validation` parameter would end the invariant. There must never be one."""
    import inspect

    params = set(inspect.signature(record_fact).parameters)
    forbidden = {"force", "skip_validation", "trust_me", "unsafe", "bypass", "allow_unsourced"}
    assert not (params & forbidden), f"record_fact grew a bypass parameter: {params & forbidden}"


def test_rejects_fact_with_no_source(ledger) -> None:
    with pytest.raises((ProvenanceError, TypeError)):
        record_fact(
            ledger, path="hpi.site", value="chest",
            tier=SourceTier.STATED, source=None, confidence=0.9,  # type: ignore[arg-type]
        )


def test_rejects_blank_verbatim(ledger) -> None:
    with pytest.raises(ValueError):
        UtteranceSpan(
            verbatim="   ", turn_id="t1", question_id="q1", char_start=0, char_end=3
        )


def test_rejects_null_value(ledger) -> None:
    span = utterance_span(verbatim="chest", turn_id="t1", question_id="hpi.site")
    with pytest.raises(ProvenanceError, match="null value"):
        record_fact(
            ledger, path="hpi.site", value=None,
            tier=SourceTier.STATED, source=span, confidence=0.9,
        )


def test_rejects_paraphrase(ledger) -> None:
    """The anti-hallucination check: a value that is not in its own source is refused."""
    span = utterance_span(
        verbatim="it started three days ago", turn_id="t1", question_id="hpi.onset"
    )
    with pytest.raises(ProvenanceError, match="does not appear in its own source span"):
        record_fact(
            ledger, path="hpi.onset", value="myocardial infarction",
            tier=SourceTier.STATED, source=span, confidence=0.9,
        )


def test_rejects_document_tier_with_utterance_span(ledger) -> None:
    span = utterance_span(verbatim="metformin", turn_id="t1", question_id="med.list")
    with pytest.raises(ProvenanceError, match="requires a DocumentSpan"):
        record_fact(
            ledger, path="medications[0].name", value="metformin",
            tier=SourceTier.DOCUMENT, source=span, confidence=0.9,
        )


def test_rejects_confirmed_tier_without_question(ledger) -> None:
    span = UtteranceSpan(
        verbatim="yes", turn_id="t1", question_id="", char_start=0, char_end=3
    )
    with pytest.raises(ProvenanceError, match="no question_id"):
        record_fact(
            ledger, path="past_medical.hospitalised", value=True,
            tier=SourceTier.CONFIRMED, source=span, confidence=1.0,
        )


def test_rejects_unknown_path(ledger) -> None:
    span = utterance_span(verbatim="chest", turn_id="t1", question_id="hpi.site")
    with pytest.raises(ValidationError, match="ontology defines"):
        record_fact(
            ledger, path="hpi.definitely_not_a_field", value="chest",
            tier=SourceTier.STATED, source=span, confidence=0.9,
            known_paths={"hpi.site"},
        )


def test_rejects_fact_outside_consent_scope(ledger) -> None:
    span = utterance_span(verbatim="chest", turn_id="t1", question_id="hpi.site")
    with pytest.raises(ProvenanceError, match="consent scope"):
        record_fact(
            ledger, path="hpi.site", value="chest",
            tier=SourceTier.STATED, source=span, confidence=0.9,
            required_scope="genomics",
        )


def test_document_span_requires_page_and_bbox() -> None:
    with pytest.raises(ValueError):
        DocumentSpan(  # type: ignore[call-arg]
            verbatim="Metformin 500mg", document_id="doc1",
            ocr_confidence=0.9, ocr_backend="textlayer",
        )
    span = DocumentSpan(
        verbatim="Metformin 500mg", document_id="doc1", page=2,
        bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.05),
        ocr_confidence=0.91, ocr_backend="textlayer",
    )
    assert span.page == 2 and span.bbox.width == 0.3


def test_there_are_exactly_three_tiers() -> None:
    """A fourth tier would be a place to hide an inference. There is no fourth tier."""
    assert {t.value for t in SourceTier} == {"stated", "confirmed", "document"}


def test_selection_evidence_requires_a_tap() -> None:
    with pytest.raises(ValueError, match="evidence of a tap"):
        UtteranceSpan(
            verbatim="Chest", turn_id="t1", question_id="hpi.site",
            char_start=0, char_end=5, modality=Modality.SPEECH,
            selected_values=("chest",),
        )


def test_selection_evidence_must_match_the_recorded_value(ledger) -> None:
    span = utterance_span(
        verbatim="Cold sweating", turn_id="t1", question_id="hpi.associated",
        modality=Modality.TOUCH, selected_values=("sweating",),
    )
    with pytest.raises(ProvenanceError):
        record_fact(
            ledger, path="hpi.associated", value=["sweating", "breathlessness"],
            tier=SourceTier.CONFIRMED, source=span, confidence=1.0,
        )


def test_contradiction_supersedes_rather_than_overwrites(ledger) -> None:
    first = record_fact(
        ledger, path="chief_complaint.duration", value="three days",
        tier=SourceTier.STATED, confidence=0.8,
        source=utterance_span(verbatim="three days", turn_id="t1", question_id="cc.duration"),
    )
    second = record_fact(
        ledger, path="chief_complaint.duration", value="about a week",
        tier=SourceTier.STATED, confidence=0.8,
        source=utterance_span(verbatim="about a week", turn_id="t7", question_id="cc.duration"),
    )
    stored_first = ledger.by_id(first.fact_id)
    assert stored_first is not None and stored_first.superseded_by == second.fact_id
    assert len(ledger.facts) == 2, "the earlier answer must be kept, not overwritten"
    assert len(ledger.active_facts()) == 1

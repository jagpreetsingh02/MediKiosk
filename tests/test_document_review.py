"""The patient reads back what OCR found on their own paper, before it counts.

Two things are proved here. First, that a *named* human correction reaches the ledger — it
did not before this slice, and the lane reported success anyway. Second, that the patient's
authority and the document's authority are different things: a patient may admit a
low-confidence reading, and may dispute a high-confidence one, but disputing does not delete
what the prescription says.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contracts.provenance import BoundingBox, DocumentSpan, SourceTier
from app.contracts.record import record_fact
from app.core.errors import ProvenanceError
from app.modules.documents.pipeline import (
    classify_document,
    confidence_band,
    ingest,
)

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"


@pytest.fixture
def known_paths():
    from app.modules.dialogue.ontology import load_ontology

    return load_ontology().known_paths


def _span(**overrides):
    base = dict(
        verbatim="TAB. METFARMIN 500mg 1-0-1 x 30 days",
        document_id="doc_x",
        page=1,
        bbox=BoundingBox(x=0.1, y=0.1, width=0.5, height=0.05),
        ocr_confidence=0.61,
        ocr_backend="tesseract",
        handwritten=True,
    )
    base.update(overrides)
    return DocumentSpan(**base)


# ------------------------------------------------- the correction that was being dropped


def test_a_correction_that_changes_a_word_is_refused_without_a_named_reader(ledger) -> None:
    """The old behaviour, pinned. "Metformin" is not in "METFARMIN", and must not be."""
    with pytest.raises(ProvenanceError, match="does not appear in its own"):
        record_fact(
            ledger,
            path="medications[0].name",
            value="Metformin",
            tier=SourceTier.DOCUMENT,
            source=_span(),
            confidence=0.61,
        )


def test_a_named_human_reading_is_what_admits_the_correction(ledger) -> None:
    fact = record_fact(
        ledger,
        path="medications[0].name",
        value="Metformin",
        tier=SourceTier.DOCUMENT,
        source=_span(human_reading="Metformin", read_by="dr.mehta@aiia"),
        confidence=0.61,
    )
    assert fact.value == "Metformin"
    # The scrawl is still the evidence. The reading sits beside it, not over it.
    assert fact.source.verbatim == "TAB. METFARMIN 500mg 1-0-1 x 30 days"
    assert fact.source.read_by == "dr.mehta@aiia"


def test_an_unattributed_reading_is_not_provenance() -> None:
    """Without a name this would be a free-text bypass of the echo check, which is the point
    of the echo check."""
    with pytest.raises(ValueError, match="must name who read it"):
        _span(human_reading="Metformin")


def test_a_reading_cannot_launder_an_unrelated_value(ledger) -> None:
    """A human may correct what the scrawl says. They may not attach any value they like."""
    with pytest.raises(ProvenanceError):
        record_fact(
            ledger,
            path="medications[0].name",
            value="Warfarin",
            tier=SourceTier.DOCUMENT,
            source=_span(human_reading="Metformin", read_by="dr.mehta@aiia"),
            confidence=0.61,
        )


# ------------------------------------------------------------------ the readback contract


def test_the_upload_response_carries_what_was_found_not_only_what_failed(
    ledger, known_paths
) -> None:
    """No screen could show a patient their own prescription before this: the successful
    extractions never left the API."""
    result = ingest(
        ledger,
        (FIXTURES / "prescription.pdf").read_bytes(),
        filename="prescription.pdf",
        media_type="application/pdf",
        known_paths=known_paths,
    )
    payload = result.to_dict()
    assert payload["extracted"], "the response must list the entities that were recorded"
    assert len(payload["extracted"]) >= len(payload["needsVerification"])
    assert payload["documentKind"] == "prescription"

    medicines = [item for item in payload["extracted"] if item["kind"] == "medication"]
    assert medicines, "the prescription fixture must yield medicines"
    for item in medicines:
        assert item["itemId"]
        assert item["confidenceBand"] in ("high", "medium", "verify")
        assert item["sourceText"], "every readback item must carry the line it came from"


def test_every_item_is_addressable_across_both_lanes(ledger, known_paths) -> None:
    result = ingest(
        ledger,
        (FIXTURES / "prescription.pdf").read_bytes(),
        filename="prescription.pdf",
        media_type="application/pdf",
        known_paths=known_paths,
    )
    ids = [item["itemId"] for item in result.extracted_items()]
    assert len(ids) == len(set(ids)), "an ambiguous itemId would confirm the wrong medicine"
    assert all(i.startswith(("recorded:", "pending:")) for i in ids)


def test_confidence_is_banded_not_reported_as_a_percentage() -> None:
    """A patient reading "81%" hears "81% chance this medicine is right". It is not that."""
    assert confidence_band(0.98, handwritten=False) == "high"
    assert confidence_band(0.80, handwritten=False) == "medium"
    assert confidence_band(0.50, handwritten=False) == "verify"
    # Handwriting goes to the human lane regardless of what the engine claims about it.
    assert confidence_band(0.99, handwritten=True) == "verify"


def test_document_kind_comes_from_what_was_found_not_the_filename() -> None:
    assert classify_document([{"kind": "medication"}]) == "prescription"
    assert classify_document([{"kind": "investigation"}]) == "lab_report"
    assert classify_document([{"kind": "note"}]) == "other"
    assert classify_document([]) == "other"

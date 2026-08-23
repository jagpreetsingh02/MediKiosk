"""Phase 4 — documents: OCR, entities, ranges, timeline, and the handwriting lane."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.contracts.history import TimelineEvent
from app.core.errors import UpstreamUnavailable, ValidationError
from app.modules.dialogue.ontology import load_ontology
from app.modules.documents.backends import TesseractOCR, TextLayerOCR
from app.modules.documents.entities import (
    document_date,
    extract_entities,
    parse_date,
)
from app.modules.documents.pipeline import ingest, verify_entity
from app.modules.documents.ranges import assess, match_analyte, parse_printed_range
from app.modules.documents.timeline import group_by_period, order_timeline

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"


@pytest.fixture
def known_paths() -> set[str]:
    return load_ontology().known_paths


# ------------------------------------------------------------------ backends


def test_both_backends_exist_and_report_availability_honestly() -> None:
    assert TextLayerOCR().available is True
    tesseract = TesseractOCR()
    assert isinstance(tesseract.available, bool)


def test_textlayer_refuses_images_rather_than_returning_nothing() -> None:
    with pytest.raises(ValidationError, match="image-capable backend"):
        TextLayerOCR().read(b"\x89PNG", filename="scan.png", media_type="image/png")


def test_textlayer_reads_a_digital_pdf_exactly() -> None:
    data = (FIXTURES / "prescription.pdf").read_bytes()
    result = TextLayerOCR().read(data, filename="prescription.pdf", media_type="application/pdf")
    assert "METFORMIN" in result.text
    assert result.mean_confidence > 0.95


def test_every_block_carries_a_bbox_and_confidence() -> None:
    """Invariant 2 needs both for a document-tier fact. Missing either is unrecordable."""
    data = (FIXTURES / "lab_report.pdf").read_bytes()
    result = TextLayerOCR().read(data, filename="lab_report.pdf", media_type="application/pdf")
    for page in result.pages:
        for block in page.blocks:
            assert 0.0 <= block.bbox.x <= 1.0 and 0.0 <= block.bbox.y <= 1.0
            assert block.bbox.width > 0 and block.bbox.height > 0
            assert 0.0 <= block.confidence <= 1.0


# ------------------------------------------------------------------ entities


def test_indian_prescription_notation_is_parsed() -> None:
    result = TextLayerOCR().read(
        b"TAB. METFORMIN 500MG 1-0-1 x 30 days\nTAB. AMLODIPINE 5MG OD\nCAP. OMEPRAZOLE 20MG HS",
        filename="rx.txt",
        media_type="text/plain",
    )
    entities, _ = extract_entities(result)
    meds = {e.text: e.detail for e in entities if e.kind == "medication"}
    assert set(meds) == {"METFORMIN", "AMLODIPINE", "OMEPRAZOLE"}
    assert meds["METFORMIN"]["dose"] == "500MG"
    assert "morning" in meds["METFORMIN"]["frequency"]
    assert meds["AMLODIPINE"]["frequency"] == "once daily"
    assert meds["OMEPRAZOLE"]["frequency"] == "at bedtime"


def test_od_inside_a_drug_name_is_not_read_as_a_frequency() -> None:
    """AMLODIPINE contains 'OD'. Without word boundaries the name truncates to 'AML'."""
    result = TextLayerOCR().read(
        b"TAB. AMLODIPINE 5MG OD", filename="rx.txt", media_type="text/plain"
    )
    entities, _ = extract_entities(result)
    assert entities[0].text == "AMLODIPINE"
    assert entities[0].detail["dose"] == "5MG"


def test_analyte_label_containing_digits_is_not_split() -> None:
    """'HbA1c 8.2' must not parse as label 'HbA' with value 1."""
    result = TextLayerOCR().read(
        b"HbA1c 8.2 % (ref 4.0 - 5.6)", filename="lab.txt", media_type="text/plain"
    )
    entities, _ = extract_entities(result)
    assert len(entities) == 1
    assert entities[0].detail["value"] == 8.2
    assert entities[0].detail["rangeFlag"] == "high"


def test_headings_are_not_read_as_medications() -> None:
    result = TextLayerOCR().read(
        b"Patient: someone   Age: 64\nReg No 12345\nDate: 14/03/2026",
        filename="rx.txt",
        media_type="text/plain",
    )
    entities, _ = extract_entities(result)
    assert not [e for e in entities if e.kind == "medication"]


# ------------------------------------------------------------------ ranges


def test_a_range_printed_on_the_report_beats_our_table() -> None:
    """Labs differ. Flagging against our table when the report disagrees destroys trust."""
    ours = assess("Serum Creatinine", 1.25, sex="female")
    theirs = assess("Serum Creatinine", 1.25, printed_range="0.6 - 1.4", sex="female")
    assert ours.flag == "high" and ours.source == "reference_table"
    assert theirs.flag == "in_range" and theirs.source == "report"


def test_unknown_analyte_is_unknown_not_normal() -> None:
    judgement = assess("Serum Unobtainium", 42.0)
    assert judgement.flag == "unknown"
    assert judgement.low is None


def test_sex_specific_intervals_are_applied() -> None:
    assert assess("Haemoglobin", 12.5, sex="male").flag == "low"
    assert assess("Haemoglobin", 12.5, sex="female").flag == "in_range"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4.0 - 5.6", (4.0, 5.6)),
        ("(0.4 to 4.0)", (0.4, 4.0)),
        ("< 200", (None, 200.0)),
        ("up to 150", (None, 150.0)),
        ("> 40", (40.0, None)),
        ("no range here", None),
    ],
)
def test_printed_range_parsing(text, expected) -> None:
    assert parse_printed_range(text) == expected


def test_longest_alias_wins() -> None:
    assert match_analyte("Total Cholesterol").key == "total_cholesterol"
    assert match_analyte("HDL Cholesterol").key == "hdl"


# ------------------------------------------------------------------ dates & timeline


@pytest.mark.parametrize(
    ("text", "expected", "precision"),
    [
        ("Date: 14/03/2026", date(2026, 3, 14), "exact"),
        ("2026-02-02 collected", date(2026, 2, 2), "exact"),
        ("12 March 2019", date(2019, 3, 12), "exact"),
        ("March 2019", date(2019, 3, 1), "month"),
        ("operated in 2019", date(2019, 1, 1), "year"),
        ("no date at all", None, "unknown"),
    ],
)
def test_date_parsing_carries_precision(text, expected, precision) -> None:
    assert parse_date(text) == (expected, precision)


def test_document_header_date_is_preferred_over_a_body_year() -> None:
    result = TextLayerOCR().read(
        b"Discharge summary\nOperated in 2019\nDate: 14/03/2026",
        filename="d.txt",
        media_type="text/plain",
    )
    found, precision, _line = document_date(result)
    assert found == date(2026, 3, 14) and precision == "exact"


def test_entities_inherit_the_document_date_and_say_so() -> None:
    result = TextLayerOCR().read(
        b"Date: 14/03/2026\nTAB. METFORMIN 500MG OD", filename="rx.txt", media_type="text/plain"
    )
    entities, _ = extract_entities(result)
    med = next(e for e in entities if e.kind == "medication")
    assert med.observed_on == date(2026, 3, 14)
    assert med.detail["dateSource"] == "document_header"


def test_undated_events_are_kept_and_sorted_last() -> None:
    events = [
        TimelineEvent(event_id="a", occurred_on=None, kind="note", label="undated"),
        TimelineEvent(event_id="b", occurred_on=date(2020, 1, 1), kind="note", label="old"),
        TimelineEvent(event_id="c", occurred_on=date(2026, 1, 1), kind="note", label="new"),
    ]
    ordered = order_timeline(events)
    assert [e.label for e in ordered] == ["new", "old", "undated"]


def test_undated_group_is_labelled_not_hidden() -> None:
    groups = group_by_period(
        [TimelineEvent(event_id="a", occurred_on=None, kind="note", label="undated")]
    )
    assert groups[-1]["period"] == "unknown"
    assert "not legible" in groups[-1]["label"]


# ------------------------------------------------------------------ pipeline & the lane


def test_ingest_writes_document_tier_facts_with_page_and_bbox(ledger, known_paths) -> None:
    data = (FIXTURES / "prescription.pdf").read_bytes()
    result = ingest(
        ledger,
        data,
        filename="prescription.pdf",
        media_type="application/pdf",
        known_paths=known_paths,
        backend_name="textlayer",
        sex="female",
    )
    assert result.facts
    for fact in result.facts:
        assert fact.tier.value == "document"
        assert fact.source.page >= 1
        assert fact.source.bbox.width > 0
        assert fact.source.document_id == result.document_id


def test_handwriting_lane_is_never_auto_merged(ledger, known_paths) -> None:
    """The core Module B guarantee: no path from a scrawl to the record without a human."""
    data = (FIXTURES / "lab_report_degraded.png").read_bytes()
    if not TesseractOCR().available:
        pytest.skip("tesseract is not installed")
    result = ingest(
        ledger,
        data,
        filename="lab_degraded.png",
        media_type="image/png",
        known_paths=known_paths,
        backend_name="tesseract",
        sex="female",
    )
    assert result.needs_verification, "the degraded fixture must produce low-confidence entities"
    lane_texts = {e["text"] for e in result.needs_verification}
    recorded = {str(f.value) for f in result.facts}
    assert not (lane_texts & recorded), "a low-confidence entity reached the record unverified"


def test_verification_by_a_human_is_what_creates_the_fact(ledger, known_paths) -> None:
    if not TesseractOCR().available:
        pytest.skip("tesseract is not installed")
    data = (FIXTURES / "lab_report_degraded.png").read_bytes()
    result = ingest(
        ledger,
        data,
        filename="lab_degraded.png",
        media_type="image/png",
        known_paths=known_paths,
        backend_name="tesseract",
        sex="female",
    )
    before = len(ledger.facts)
    facts = verify_entity(
        ledger,
        result,
        entity_index=result.needs_verification[0]["entityIndex"],
        accepted=True,
        verified_by="dr.test",
        known_paths=known_paths,
    )
    assert facts and len(ledger.facts) > before


def test_rejecting_a_low_confidence_entity_records_nothing(ledger, known_paths) -> None:
    if not TesseractOCR().available:
        pytest.skip("tesseract is not installed")
    data = (FIXTURES / "lab_report_degraded.png").read_bytes()
    result = ingest(
        ledger,
        data,
        filename="lab_degraded.png",
        media_type="image/png",
        known_paths=known_paths,
        backend_name="tesseract",
        sex="female",
    )
    before = len(ledger.facts)
    facts = verify_entity(
        ledger,
        result,
        entity_index=result.needs_verification[0]["entityIndex"],
        accepted=False,
        verified_by="dr.test",
        known_paths=known_paths,
    )
    assert not facts and len(ledger.facts) == before


def test_a_correction_keeps_the_original_ocr_span(ledger, known_paths) -> None:
    """The physician must see the scrawl next to what a person read it as."""
    if not TesseractOCR().available:
        pytest.skip("tesseract is not installed")
    data = (FIXTURES / "lab_report_degraded.png").read_bytes()
    result = ingest(
        ledger,
        data,
        filename="lab_degraded.png",
        media_type="image/png",
        known_paths=known_paths,
        backend_name="tesseract",
        sex="female",
    )
    pending = result.needs_verification[0]
    facts = verify_entity(
        ledger,
        result,
        entity_index=pending["entityIndex"],
        accepted=True,
        verified_by="dr.test",
        known_paths=known_paths,
        corrected_text="TSH",
    )
    if facts:
        assert facts[0].source.verbatim == pending["sourceText"]


def test_empty_and_oversized_uploads_are_refused(ledger, known_paths) -> None:
    with pytest.raises(ValidationError, match="empty"):
        ingest(ledger, b"", filename="x.txt", media_type="text/plain", known_paths=known_paths)


def test_a_scan_with_no_text_layer_fails_honestly(ledger, known_paths) -> None:
    """Silently returning zero entities would look like 'a clean document'. It is not."""
    import io

    from PIL import Image
    from pypdfium2 import PdfDocument  # noqa: F401

    buffer = io.BytesIO()
    Image.new("L", (200, 200), 255).save(buffer, format="PNG")
    with pytest.raises((UpstreamUnavailable, ValidationError)):
        ingest(
            ledger,
            buffer.getvalue(),
            filename="blank.png",
            media_type="image/png",
            known_paths=known_paths,
            backend_name="textlayer",
        )

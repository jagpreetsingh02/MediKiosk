"""Phase 1 of the handwriting pipeline — validate, deskew, denoise, contrast, segment.

These are the steps that decide whether the model sees a prescription line or a rectangle of
paper, and they are all deterministic, so they are all testable without a model present.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.errors import ValidationError
from app.modules.documents.preprocess import (
    MIN_DIMENSION,
    estimate_skew,
    prepare,
    validate_image,
)
from app.modules.documents.segmentation import find_columns, find_lines

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"

#: Non-blank lines actually drawn on each fixture by scripts/make_document_fixtures.py.
LINE_COUNTS = {"prescription": 11, "lab_report": 9, "discharge": 7}


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------------------------------------------------ validation


def test_a_file_that_is_not_an_image_is_refused_in_words_a_patient_can_act_on() -> None:
    with pytest.raises(ValidationError) as exc:
        validate_image(b"this is not a png")
    assert "take the picture again" in str(exc.value)


def test_an_image_too_small_to_carry_text_is_refused_rather_than_read() -> None:
    """A thumbnail can be "read" — that is the danger. It cannot be read *correctly*."""
    tiny = _png(Image.new("L", (MIN_DIMENSION - 1, MIN_DIMENSION - 1), 255))
    with pytest.raises(ValidationError) as exc:
        validate_image(tiny)
    assert "too small" in str(exc.value)


def test_an_empty_upload_is_refused() -> None:
    with pytest.raises(ValidationError):
        validate_image(b"")


# ------------------------------------------------------------------ deskew


@pytest.mark.parametrize("applied", [-3.0, -1.5, 2.5, 4.0])
def test_deskew_recovers_the_angle_a_page_was_rotated_by(applied: float) -> None:
    """The whole of line segmentation rests on rows of ink being rows. This is that test."""
    page = Image.new("L", (900, 600), 255)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(page)
    for y in range(80, 520, 40):
        draw.rectangle([120, y, 780, y + 12], fill=20)
    rotated = page.rotate(applied, resample=Image.Resampling.BICUBIC, fillcolor=255)

    prepared = prepare(_png(rotated))
    # The estimate counter-rotates, so it carries the opposite sign to the rotation applied.
    assert prepared.skew_degrees == pytest.approx(-applied, abs=0.6)


def test_a_blank_page_reports_no_skew_rather_than_an_arbitrary_angle() -> None:
    assert estimate_skew(np.zeros((200, 200), dtype=bool)) == 0.0


def test_the_degraded_fixture_is_straightened() -> None:
    """`make_document_fixtures.py` rotates it -0.9°. The estimate must find that back."""
    prepared = prepare((FIXTURES / "prescription_degraded.png").read_bytes())
    assert prepared.skew_degrees == pytest.approx(0.9, abs=0.4)


# ------------------------------------------------------------------ binarisation


def test_grain_on_blank_paper_stays_well_below_the_ink_on_a_written_line() -> None:
    """The regression that made the degraded fixture unsegmentable.

    A local *mean* threshold left every blank row of the degraded fixture reading at ~3% of
    the page width in ink — more than enough to defeat a row-projection profile, which then
    merged the entire prescription into one band and handed the model a whole page.

    The property that matters is not the absolute ink fraction, it is the *separation*: a row
    of writing must stand clear of the noise floor by a wide margin, on a photograph that has
    grain, blur, a lighting gradient and crushed contrast all at once.
    """
    prepared = prepare((FIXTURES / "prescription_degraded.png").read_bytes())
    profile = prepared.ink.sum(axis=1)
    floor = float(np.percentile(profile, 20))
    written = float(np.percentile(profile, 95))
    assert written > floor * 4


def test_a_page_of_pure_noise_yields_no_lines_rather_than_invented_ones() -> None:
    """A photograph of a desk, a wall, or a thumb. There is no safe reading of it.

    Returning nothing is what sends the caller to Tesseract instead of handing a handwriting
    model an arbitrary rectangle, which it would answer with a fluent, entirely invented line.
    """
    rng = np.random.default_rng(20260904)
    noise = rng.normal(210, 12, size=(400, 400)).clip(0, 255).astype(np.uint8)
    prepared = prepare(_png(Image.fromarray(noise, mode="L")))
    assert find_lines(prepared) == []


def test_ink_survives_binarisation_on_a_real_page() -> None:
    prepared = prepare((FIXTURES / "prescription_scan.png").read_bytes())
    assert 0.001 < prepared.ink_fraction < 0.2


def test_every_step_is_recorded_for_provenance() -> None:
    prepared = prepare((FIXTURES / "prescription_degraded.png").read_bytes())
    joined = " ".join(prepared.steps).lower()
    for step in ("validated", "deskew", "denoised", "contrast", "binarised"):
        assert step in joined


# ------------------------------------------------------------------ segmentation


@pytest.mark.parametrize("base", sorted(LINE_COUNTS))
def test_a_clean_scan_segments_into_exactly_the_lines_printed_on_it(base: str) -> None:
    prepared = prepare((FIXTURES / f"{base}_scan.png").read_bytes())
    assert len(find_lines(prepared)) == LINE_COUNTS[base]


@pytest.mark.parametrize("base", sorted(LINE_COUNTS))
def test_a_degraded_photograph_never_loses_lines(base: str) -> None:
    """Over-segmenting is survivable; under-segmenting silently deletes a medicine.

    An extra band is a crop the model reads as empty and reconstruction drops. A missing band
    is a prescription line that never existed as far as the record is concerned. So the only
    bound asserted here is the one whose violation is dangerous.
    """
    prepared = prepare((FIXTURES / f"{base}_degraded.png").read_bytes())
    assert len(find_lines(prepared)) >= LINE_COUNTS[base]


def test_lines_come_back_in_reading_order() -> None:
    prepared = prepare((FIXTURES / "prescription_scan.png").read_bytes())
    lines = find_lines(prepared)
    tops = [line.top for line in lines]
    assert tops == sorted(tops)
    assert [line.index for line in lines] == list(range(len(lines)))


def test_every_line_carries_a_bbox_inside_the_page() -> None:
    """Invariant 2 needs a box per document-tier fact, and a box outside the page is a lie."""
    prepared = prepare((FIXTURES / "prescription_degraded.png").read_bytes())
    for line in find_lines(prepared):
        assert 0.0 <= line.bbox.x <= 1.0
        assert 0.0 <= line.bbox.y <= 1.0
        assert 0.0 < line.bbox.width <= 1.0
        assert 0.0 < line.bbox.height <= 1.0


def test_a_crop_is_the_region_the_box_claims() -> None:
    prepared = prepare((FIXTURES / "prescription_scan.png").read_bytes())
    line = find_lines(prepared)[0]
    crop = line.crop(prepared)
    assert crop.size == (line.width, line.height)


def test_a_blank_page_yields_no_lines_rather_than_one_big_one() -> None:
    """The caller falls back to Tesseract on an empty list. A single page-sized "line" would
    instead be handed to the model, which would return a confident sentence about nothing."""
    prepared = prepare(_png(Image.new("L", (800, 600), 255)))
    assert find_lines(prepared) == []


# ------------------------------------------------------------------ columns


def test_a_two_column_pad_is_split_so_lines_are_not_welded_across_the_gutter() -> None:
    from PIL import ImageDraw

    page = Image.new("L", (1000, 600), 255)
    draw = ImageDraw.Draw(page)
    for y in range(60, 540, 40):
        draw.rectangle([40, y, 380, y + 14], fill=20)
        draw.rectangle([620, y, 950, y + 14], fill=20)
    prepared = prepare(_png(page))
    assert len(find_columns(prepared.ink)) == 2

    lines = find_lines(prepared)
    assert {line.column for line in lines} == {0, 1}
    # Column-major: everything in the left column is emitted before the right one.
    columns = [line.column for line in lines]
    assert columns == sorted(columns)


def test_a_single_column_page_with_a_wide_margin_is_not_split() -> None:
    """Splitting a one-column page cuts every line in half. The guard must be conservative."""
    prepared = prepare((FIXTURES / "prescription_scan.png").read_bytes())
    assert find_columns(prepared.ink) == [(0, prepared.width)]

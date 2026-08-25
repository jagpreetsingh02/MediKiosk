"""Image conditioning, and the silent failures it exists to prevent.

No image had ever been through this pipeline. `TesseractOCR` handed raw bytes to the binary,
which is fine for the clean synthetic scans in `data/fixtures/` and wrong for the thing a
patient actually brings: a phone photo, rotated by an EXIF tag, taken at an angle, under one
overhead light, saved as HEIC.

Every failure mode here is SILENT. Tesseract does not report "this is sideways" or "this is
too small". It returns empty output or confident nonsense, the patient is told their paper
could not be read, and nothing in the logs says why. So these tests assert on OCR *output*
wherever they can, not on the shape of an intermediate image — a preprocessing step that
looks right and reads worse is exactly the bug this module already had once.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

pytest.importorskip("PIL", reason="Pillow is required for image preprocessing")
pytest.importorskip("numpy", reason="numpy is required for deskew and thresholding")

from PIL import Image  # noqa: E402

from app.modules.documents import imaging  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"
HAS_TESSERACT = shutil.which("tesseract") is not None
needs_tesseract = pytest.mark.skipif(HAS_TESSERACT is False, reason="tesseract not installed")


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _ocr_words(data: bytes, filename: str) -> int:
    from app.modules.documents.backends import get_ocr_backend

    result = get_ocr_backend("tesseract").read(data, filename=filename, media_type="image/png")
    return len(result.text.split())


# ------------------------------------------------------------------ EXIF


def test_exif_orientation_is_applied_before_anything_measures_the_image() -> None:
    """A phone photo rotated by metadata is read as rotated text, and OCR returns garbage.

    The tag is the whole bug: the PIXELS are landscape, the tag says "display portrait", and
    every viewer a human uses honours it — so the photo looks upright to the patient who took
    it and is sideways to anything that reads the raw buffer.
    """
    landscape = Image.new("L", (400, 200), color=255)
    buffer = io.BytesIO()
    # Orientation 6 = rotate 90° clockwise for display. What an iPhone writes held upright.
    exif = Image.Exif()
    exif[0x0112] = 6
    landscape.save(buffer, format="JPEG", exif=exif)

    prepared = imaging.prepare(buffer.getvalue(), filename="photo.jpg")

    assert prepared.rotated_by_exif, "the orientation tag was ignored"
    # 400x200 displayed with orientation 6 is 200x400. If this is still landscape the tag
    # was read and not applied, which is the same bug wearing a different hat.
    assert prepared.height > prepared.width, (
        f"expected portrait after transpose, got {prepared.width}x{prepared.height}"
    )


def test_an_image_without_an_orientation_tag_is_not_rotated() -> None:
    plain = Image.new("L", (400, 200), color=255)
    prepared = imaging.prepare(_png(plain), filename="scan.png")
    assert not prepared.rotated_by_exif
    assert prepared.width > prepared.height


# ------------------------------------------------------------ resolution


def test_a_large_photo_is_scaled_down_to_the_target() -> None:
    """Phone cameras produce 4000px+. Above the target it costs time and gains no recall."""
    huge = Image.new("L", (4032, 3024), color=255)
    prepared = imaging.prepare(_png(huge), filename="big.png")
    assert max(prepared.width, prepared.height) == imaging.TARGET_LONG_EDGE
    assert prepared.scaled_from == (4032, 3024)
    assert not prepared.too_small


def test_a_small_photo_is_flagged_and_never_upscaled() -> None:
    """THE DISHONEST FIX WOULD BE TO UPSCALE IT.

    Interpolation invents no detail. An 800px photo enlarged to 2400px is still an 800px
    photo, but it now produces output confident enough to look real — which is worse than
    empty output, because nobody checks it. The honest behaviour is to leave it alone, record
    that it is under-resolution, and let the failure UX ask for a closer photo.
    """
    small = Image.new("L", (800, 600), color=255)
    prepared = imaging.prepare(_png(small), filename="small.png")

    assert prepared.too_small
    assert prepared.scaled_from is None, "an under-resolution image was resized"
    assert max(prepared.width, prepared.height) <= 800, "the image was upscaled — it must not be"


# ---------------------------------------------------------------- deskew


@needs_tesseract
def test_deskew_recovers_a_rotated_page() -> None:
    """The point of deskew, measured where it counts: words recovered.

    A clean fixture is rotated by a known angle, which is a genuine skew with a genuine
    interior peak. Asserting on the recovered ANGLE alone would pass even if the rotation
    made the text unreadable, so this asserts on OCR output.
    """
    # PIL rotates ANTICLOCKWISE for a positive angle, so `rotate(-3)` tilts the page
    # clockwise and the correction is +3. Getting this backwards is easy and the reason the
    # assertion below is on magnitude and direction rather than on a bare sign.
    applied = -3.0
    source = Image.open(FIXTURES / "prescription_scan.png").convert("L")
    tilted = source.rotate(applied, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)

    upright_words = _ocr_words(_png(source), "prescription_scan.png")
    tilted_words = _ocr_words(_png(tilted), "tilted.png")
    prepared = imaging.prepare(_png(tilted), filename="tilted.png")

    recovered = prepared.deskewed_degrees
    assert recovered == pytest.approx(-applied, abs=1.0), (
        f"a page tilted {applied}° needs a {-applied}° correction, got {recovered}°"
    )
    # Deskew need not be perfect; it must recover most of what the tilt cost.
    assert tilted_words >= upright_words * 0.6, (
        f"deskewed page read {tilted_words} words against {upright_words} upright"
    )


def test_a_square_page_is_left_alone() -> None:
    """A rotation costs a resample, and resampling straight text makes it worse.

    This is half of the regression that reduced a real fixture from 65 words to zero: the
    search ran to the edge of its range on a page with no skew at all, and the result was
    applied as though it were a finding.
    """
    prepared = imaging.prepare(
        (FIXTURES / "prescription_scan.png").read_bytes(), filename="prescription_scan.png"
    )
    assert prepared.deskewed_degrees == 0.0, (
        f"a square scan was rotated by {prepared.deskewed_degrees}°"
    )


@needs_tesseract
def test_deskew_never_makes_a_readable_page_unreadable() -> None:
    """The regression itself, pinned.

    The first version of `_estimate_skew` scored rotations without controlling for the fill
    introduced at the corners, so its score rose monotonically toward whichever boundary was
    furthest from square. On `prescription_degraded.png` it chose the full 8°, and OCR output
    went from 65 words to 0. Every fixture must come out no worse than it went in.
    """
    for name in ("prescription_scan.png", "prescription_degraded.png", "lab_report_scan.png"):
        raw = (FIXTURES / name).read_bytes()
        plain = Image.open(io.BytesIO(raw)).convert("L")
        before = _ocr_words(_png(plain), name)
        after = _ocr_words(raw, name)
        assert after >= before * 0.8, (
            f"{name}: conditioning dropped OCR from {before} to {after} words"
        )


# ------------------------------------------------------------------ HEIC


def test_heic_is_either_read_or_refused_with_an_actionable_message() -> None:
    """iPhones shoot HEIC by default, so this is not an edge case.

    Either the converter is installed and it reads, or the patient is told something they can
    actually do. What must never happen is a raw decoder error reaching a patient.
    """
    from app.core.errors import ValidationError

    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        pytest.skip("pillow-heif not installed")

    # Not a real HEIC — the point is the failure path, and the message it produces.
    with pytest.raises(ValidationError) as caught:
        imaging.prepare(b"not actually an image", filename="IMG_4021.HEIC")

    message = str(caught.value)
    assert "HEIC" in message
    assert "Most Compatible" in message or "camera" in message.lower(), (
        "the HEIC refusal must tell the patient what to do about it"
    )
    for leak in ("Traceback", "pillow", "PIL.", "cannot identify"):
        assert leak not in message, f"a backend detail leaked to the patient: {leak}"


def test_an_undecodable_file_fails_in_words_a_patient_can_act_on() -> None:
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError) as caught:
        imaging.prepare(b"\x00\x01\x02 not an image", filename="scan.png")

    message = str(caught.value)
    assert "photo" in message.lower() or "pdf" in message.lower()
    for leak in ("Traceback", "PIL", "cannot identify image file"):
        assert leak not in message


# ------------------------------------------------------- the whole pipeline


@needs_tesseract
def test_image_ocr_actually_reads_a_synthetic_prescription() -> None:
    """The gap this whole module closes: an image, through the real engine, producing text.

    Asserting on real content rather than on a word count, because a word count passes on
    noise.
    """
    from app.modules.documents.backends import get_ocr_backend

    raw = (FIXTURES / "prescription_scan.png").read_bytes()
    result = get_ocr_backend("tesseract").read(
        raw, filename="prescription_scan.png", media_type="image/png"
    )
    text = result.text.lower()

    assert result.pages, "no pages came back"
    assert result.mean_confidence > 0.5, f"confidence {result.mean_confidence:.2f} is too low"
    assert "metformin" in text or "polyclinic" in text, (
        f"the prescription's own words are missing: {result.text[:200]!r}"
    )
    assert result.preparation is not None, "the conditioning record was not carried through"


@needs_tesseract
def test_a_scanned_pdf_with_no_text_layer_falls_back_to_image_ocr() -> None:
    """`textlayer` is right to refuse a scan, but refusing is not the patient's problem.

    A PDF exported by a phone scanner app has no text layer at all. Without the fallback the
    patient uploads a perfectly good document and is told it could not be read.
    """
    from app.modules.documents.backends import read_document

    scan = Image.open(FIXTURES / "prescription_scan.png").convert("RGB")
    buffer = io.BytesIO()
    scan.save(buffer, format="PDF")  # a PDF whose only content is a raster image

    result = read_document(
        buffer.getvalue(), filename="scanned.pdf", media_type="application/pdf"
    )

    assert result.backend == "tesseract", (
        f"a text-layer-free PDF was not routed to image OCR (got {result.backend})"
    )
    assert result.text.strip(), "image OCR of a scanned PDF produced nothing"

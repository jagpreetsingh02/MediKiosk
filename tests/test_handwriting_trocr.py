"""Phase 2 — the TrOCR handwriting backend, and the fallbacks that make it safe to have.

None of these tests need torch, the network, or the model. That is deliberate: every path
tested here is a path that must work *when the model is not there*, and a test that only runs
on a machine with a 400 MB checkpoint downloaded is not a test of the fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contracts.provenance import BoundingBox
from app.core.errors import UpstreamUnavailable, ValidationError
from app.modules.documents import trocr as trocr_module
from app.modules.documents.backends import (
    OCRBlock,
    OCRPage,
    OCRResult,
    UnsupportedMedia,
    _chain,
    available_backends,
    read_document,
)
from app.modules.documents.trocr import (
    _REPEAT,
    LineReading,
    MedicalPrescriptionTrOCR,
    _agreement,
    corroborate,
)

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"


# ------------------------------------------------------------------ the chain


def test_tesseract_is_last_in_every_chain() -> None:
    """The floor of the system: the one engine with no optional dependency and no network."""
    for media_type, filename in (
        ("image/png", "photo.png"),
        ("image/jpeg", "photo.jpg"),
        ("application/pdf", "scan.pdf"),
        ("application/octet-stream", "mystery.heic"),
    ):
        assert _chain(media_type, filename)[-1] == "tesseract"


def test_a_photograph_goes_to_the_handwriting_model_first() -> None:
    assert _chain("image/jpeg", "rx.jpg")[0] == "trocr"


def test_a_pdf_goes_to_its_text_layer_first() -> None:
    """When a text layer exists it is exact, and no recognition can beat exact."""
    assert _chain("application/pdf", "report.pdf")[0] == "textlayer"


def test_about_reports_what_each_engine_is_for_not_just_whether_it_loaded() -> None:
    backends = {b["name"]: b for b in available_backends()}
    assert set(backends) == {"textlayer", "tesseract", "trocr"}
    assert "fallback" in str(backends["tesseract"]["role"])
    assert isinstance(backends["trocr"]["available"], bool)


# ------------------------------------------------------------------ availability


def test_the_backend_reports_itself_unavailable_rather_than_failing_at_read_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trocr_module, "dependencies_available", lambda: False)
    backend = MedicalPrescriptionTrOCR()
    assert backend.available is False
    with pytest.raises(UpstreamUnavailable):
        backend.read(b"x", filename="a.png", media_type="image/png")


def test_the_master_switch_turns_the_model_off_on_a_machine_that_could_run_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(trocr_module, "dependencies_available", lambda: True)
    monkeypatch.setattr(settings, "handwriting_ocr_enabled", False)
    assert MedicalPrescriptionTrOCR().available is False


def test_the_handwriting_model_refuses_plain_text_rather_than_hallucinating_over_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trocr_module, "dependencies_available", lambda: True)
    backend = MedicalPrescriptionTrOCR()
    with pytest.raises(UnsupportedMedia):
        backend.read(b"TAB METFORMIN 500", filename="rx.txt", media_type="text/plain")


def test_dependencies_check_does_not_touch_the_network() -> None:
    """`/about` calls this on every request. A check that downloaded would hang the endpoint."""
    import inspect

    source = inspect.getsource(trocr_module.dependencies_available)
    assert "find_spec" in source
    for forbidden in ("from_pretrained", "requests", "httpx", "hf_hub"):
        assert forbidden not in source


# ------------------------------------------------------------------ fallback


def _fake_engine(name: str, *, raises: Exception | None = None, text: str = "read"):
    class Fake:
        def __init__(self) -> None:
            self.available = True
            self.name = name

        def read(self, data: bytes, *, filename: str, media_type: str) -> OCRResult:
            if raises is not None:
                raise raises
            return OCRResult(
                backend=name,
                pages=(
                    OCRPage(
                        page=1,
                        blocks=(
                            OCRBlock(
                                text=text,
                                bbox=BoundingBox(x=0, y=0, width=1, height=1),
                                confidence=0.9,
                                engine=name,
                            ),
                        ),
                        width=100,
                        height=100,
                    ),
                ),
            )

    return Fake


@pytest.mark.parametrize(
    "failure",
    [
        UpstreamUnavailable("torch is not installed"),
        UpstreamUnavailable("gated repo: 401"),
        UpstreamUnavailable("inference failed"),
        UpstreamUnavailable("no readable lines"),
        UnsupportedMedia("wrong engine"),
    ],
    ids=["no-deps", "auth-fails", "inference-fails", "no-text", "wrong-media"],
)
def test_every_way_the_model_can_fail_lands_on_tesseract(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """The five failure modes the brief names, and they all have the same consequence."""
    registry = {
        "trocr": _fake_engine("trocr", raises=failure),
        "tesseract": _fake_engine("tesseract", text="tesseract read this"),
        "textlayer": _fake_engine("textlayer"),
    }
    monkeypatch.setattr(
        "app.modules.documents.backends._backend_class", lambda name: registry[name]
    )
    result = read_document(b"data", filename="rx.png", media_type="image/png")
    assert result.backend == "tesseract"
    assert result.text == "tesseract read this"


def test_a_bug_in_an_engine_is_not_swallowed_by_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fallback that catches everything turns every bug into a silent quality regression."""
    registry = {
        "trocr": _fake_engine("trocr", raises=ZeroDivisionError("a real bug")),
        "tesseract": _fake_engine("tesseract"),
        "textlayer": _fake_engine("textlayer"),
    }
    monkeypatch.setattr(
        "app.modules.documents.backends._backend_class", lambda name: registry[name]
    )
    with pytest.raises(ZeroDivisionError):
        read_document(b"data", filename="rx.png", media_type="image/png")


def test_an_explicitly_requested_engine_does_not_silently_become_another_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The benchmark compares engines. A fallback would compare an engine with itself."""
    registry = {
        "trocr": _fake_engine("trocr", raises=UpstreamUnavailable("no model")),
        "tesseract": _fake_engine("tesseract"),
        "textlayer": _fake_engine("textlayer"),
    }
    monkeypatch.setattr(
        "app.modules.documents.backends._backend_class", lambda name: registry[name]
    )
    with pytest.raises(UpstreamUnavailable):
        read_document(b"d", filename="rx.png", media_type="image/png", requested="trocr")


def test_an_unknown_engine_name_is_an_error_not_a_default() -> None:
    with pytest.raises(ValidationError):
        read_document(b"d", filename="a.png", media_type="image/png", requested="nonesuch")


# ------------------------------------------------------------------ the yield guard


def _prepared_stub():
    from app.modules.documents.preprocess import prepare

    return prepare((FIXTURES / "prescription_scan.png").read_bytes())


def test_a_page_read_only_in_part_goes_to_tesseract_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard that stops a prescription losing medicines without leaving a gap.

    Measured with the base TrOCR checkpoint on prescription_scan.png: 11 lines segmented,
    3 returned. Those three were confident. Nothing downstream could have told that eight
    lines — including two of the four drugs — were simply absent.
    """
    from app.modules.documents.segmentation import find_lines

    prepared = _prepared_stub()
    regions = find_lines(prepared)
    assert len(regions) > 5

    def only_two(_prepared, _regions) -> list[LineReading]:
        return [
            LineReading(region=regions[0], text="TAB METFORMIN 500", confidence=0.95),
            LineReading(region=regions[1], text="TAB AMLODIPINE 5", confidence=0.93),
        ]

    monkeypatch.setattr(trocr_module, "read_lines", only_two)
    monkeypatch.setattr(trocr_module, "dependencies_available", lambda: True)
    backend = MedicalPrescriptionTrOCR()
    with pytest.raises(UpstreamUnavailable) as exc:
        backend.read(
            (FIXTURES / "prescription_scan.png").read_bytes(),
            filename="rx.png",
            media_type="image/png",
        )
    assert "too few to trust" in str(exc.value)


def test_a_page_read_in_full_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.documents.segmentation import find_lines

    prepared = _prepared_stub()
    regions = find_lines(prepared)

    monkeypatch.setattr(
        trocr_module,
        "read_lines",
        lambda _p, rs: [LineReading(region=r, text=f"line {r.index}", confidence=0.9) for r in rs],
    )
    monkeypatch.setattr(trocr_module, "dependencies_available", lambda: True)
    result = MedicalPrescriptionTrOCR().read(
        (FIXTURES / "prescription_scan.png").read_bytes(),
        filename="rx.png",
        media_type="image/png",
    )
    assert result.backend == "trocr"
    blocks = result.pages[0].blocks
    assert len(blocks) == len(regions)
    assert all(block.engine == "trocr" for block in blocks)
    assert all(0.0 <= block.bbox.x <= 1.0 for block in blocks)


# ------------------------------------------------------------------ degenerate output


@pytest.mark.parametrize(
    "text",
    ["mg mg mg mg mg mg", "500500500500500500", "TAB TAB TAB TAB TAB TAB"],
)
def test_a_looping_decoder_is_recognised_as_noise(text: str) -> None:
    """Its per-token confidence is HIGH — the model is very sure of its own repetition."""
    assert _REPEAT.search(text) is not None


@pytest.mark.parametrize("text", ["TAB AUGMENTIN 625 BD x 5d", "PCM 500 SOS", "Pantop 40 OD bf"])
def test_a_real_prescription_line_is_not_mistaken_for_a_loop(text: str) -> None:
    assert _REPEAT.search(text) is None


# ------------------------------------------------------------------ corroboration


def test_agreement_is_computed_on_letters_and_digits_only() -> None:
    assert _agreement("TAB. AUGMENTIN 625", "TAB AUGMENTIN 625") == pytest.approx(1.0)
    assert _agreement("AUGMENTIN", "AZITHROMYCIN") < 0.6


def test_corroboration_can_only_lower_confidence_never_raise_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two engines can agree on the same misreading — they are looking at the same strokes.

    So agreement is not evidence of correctness and must not buy confidence. Disagreement IS
    evidence that the line is hard, and is allowed to push it toward a human.
    """
    from app.core.config import settings

    prepared = _prepared_stub()
    from app.modules.documents.segmentation import find_lines

    region = find_lines(prepared)[0]

    monkeypatch.setattr(settings, "ocr_corroborate", True)
    monkeypatch.setattr("app.modules.documents.trocr.shutil.which", lambda _n: "/usr/bin/tesseract")

    for other, original in (("identical text", 0.5), ("something else entirely", 0.5)):
        monkeypatch.setattr(
            "app.modules.documents.trocr._tesseract_line", lambda _i, _b, o=other: o
        )
        out = corroborate(
            prepared, [LineReading(region=region, text="identical text", confidence=original)]
        )
        assert out[0].confidence <= original
        assert out[0].corroboration is not None


def test_corroboration_is_skipped_for_lines_a_second_opinion_cannot_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    prepared = _prepared_stub()
    from app.modules.documents.segmentation import find_lines

    region = find_lines(prepared)[0]
    monkeypatch.setattr(settings, "ocr_corroborate", True)
    monkeypatch.setattr("app.modules.documents.trocr.shutil.which", lambda _n: "/usr/bin/tesseract")

    def explode(*_args, **_kwargs):
        raise AssertionError("a confident line must not cost a subprocess")

    monkeypatch.setattr("app.modules.documents.trocr._tesseract_line", explode)
    confident = LineReading(region=region, text="TAB AUGMENTIN 625", confidence=0.97)
    assert corroborate(prepared, [confident])[0].corroboration is None


def test_no_second_opinion_is_not_the_same_as_disagreement() -> None:
    """`None` and `0.0` must never render the same way on a physician's screen."""
    prepared = _prepared_stub()
    from app.modules.documents.segmentation import find_lines

    region = find_lines(prepared)[0]
    reading = LineReading(region=region, text="x", confidence=0.5)
    assert reading.corroboration is None

"""Stage 5-8: `khedim/Medical-Prescription-OCR` over one line at a time, then reassembled.

This is the engine the whole handwriting upgrade exists for, and the discipline around it
matters more than the call into it.

**It never sees a page.** The model is a TrOCR encoder-decoder fine-tuned on crops of single
handwritten prescription lines. Its decoder is a language model with a bounded output length
and no concept of a newline. Given a whole prescription it does not fail — it emits one
fluent, plausible line and drops the rest, and that failure is indistinguishable from success
at the API boundary. So `preprocess.prepare()` and `segmentation.find_lines()` run first,
always, and the model is only ever asked the question it was trained on.

**It reports a real confidence.** Not a constant, not a proxy for string length: the geometric
mean of the model's own per-token probabilities, from `compute_transition_scores`. That number
is what decides whether a medicine reaches the record or the verification lane, so inventing
it would be the single most dangerous line of code in this module.

**It refuses rather than guesses.** Missing dependencies, a failed download, an inference
error, no segmentable lines, or nothing but empty crops all raise `UpstreamUnavailable`, and
`read_document()` falls back to Tesseract. A handwriting model handed an unreadable input
does not return nothing — it returns a confident sentence — so every path where the input is
not what the model expects has to be closed *before* the call, not after.

**Tesseract can corroborate but never contributes text.** Where a line's confidence lands in
the ambiguous band, the same crop is read again with Tesseract and the two strings compared.
Agreement is recorded; disagreement *lowers* confidence toward the verification lane. The two
readings are never spliced, because a sentence half from one engine and half from another is
a sentence no engine actually read and no human ever wrote.
"""

from __future__ import annotations

import difflib
import importlib.util
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.core.logging import get_logger
from app.modules.documents.backends import OCRBlock, OCRPage, OCRResult, UnsupportedMedia
from app.modules.documents.preprocess import PreparedImage, prepare
from app.modules.documents.segmentation import LineRegion, find_lines

log = get_logger(__name__)

#: Cached across calls. Loading the weights takes seconds; a kiosk uploading three documents
#: in one session must not pay that three times.
_LOADED: dict[str, Any] = {}

#: A decoder that has started looping emits the same short token forever. The text is not a
#: reading of anything, and its per-token confidence is *high* — the model is very sure about
#: its own repetition — so confidence alone cannot catch it.
_REPEAT = re.compile(r"(.{1,12}?)\1{4,}")


@dataclass(frozen=True, slots=True)
class LineReading:
    """One crop, read. Carries where it came from so the block can cite it."""

    region: LineRegion
    text: str
    confidence: float
    corroboration: float | None = None
    corroborating_text: str | None = None


def dependencies_available() -> bool:
    """Whether torch and transformers can be imported at all.

    Deliberately does *not* touch the network or the model cache. `available` is read by
    `/about` on every request, and a availability check that tries a download would turn a
    status endpoint into a several-minute hang the first time anyone opened it.
    """
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "transformers"))


def _device() -> str:
    import torch

    choice = settings.trocr_device
    if choice != "auto":
        return choice
    if torch.cuda.is_available():
        return "cuda"
    # Apple Silicon. The kiosk demo machine is one, and CPU inference on 15 line crops is
    # roughly 8× slower there.
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _auth() -> dict[str, str]:
    """The Hugging Face token, as a kwarg, or nothing at all.

    Returned as a dict rather than a value so the token never appears in a call signature,
    a log line or a traceback frame that renders its arguments. `khedim/Medical-Prescription-OCR`
    is gated, so on a kiosk that is meant to run the model this is the difference between
    working and a 401 — and on one that is not, its absence is a supported configuration,
    not an error.
    """
    return {"token": settings.hf_token} if settings.hf_token else {}


def _resolve(kind: str, loader: Any, candidates: list[str]) -> Any:
    """Load one half of the processor from the first checkpoint that actually has it.

    A `TrOCRProcessor` is a tokenizer plus an image processor, and community fine-tunes
    publish them inconsistently — `khedim/Medical-Prescription-OCR` ships `tokenizer.json`
    and no `preprocessor_config.json` at all. Asking `TrOCRProcessor.from_pretrained()` for
    both at once therefore fails on the half that is missing and throws away the half that is
    present, which is why the two are resolved independently here.

    The order matters: the fine-tune first, because a fine-tune that *did* change its
    tokenizer must be read with its own, and only then the base checkpoints.
    """
    errors: list[str] = []
    for candidate in candidates:
        try:
            return loader.from_pretrained(candidate, **_auth())
        except Exception as exc:
            errors.append(f"{candidate}: {str(exc)[:80]}")
    raise UpstreamUnavailable(
        f"No {kind} could be loaded for the handwriting model ({'; '.join(errors)})."
    )


def load_model() -> tuple[Any, Any, str]:
    """Processor, model and device. Cached. Raises `UpstreamUnavailable` on any failure.

    Every way this can go wrong ends in the same place, because they all mean the same thing
    to the caller — *use Tesseract*: torch not installed, the repo gated behind a Hugging Face
    token the kiosk does not have, no network, a corrupt cache, an incompatible transformers
    version. None of those is a patient's problem and none of them should surface as an error
    on a kiosk screen.
    """
    if "model" in _LOADED:
        return _LOADED["processor"], _LOADED["model"], _LOADED["device"]

    if not dependencies_available():
        raise UpstreamUnavailable(
            "Handwriting recognition needs `torch` and `transformers` "
            "(pip install -r requirements-handwriting.txt)."
        )

    model_id = settings.trocr_model_id
    try:
        import torch
        from transformers import (
            AutoImageProcessor,
            AutoTokenizer,
            TrOCRProcessor,
            VisionEncoderDecoderModel,
        )

        tokenizer = _resolve(
            "tokenizer",
            AutoTokenizer,
            [model_id, settings.trocr_processor_id, settings.trocr_tokenizer_id],
        )
        image_processor = _resolve(
            "image processor", AutoImageProcessor, [model_id, settings.trocr_processor_id]
        )
        processor = TrOCRProcessor(image_processor=image_processor, tokenizer=tokenizer)

        # `**_auth()` is a token or nothing, and transformers' overloads do not describe a
        # kwargs splat; the alternative is repeating the whole call under an `if`.
        model = VisionEncoderDecoderModel.from_pretrained(model_id, **_auth())  # type: ignore[arg-type]
        device = _device()
        model.to(device)  # type: ignore[arg-type]
        model.eval()
        torch.set_grad_enabled(False)
    except UpstreamUnavailable:
        raise
    except Exception as exc:
        log.error("ocr.trocr_unavailable", model=model_id, error=str(exc)[:200])
        raise UpstreamUnavailable(
            f"The handwriting model could not be loaded: {str(exc)[:160]}"
        ) from exc

    _LOADED.update({"processor": processor, "model": model, "device": device})
    log.info(
        "ocr.trocr_loaded",
        model=model_id,
        device=device,
        tokenizer=type(tokenizer).__name__,
        image_processor=type(image_processor).__name__,
    )
    return processor, model, device


def _confidence(model: Any, generated: Any) -> list[float]:
    """Per-line confidence: the geometric mean of the model's own token probabilities.

    Geometric rather than arithmetic because the tokens are a joint probability, and because
    it is the harsher of the two — one token the model was unsure about drags the line's
    score down rather than being averaged away by a run of easy ones. In a dosage that is
    exactly the token that matters.

    Padding is excluded, otherwise a short line scores higher than a long one purely for
    being short.
    """
    import torch

    scores = model.compute_transition_scores(
        generated.sequences, generated.scores, normalize_logits=True
    )
    finite = torch.isfinite(scores)
    out: list[float] = []
    for row, mask in zip(scores, finite, strict=True):
        kept = row[mask]
        out.append(float(kept.mean().exp()) if kept.numel() else 0.0)
    return out


def read_lines(prepared: PreparedImage, regions: list[LineRegion]) -> list[LineReading]:
    """Run the model over every crop, in batches, and return what it actually read."""
    import torch

    processor, model, device = load_model()
    readings: list[LineReading] = []
    batch_size = max(settings.trocr_batch_size, 1)

    for start in range(0, len(regions), batch_size):
        batch = regions[start : start + batch_size]
        # TrOCR's image processor expects RGB; a greyscale crop silently loses the channel
        # dimension and the encoder sees a batch of the wrong rank.
        images = [region.crop(prepared).convert("RGB") for region in batch]
        try:
            pixels = processor(images=images, return_tensors="pt").pixel_values.to(device)
            generated = model.generate(
                pixels,
                max_new_tokens=settings.trocr_max_new_tokens,
                num_beams=1,  # greedy: reproducible, and the confidence means what it says
                output_scores=True,
                return_dict_in_generate=True,
            )
            texts = processor.batch_decode(generated.sequences, skip_special_tokens=True)
            confidences = _confidence(model, generated)
        except Exception as exc:
            log.error("ocr.trocr_inference_failed", lines=len(batch), error=str(exc)[:200])
            raise UpstreamUnavailable(
                f"Handwriting recognition failed on this page: {str(exc)[:160]}"
            ) from exc

        for region, text, confidence in zip(batch, texts, confidences, strict=True):
            cleaned = text.strip()
            if not cleaned or not any(ch.isalnum() for ch in cleaned):
                continue
            if _REPEAT.search(cleaned):
                # The decoder looped. Its own confidence is high and meaningless; the text
                # describes nothing on the page, so it is dropped rather than de-rated.
                log.info("ocr.trocr_degenerate_output", line=region.index, text=cleaned[:40])
                continue
            readings.append(LineReading(region=region, text=cleaned, confidence=confidence))

    del torch
    return readings


# ---------------------------------------------------------------- corroboration


def _tesseract_line(image: Image.Image, binary: str) -> str | None:
    """The same crop, read by Tesseract. `--psm 7` is "this image is one line of text"."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "line.png"
        image.save(path)
        try:
            completed = subprocess.run(
                [binary, str(path), "stdout", "-l", "eng", "--psm", "7"],
                check=True,
                capture_output=True,
                timeout=20,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    return completed.stdout.decode("utf-8", "replace").strip() or None


def _agreement(left: str, right: str) -> float:
    def fold(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.casefold())

    return difflib.SequenceMatcher(None, fold(left), fold(right)).ratio()


def corroborate(prepared: PreparedImage, readings: list[LineReading]) -> list[LineReading]:
    """Second-read the ambiguous lines with Tesseract, and let disagreement cost confidence.

    Only the ambiguous band is re-read — lines the model was confident about, and lines it
    was hopeless on, are not going to have their fate changed by a second opinion, and a
    subprocess per line is not free.

    **Agreement never raises confidence.** Two engines can agree on the same misreading —
    they see the same strokes — so treating agreement as evidence of correctness would be
    building a second, worse confidence score on top of the model's real one. Disagreement,
    on the other hand, is genuine evidence that the line is hard, and it is allowed to push
    the line into the lane where a human reads it. The asymmetry is the point.
    """
    if not settings.ocr_corroborate:
        return readings
    binary = shutil.which("tesseract")
    if binary is None:
        return readings

    low = settings.trocr_min_line_confidence
    high = settings.ocr_low_confidence_threshold
    out: list[LineReading] = []
    for reading in readings:
        if not (low <= reading.confidence < high):
            out.append(reading)
            continue
        other = _tesseract_line(reading.region.crop(prepared), binary)
        if other is None:
            out.append(reading)
            continue
        ratio = _agreement(reading.text, other)
        # Scaled, never boosted: at full agreement the model's own number is kept intact.
        penalised = reading.confidence * (0.6 + 0.4 * ratio)
        out.append(
            LineReading(
                region=reading.region,
                text=reading.text,
                confidence=round(min(penalised, reading.confidence), 4),
                corroboration=round(ratio, 3),
                corroborating_text=other,
            )
        )
    return out


# ---------------------------------------------------------------- the backend


class MedicalPrescriptionTrOCR:
    """`khedim/Medical-Prescription-OCR`, line by line, with an honest confidence per line."""

    name = "trocr"

    def __init__(self) -> None:
        self.available = settings.handwriting_ocr_enabled and dependencies_available()

    def read(self, data: bytes, *, filename: str, media_type: str) -> OCRResult:
        if not self.available:
            raise UpstreamUnavailable(
                "Handwriting recognition is not installed on this kiosk."
            )

        is_pdf = media_type == "application/pdf" or filename.lower().endswith(".pdf")
        if not is_pdf and not (
            media_type.startswith("image/")
            or filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".heic"))
        ):
            raise UnsupportedMedia(
                f"{self.name} reads photographs and scanned PDFs, not {media_type!r}."
            )

        pages = self._read_pdf(data) if is_pdf else [self._read_page(data, page_number=1)]
        pages = [page for page in pages if page.blocks]
        if not pages:
            # Nothing segmentable, or every crop came back empty. Both mean "this is not a
            # page of handwriting the model can read", and both must reach Tesseract.
            raise UpstreamUnavailable(
                "The handwriting model found no readable lines on this page."
            )
        return OCRResult(backend=self.name, pages=tuple(pages))

    def _read_pdf(self, data: bytes) -> list[OCRPage]:
        import io

        import pypdfium2

        document = pypdfium2.PdfDocument(io.BytesIO(data))
        pages: list[OCRPage] = []
        try:
            for index in range(len(document)):
                buffer = io.BytesIO()
                document[index].render(scale=settings.trocr_render_dpi / 72).to_pil().save(
                    buffer, format="PNG"
                )
                pages.append(self._read_page(buffer.getvalue(), page_number=index + 1))
        finally:
            document.close()
        return pages

    def _read_page(self, image_bytes: bytes, *, page_number: int) -> OCRPage:
        prepared = prepare(image_bytes)
        regions = find_lines(prepared)
        if not regions:
            return OCRPage(
                page=page_number, blocks=(), width=prepared.width, height=prepared.height
            )
        if len(regions) > settings.trocr_max_lines:
            # A page segmenting into hundreds of bands is not a prescription — it is a
            # photograph of a textured surface, or a table. Reading 400 crops would take
            # minutes and produce nothing. Refusing sends it to Tesseract in one pass.
            log.warning(
                "ocr.trocr_too_many_lines", lines=len(regions), limit=settings.trocr_max_lines
            )
            raise UpstreamUnavailable(
                f"This page segmented into {len(regions)} regions, which is not a prescription."
            )

        readings = corroborate(prepared, read_lines(prepared, regions))
        blocks = tuple(
            OCRBlock(
                text=reading.text,
                bbox=reading.region.bbox,
                confidence=round(reading.confidence, 4),
                handwritten=reading.confidence <= settings.ocr_low_confidence_threshold,
                engine=self.name,
                corroboration=reading.corroboration,
            )
            for reading in readings
            if reading.confidence >= settings.trocr_min_line_confidence
        )
        yield_ratio = len(blocks) / len(regions)
        log.info(
            "ocr.trocr_page_read",
            page=page_number,
            regions=len(regions),
            kept=len(blocks),
            line_yield=round(yield_ratio, 3),
            skew=prepared.skew_degrees,
        )
        if yield_ratio < settings.trocr_min_line_yield:
            # THE MOST IMPORTANT GUARD IN THIS FILE.
            #
            # Every line the model refuses is dropped individually and correctly — an empty
            # crop, a looping decoder, a confidence too low to trust. But a page where most
            # of the lines were dropped is not a page that was partly read; it is a page the
            # model could not read, returning the two or three lines it happened to be
            # confident about. Handed on, that is a PRESCRIPTION WITH MEDICINES MISSING, and
            # nothing downstream can tell that anything is absent: the record shows two drugs
            # and there is no gap where the other three were.
            #
            # Measured on prescription_scan.png with the base TrOCR checkpoint: 11 lines
            # segmented, 3 kept, and the three kept were confident and wrong-ish. Tesseract
            # read all 11. A worse reading of the whole prescription beats a good reading of
            # a quarter of it, so the page goes to Tesseract in full.
            raise UpstreamUnavailable(
                f"The handwriting model read only {len(blocks)} of {len(regions)} lines on "
                "this page — too few to trust as a whole prescription."
            )
        return OCRPage(
            page=page_number, blocks=blocks, width=prepared.width, height=prepared.height
        )

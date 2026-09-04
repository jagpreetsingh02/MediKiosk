"""Stage 1 and 2 of the handwriting pipeline: make the photograph readable, then measure it.

A phone photograph of a prescription is not an image of text. It is an image of a *sheet of
paper* — held at an angle, lit from one side, creased, and compressed by a messaging app on
the way in. `khedim/Medical-Prescription-OCR` is a TrOCR model trained on tight crops of
single handwritten prescription lines; handing it a whole photograph is handing it something
it has never seen. Everything here exists to turn the first thing into the second.

The four steps, in the order they must run:

1. **validate** — is this an image at all, and one big enough to have readable text on it?
2. **deskew** — a rotated line breaks row-projection segmentation completely, so this runs
   before anything measures rows.
3. **denoise** — JPEG ringing and sensor grain become ink in the binarisation otherwise.
4. **contrast** — a photograph lit from one side has no single global threshold that works,
   so the normalisation is *local*, over a window, not a curve applied to the whole frame.

Every step records what it did in `PreparedImage.steps`. That list is provenance: when a
physician asks why a line was read the way it was, "we rotated it 3.5° and normalised
contrast over a 41px window" is an answer, and "we cleaned it up" is not.

Pillow and numpy only, both already dependencies. No OpenCV: the deskew and the local
threshold here are twenty lines of numpy each, and adding a 60 MB wheel to a kiosk image for
two functions is a bad trade.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from app.core.errors import ValidationError
from app.core.logging import get_logger

log = get_logger(__name__)

#: Below this in either dimension there is nothing a handwriting model can do. A 200px-wide
#: photograph of a prescription is not a hard case, it is an unusable one, and saying so is
#: better than returning a confident transcription of noise.
MIN_DIMENSION = 120

#: Above this, downscale before doing anything. A 12 MP phone photo costs ~40x more to
#: deskew than the 2200px version and the projection profile is identical.
MAX_DIMENSION = 2400

#: Deskew search. ±8° covers a hand-held photograph of a sheet on a table; beyond that the
#: page is rotated, not skewed, and a projection search would lock onto the wrong axis.
SKEW_LIMIT_DEGREES = 8.0
SKEW_COARSE_STEP = 1.0
SKEW_FINE_STEP = 0.2
#: Below this the rotation costs more (resampling blur) than the alignment buys.
SKEW_APPLY_THRESHOLD = 0.3

#: Local-contrast window, in pixels, at the working resolution. Roughly two x-heights: wide
#: enough to contain both ink and paper, narrow enough to track a lighting gradient.
CONTRAST_WINDOW = 41

#: Sauvola's k and R. k sets how far below the local mean a pixel must fall to count as ink
#: on *flat* paper; R is the expected dynamic range of an 8-bit image. The published defaults
#: (0.2, 128) are used unchanged — they are tuned for exactly this problem, document
#: binarisation under uneven illumination, and there is nothing in a prescription photograph
#: that argues for different ones.
SAUVOLA_K = 0.2
SAUVOLA_R = 128.0


@dataclass(slots=True)
class PreparedImage:
    """A photograph turned into something a line segmenter and a TrOCR model can use.

    `image` is greyscale-on-white at the working scale and is what gets *cropped and read* —
    TrOCR wants natural greyscale, not a binarisation, because stroke weight carries
    information about which character was written.

    `ink` is the binarised view and is what gets *measured* — segmentation needs a hard
    yes/no per pixel to build a projection profile from.
    """

    image: Image.Image
    ink: np.ndarray
    width: int
    height: int
    skew_degrees: float
    scale: float
    steps: list[str] = field(default_factory=list)

    @property
    def ink_fraction(self) -> float:
        """How much of the page is ink. A sanity signal, not a quality score."""
        return float(self.ink.mean())


def validate_image(data: bytes) -> Image.Image:
    """Open the upload as an image, or say plainly that it is not one.

    Truncated uploads are the common real failure — a kiosk on a slow connection, a patient
    who walked away mid-upload — and Pillow will happily hand back a half-decoded image
    unless `load()` is forced here, where the error can still be turned into a sentence.
    """
    if not data:
        raise ValidationError("That file is empty.")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ValidationError(
            "That file could not be opened as a photograph. Please take the picture again."
        ) from exc

    if image.width < MIN_DIMENSION or image.height < MIN_DIMENSION:
        raise ValidationError(
            f"That picture is {image.width}×{image.height} pixels — too small to read text "
            "from. Please take it again, closer to the paper."
        )
    return image


def _to_working_greyscale(image: Image.Image) -> tuple[Image.Image, float]:
    """Greyscale, upright per EXIF, and no larger than the working resolution."""
    # A phone in portrait writes the rotation into EXIF rather than the pixels. Without this
    # every line on the page is 90° out and segmentation finds one enormous "line".
    image = ImageOps.exif_transpose(image) or image
    if image.mode != "L":
        image = image.convert("L")
    longest = max(image.width, image.height)
    scale = 1.0
    if longest > MAX_DIMENSION:
        scale = MAX_DIMENSION / longest
        image = image.resize(
            (max(int(image.width * scale), 1), max(int(image.height * scale), 1)),
            Image.Resampling.LANCZOS,
        )
    return image, scale


def _window_stats(array: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Local mean and local standard deviation, in four passes over the whole image.

    Summed-area tables, over the values and over their squares. The alternative — a window
    reduction per pixel — is the difference between 40 ms and several seconds on a 2400px
    page, which on a kiosk is the difference between an upload that feels instant and one a
    patient assumes has hung.
    """
    padded = np.pad(array.astype(np.float64), window // 2, mode="edge")
    height, width = array.shape

    def boxsum(values: np.ndarray) -> np.ndarray:
        integral = np.pad(
            values.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)), mode="constant"
        )
        total = (
            integral[window:, window:]
            - integral[:-window, window:]
            - integral[window:, :-window]
            + integral[:-window, :-window]
        )
        return total[:height, :width]

    count = float(window * window)
    mean = boxsum(padded) / count
    mean_square = boxsum(padded * padded) / count
    variance = np.maximum(mean_square - mean * mean, 0.0)
    return mean, np.sqrt(variance)


def _binarise(array: np.ndarray) -> np.ndarray:
    """Ink mask by Sauvola local thresholding. True = ink.

    A *global* threshold fails on the actual input: one side of a hand-held photograph is
    brighter than the other, and any single cut-off either loses the shaded half of the page
    or floods the lit half.

    A local *mean* threshold fixes the lighting but not the grain, and grain is the failure
    that matters here. On flat paper every pixel sits at its own local mean, so a fixed
    offset below the mean turns sensor noise and JPEG ringing into ink — which is exactly
    what happened on the degraded fixture: a 3% ink floor on every blank row, enough to
    defeat line segmentation entirely and merge the whole page into one band.

    Sauvola scales the offset by the *local standard deviation*, so the rule becomes "how far
    below the mean is unusual **for this neighbourhood**". Flat paper has a low deviation and
    therefore a strict threshold that rejects grain; a neighbourhood containing a pen stroke
    has a high deviation and a permissive one that keeps thin strokes. Same window, opposite
    behaviour, which is the property a photograph of handwriting needs.
    """
    mean, deviation = _window_stats(array, CONTRAST_WINDOW)
    threshold = mean * (1.0 + SAUVOLA_K * ((deviation / SAUVOLA_R) - 1.0))
    return array.astype(np.float64) < threshold


def estimate_skew(ink: np.ndarray) -> float:
    """Skew angle in degrees, from the rotation that makes the row profile most peaked.

    Text lines are horizontal bands of ink separated by blank paper. Rotate the page to
    exactly the right angle and the row-ink profile becomes a comb — tall peaks, deep
    troughs. Rotate it wrong and every line smears across its neighbours and the profile
    flattens. So the variance of the row profile *is* the objective function, and the deskew
    is a one-dimensional search over it.

    Coarse then fine, rather than a fine sweep: 1° steps to find the basin, 0.2° inside it.
    A single 0.2° sweep over ±8° costs four times as much for the same answer.
    """
    if not ink.any():
        return 0.0

    # The search runs on a downscaled copy — the profile's shape is a property of the layout,
    # not of the resolution, and this makes the sweep cheap enough to do properly.
    small = ink[:: max(ink.shape[0] // 600, 1), :: max(ink.shape[1] // 600, 1)].astype(np.float32)
    if small.size == 0 or not small.any():
        return 0.0

    def score(angle: float) -> float:
        rotated = _rotate_array(small, angle)
        profile = rotated.sum(axis=1)
        return float(profile.var())

    coarse = np.arange(-SKEW_LIMIT_DEGREES, SKEW_LIMIT_DEGREES + SKEW_COARSE_STEP, SKEW_COARSE_STEP)
    best = max(coarse, key=score)
    fine = np.arange(
        best - SKEW_COARSE_STEP, best + SKEW_COARSE_STEP + SKEW_FINE_STEP, SKEW_FINE_STEP
    )
    return float(max(fine, key=score))


def _rotate_array(array: np.ndarray, degrees: float) -> np.ndarray:
    if abs(degrees) < 1e-6:
        return array
    image = Image.fromarray((array * 255).astype(np.uint8))
    rotated = image.rotate(degrees, resample=Image.Resampling.BILINEAR, fillcolor=0, expand=False)
    return np.asarray(rotated, dtype=np.float32) / 255.0


def prepare(data: bytes) -> PreparedImage:
    """validate → deskew → denoise → contrast, with a record of each step.

    The order is not arbitrary. Deskew is measured on a *binarised* view, so a first pass of
    binarisation happens before rotation; the ink mask is then rebuilt after rotation and
    denoising, because rotation resamples and the first mask no longer describes the pixels.
    """
    steps: list[str] = []
    original = validate_image(data)
    steps.append(f"validated {original.width}×{original.height} {original.mode}")

    working, scale = _to_working_greyscale(original)
    if scale != 1.0:
        steps.append(f"downscaled ×{scale:.3f} to {working.width}×{working.height}")

    array = np.asarray(working, dtype=np.uint8)
    skew = estimate_skew(_binarise(array))

    if abs(skew) >= SKEW_APPLY_THRESHOLD:
        # `fillcolor=255` is white: the corners exposed by the rotation are paper, and
        # filling them with black would put a wedge of "ink" down two edges of the page.
        working = working.rotate(
            skew, resample=Image.Resampling.BICUBIC, fillcolor=255, expand=True
        )
        steps.append(f"deskewed {skew:+.1f}°")
    else:
        steps.append(f"skew {skew:+.1f}° — below the {SKEW_APPLY_THRESHOLD}° correction threshold")

    # Median rather than Gaussian: it removes isolated speckle without softening the stroke
    # edges, and a softened stroke edge is exactly what costs a handwriting model a character.
    working = working.filter(ImageFilter.MedianFilter(size=3))
    steps.append("denoised (3px median)")

    working = ImageOps.autocontrast(working, cutoff=1)
    steps.append("contrast normalised (1% clipped)")

    array = np.asarray(working, dtype=np.uint8)
    ink = _binarise(array)
    steps.append(f"binarised locally over a {CONTRAST_WINDOW}px window")

    return PreparedImage(
        image=working,
        ink=ink,
        width=working.width,
        height=working.height,
        skew_degrees=round(skew, 2),
        scale=scale,
        steps=steps,
    )


def rotate_point(x: float, y: float, prepared: PreparedImage) -> tuple[float, float]:
    """Map a point on the prepared image back to the original photograph, normalised.

    Bounding boxes are measured on the deskewed, downscaled image, but the physician's
    evidence drawer draws them over the *uploaded* file. Without this the highlight lands
    next to the line it claims to be showing, which per `render.py` is worse than no box.
    """
    if abs(prepared.skew_degrees) < SKEW_APPLY_THRESHOLD:
        return x / max(prepared.width, 1), y / max(prepared.height, 1)

    angle = math.radians(-prepared.skew_degrees)
    cx, cy = prepared.width / 2.0, prepared.height / 2.0
    dx, dy = x - cx, y - cy
    rx = cx + dx * math.cos(angle) - dy * math.sin(angle)
    ry = cy + dx * math.sin(angle) + dy * math.cos(angle)
    return (
        min(max(rx / max(prepared.width, 1), 0.0), 1.0),
        min(max(ry / max(prepared.height, 1), 0.0), 1.0),
    )

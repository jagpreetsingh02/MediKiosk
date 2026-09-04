"""Stage 3 and 4: find the text lines on a prepared page, and crop each one.

**This is the step that makes the model work.** `khedim/Medical-Prescription-OCR` is a TrOCR
encoder-decoder fine-tuned on images of *one handwritten prescription line*. Its decoder is a
language model with a bounded output length and no notion of a newline: given a whole
prescription it emits one plausible-looking sentence and drops the rest of the page. That
failure is silent and it looks like a successful read, which is the worst shape a failure can
have in this system. So the page is cut into lines first, always, and the model only ever
sees what it was trained on.

The method is a **projection profile**, not a learned detector, and that is a deliberate
choice under the rule-or-LLM policy. A row of a page either contains ink or it does not; that
is a measurement. It is reproducible, it runs in milliseconds on a kiosk with no GPU, and
when it goes wrong it goes wrong visibly — a band too tall, a band too short — rather than
confidently returning the wrong region. A learned detector would be better on a photograph of
a crumpled page and would cost a second model, a second download, and a second thing that can
hallucinate a region that is not there.

Handles the two layouts that actually arrive: a single column of lines, and the two-column
prescription pad where the drug list sits beside a header block.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.contracts.provenance import BoundingBox
from app.core.logging import get_logger
from app.modules.documents.preprocess import PreparedImage, rotate_point

log = get_logger(__name__)

#: A band shorter than this fraction of the page is an underline, a staple hole or a speck.
MIN_LINE_HEIGHT_FRACTION = 0.006
#: …and one taller than this is two lines that touched, or a table, not a line of writing.
MAX_LINE_HEIGHT_FRACTION = 0.14
#: A band must carry at least this fraction of the page width in ink to be writing.
MIN_INK_WIDTH_FRACTION = 0.02
#: Crops are padded so ascenders and descenders are not clipped. TrOCR was trained on crops
#: with margin; a tight crop measurably costs characters at the top and bottom of the line.
VERTICAL_PAD_FRACTION = 0.30
HORIZONTAL_PAD_PIXELS = 8
#: A gutter this wide with ink on both sides is a column break, not a word space.
GUTTER_WIDTH_FRACTION = 0.045
#: Below this the model is being fed a sliver. Anything narrower is dropped rather than read.
MIN_CROP_PIXELS = 16


@dataclass(frozen=True, slots=True)
class LineRegion:
    """One text line, in reading order, with the geometry to crop it and to cite it."""

    index: int
    #: Pixel box on the *prepared* image — what gets cropped.
    left: int
    top: int
    width: int
    height: int
    #: Normalised box on the *original* upload — what a bounding box overlay draws.
    bbox: BoundingBox
    #: Which column it came from. 0 for a single-column page.
    column: int
    #: Fraction of the band that is ink. Not a confidence; a plausibility signal used to
    #: drop rules, borders and shadows before they reach the model.
    ink_density: float

    def crop(self, prepared: PreparedImage) -> Image.Image:
        return prepared.image.crop(
            (self.left, self.top, self.left + self.width, self.top + self.height)
        )


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous True runs as (start, end_exclusive)."""
    if not mask.any():
        return []
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[0::2].tolist(), edges[1::2].tolist(), strict=True))


def _smooth(profile: np.ndarray, window: int) -> np.ndarray:
    if window < 2:
        return profile
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(profile, kernel, mode="same")


def find_columns(ink: np.ndarray) -> list[tuple[int, int]]:
    """Split the page at a wide blank gutter, or return the one column it actually is.

    A prescription pad routinely puts the clinic header and the patient block side by side
    above the drug list. Segmenting that as single-column produces bands that span both, and
    the model then reads "Age: 64 / F  TAB METFORMIN 500" as one line — two unrelated pieces
    of the page welded into a sentence that appears nowhere on the paper. Splitting first is
    what stops that.

    Conservative on purpose: it takes a gutter of real width *and* meaningful ink on both
    sides. A page with one column and a wide left margin must not be split, because splitting
    it would cut every line in half.
    """
    height, width = ink.shape
    column_profile = ink.sum(axis=0).astype(np.float32)
    blank = column_profile <= max(height * 0.002, 1.0)

    min_gutter = int(width * GUTTER_WIDTH_FRACTION)
    interior = [
        (start, end)
        for start, end in _runs(blank)
        if end - start >= min_gutter and start > width * 0.15 and end < width * 0.85
    ]
    if not interior:
        return [(0, width)]

    # The widest interior gutter is the column break; multiple gutters on a prescription are
    # far more often decorative whitespace than a three-column layout.
    start, end = max(interior, key=lambda run: run[1] - run[0])
    left_ink, right_ink = float(ink[:, :start].sum()), float(ink[:, end:].sum())
    total = left_ink + right_ink
    if total <= 0 or min(left_ink, right_ink) / total < 0.15:
        return [(0, width)]
    return [(0, start), (end, width)]


def _otsu(profile: np.ndarray) -> float:
    """The cut between "blank row" and "row with writing on it", found on the profile itself.

    A fraction-of-the-median threshold does not survive a real photograph. On the degraded
    fixture every blank row still carries a few percent of the page width in residual grain,
    and a fixed fraction sits *below* that floor — so every row passes, every band merges,
    and the page segments into a single line covering the whole sheet. The model then reads
    one line and silently loses the prescription.

    The row profile is genuinely bimodal — blank rows cluster at the noise floor, inked rows
    cluster far above it — so the floor is a property of this page that can be *measured*
    rather than a constant that has to be guessed. Otsu's method finds the cut that minimises
    the variance within the two groups, which identifies the blank-row population.

    Otsu's cut itself is not the threshold, and using it as one is a mistake worth recording:
    it lands mid-way between the two populations, so on a prescription — where lines vary
    from a full-width drug line to a two-character "Rx" — it drops every short line on the
    page. What is wanted is not the midpoint but the *top of the floor*, so this returns the
    cut and `_bands()` turns the rows beneath it into a mean and a spread.
    """
    if not profile.any():
        return 0.0
    top = float(profile.max())
    if top <= 0:
        return 0.0
    counts, edges = np.histogram(profile, bins=256, range=(0.0, top))
    weights = counts.astype(np.float64)
    total = weights.sum()
    if total <= 0:
        return 0.0
    centres = (edges[:-1] + edges[1:]) / 2.0

    weight_low = np.cumsum(weights)
    weight_high = total - weight_low
    sum_low = np.cumsum(weights * centres)
    sum_total = sum_low[-1]
    valid = (weight_low > 0) & (weight_high > 0)
    if not valid.any():
        return 0.0
    mean_low = np.divide(sum_low, weight_low, out=np.zeros_like(sum_low), where=weight_low > 0)
    mean_high = np.divide(
        sum_total - sum_low, weight_high, out=np.zeros_like(sum_low), where=weight_high > 0
    )
    between = weight_low * weight_high * (mean_low - mean_high) ** 2
    between[~valid] = -1.0
    return float(centres[int(np.argmax(between))])


def _floor_threshold(profile: np.ndarray, sigmas: float = 3.0) -> float:
    """Where the blank-paper population ends: the floor's mean, plus a few of its spreads.

    An outlier test, not a midpoint. A row counts as writing when it carries significantly
    more ink than a *blank* row of this page does — which keeps the two-character "Rx" line
    and the short "Advice:" line that a midpoint threshold throws away, while still rejecting
    a grain floor sitting at 3% of the page width.

    Median and MAD rather than mean and standard deviation, because Otsu's cut sits well
    above the floor and the rows beneath it therefore include the *short* text lines as well
    as the blank ones. A mean is dragged upward by that contamination — enough, measured on
    the clean prescription fixture, to threshold away the two-character "Rx" line and with it
    the marker that the next four lines are drugs. A median ignores it.

    Three spreads because the cost of the two errors is not symmetric: an extra band is a crop
    the model reads as empty and the reconstruction drops, whereas a missing band is a
    prescription line that silently never existed.
    """
    cut = _otsu(profile)
    floor = profile[profile <= cut] if cut > 0 else profile[profile <= 0]
    if floor.size == 0:
        return cut
    median = float(np.median(floor))
    # 1.4826 · MAD is the consistent estimator of σ for a normal distribution — it puts this
    # threshold on the same scale as the "three sigmas" the docstring claims.
    spread = 1.4826 * float(np.median(np.abs(floor - median)))
    return median + sigmas * spread


def _bands(ink: np.ndarray) -> list[tuple[int, int]]:
    """Row bands that contain writing, split where two lines have merged."""
    height, width = ink.shape
    row_profile = ink.sum(axis=1).astype(np.float32)
    if not row_profile.any():
        return []

    threshold = max(_floor_threshold(row_profile), width * 0.004, 1.0)
    smoothed = _smooth(row_profile, max(int(height * 0.002), 1))

    min_height = max(int(height * MIN_LINE_HEIGHT_FRACTION), 4)
    max_height = max(int(height * MAX_LINE_HEIGHT_FRACTION), min_height + 1)

    bands = [
        (start, end)
        for start, end in _runs(smoothed >= threshold)
        if end - start >= min_height
    ]
    if not bands:
        return []

    typical = float(np.median([end - start for start, end in bands]))
    out: list[tuple[int, int]] = []
    for start, end in bands:
        if end - start <= max(max_height, typical * 2.0):
            out.append((start, end))
            continue
        out.extend(_split_tall_band(row_profile, start, end, typical))
    return out


def _split_tall_band(
    row_profile: np.ndarray, start: int, end: int, typical: float
) -> list[tuple[int, int]]:
    """Cut a merged band at its internal minima.

    Handwriting joins lines together: a descender from one line touches the ascender of the
    next and the projection never returns to zero between them. The trough is still there,
    it is just not zero, so the split point is the *local minimum* rather than a blank row.
    """
    if typical < 2:
        return [(start, end)]
    span = row_profile[start:end]
    expected = max(int(round((end - start) / typical)), 2)
    cuts: list[int] = []
    for piece in range(1, expected):
        centre = int(len(span) * piece / expected)
        window = max(int(typical * 0.3), 2)
        low = max(centre - window, 1)
        high = min(centre + window, len(span) - 1)
        if low >= high:
            continue
        cuts.append(start + low + int(np.argmin(span[low:high])))

    edges = [start, *sorted(set(cuts)), end]
    return [(a, b) for a, b in zip(edges[:-1], edges[1:], strict=True) if b - a >= 4]


def find_lines(prepared: PreparedImage) -> list[LineRegion]:
    """Every text line on the page, in reading order: down each column, columns left to right.

    Returns an empty list when the page has no measurable text. That is a real answer and
    the caller must treat it as one — `TrOCRBackend` falls back to Tesseract on it rather
    than feeding the model an arbitrary rectangle.
    """
    ink = prepared.ink
    height, width = ink.shape
    regions: list[LineRegion] = []
    min_ink_width = max(int(width * MIN_INK_WIDTH_FRACTION), 6)

    for column_index, (col_start, col_end) in enumerate(find_columns(ink)):
        column_ink = ink[:, col_start:col_end]
        for band_top, band_bottom in _bands(column_ink):
            band = column_ink[band_top:band_bottom]
            columns_with_ink = np.flatnonzero(band.any(axis=0))
            if columns_with_ink.size == 0:
                continue
            ink_left = int(columns_with_ink[0])
            ink_right = int(columns_with_ink[-1]) + 1
            if ink_right - ink_left < min_ink_width:
                continue

            pad_y = max(int((band_bottom - band_top) * VERTICAL_PAD_FRACTION), 2)
            top = max(band_top - pad_y, 0)
            bottom = min(band_bottom + pad_y, height)
            left = max(col_start + ink_left - HORIZONTAL_PAD_PIXELS, 0)
            right = min(col_start + ink_right + HORIZONTAL_PAD_PIXELS, width)
            if right - left < MIN_CROP_PIXELS or bottom - top < MIN_CROP_PIXELS:
                continue

            regions.append(
                _region(
                    index=len(regions),
                    left=left,
                    top=top,
                    width=right - left,
                    height=bottom - top,
                    column=column_index,
                    density=float(band[:, ink_left:ink_right].mean()),
                    prepared=prepared,
                )
            )

    log.info(
        "ocr.lines_segmented",
        lines=len(regions),
        columns=len({r.column for r in regions}),
        skew=prepared.skew_degrees,
    )
    return regions


def _region(
    *,
    index: int,
    left: int,
    top: int,
    width: int,
    height: int,
    column: int,
    density: float,
    prepared: PreparedImage,
) -> LineRegion:
    # Both corners are mapped back through the deskew rotation, so the box cites a region of
    # the file the patient actually uploaded rather than of an intermediate we threw away.
    x0, y0 = rotate_point(left, top, prepared)
    x1, y1 = rotate_point(left + width, top + height, prepared)
    return LineRegion(
        index=index,
        left=left,
        top=top,
        width=width,
        height=height,
        column=column,
        ink_density=round(density, 4),
        bbox=BoundingBox(
            x=round(min(x0, x1), 4),
            y=round(min(y0, y1), 4),
            width=round(max(abs(x1 - x0), 1e-4), 4),
            height=round(max(abs(y1 - y0), 1e-4), 4),
        ),
    )

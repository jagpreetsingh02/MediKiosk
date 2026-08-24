"""Rasterise one page of a stored document, so evidence can be *seen*.

§12 of the build brief is blunt about this: "A blank bounding-box viewer is not sufficient."
The bounding boxes are normalised page coordinates, which can be drawn precisely over an
image and not at all over a browser's own PDF viewer — the viewer decides its own scale and
offset, and a box drawn in the wrong place is worse than no box, because it tells a physician
the system read a line it did not read.

Every fixture and most uploads are PDFs, and a browser asked to show one inline may render it,
may offer a download, or may show nothing (headless Chromium shows nothing). None of those
can carry an overlay. So the drawer asks for a PNG of the page instead, and gets a real image
with a real box on it.

`pypdfium2` is already a dependency — the tesseract backend rasterises with it before OCR — so
this adds no new one, and it renders at the same DPI the OCR saw.
"""

from __future__ import annotations

import io

from app.core.errors import UpstreamUnavailable, ValidationError
from app.core.logging import get_logger

log = get_logger(__name__)

#: The DPI the tesseract backend rasterises at. Matching it keeps the image the physician
#: looks at the same one the coordinates were measured against.
RENDER_DPI = 200


def render_page_png(data: bytes, *, media_type: str, page: int = 1) -> bytes:
    """One page as a PNG. An image passes through; a PDF page is rendered.

    Raises rather than returning a placeholder: a drawer that silently shows the wrong page
    would be a provenance failure, not a cosmetic one.
    """
    if media_type.startswith("image/"):
        return data

    if "pdf" not in media_type:
        raise ValidationError(
            f"Cannot render {media_type!r} as a page image. Only images and PDFs are stored "
            "with page geometry."
        )

    try:
        import pypdfium2  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - the dependency is pinned
        raise UpstreamUnavailable(
            "Rendering a PDF page needs `pypdfium2` (in requirements.txt)."
        ) from exc

    document = pypdfium2.PdfDocument(io.BytesIO(data))
    try:
        if page < 1 or page > len(document):
            raise ValidationError(
                f"Page {page} does not exist in this document (it has {len(document)})."
            )
        image = document[page - 1].render(scale=RENDER_DPI / 72).to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        document.close()

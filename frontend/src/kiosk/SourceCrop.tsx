/**
 * The patch of the original page a reading came from, shown beside the reading.
 *
 * WHY THIS IS THE WHOLE POINT OF THE VERIFICATION LANE. Asking "is METFORMIN 500MG correct?"
 * asks the patient to trust their memory. Showing them the strip of their own prescription the
 * words were lifted from asks them to compare two things in front of them, which is a question
 * a person can actually answer — including someone who cannot read the text, because the
 * shapes either match or they do not.
 *
 * It is also the honest presentation of an OCR error. A real upload in testing produced
 * "AMLODIPINE SMG" from a line that reads "TAB. AMLODIPINE 5MG OD x 30 days". Read alone, a
 * patient might well confirm it. Read against the crop, the mismatch is obvious and Correct is
 * the obvious action.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * THE GEOMETRY, because two different mistakes were made here and both were invisible.
 *
 * 1. THE IMAGE MUST BE THE ONE OCR READ. The bbox is normalised against the *prepared* page —
 *    EXIF-rotated, scaled, deskewed with expand=True, thresholded — and deskew alone changes
 *    the canvas size. `render.py` now serves that same prepared page for exactly this reason.
 *
 * 2. PERCENTAGE MARGINS RESOLVE AGAINST WIDTH. The first version positioned an oversized
 *    `<img>` with `margin-top: -y%`, which silently resolves against the container's WIDTH,
 *    not its height. Every crop was therefore offset vertically by the wrong amount and landed
 *    on blank paper — evidence that proved nothing, beside a reading the patient was being
 *    asked to confirm. It looked like a rendering glitch; it was a provenance failure.
 *
 * The fix is `background-position` / `background-size`, whose percentage model handles each
 * axis independently and correctly. The container's aspect ratio is then set from the crop's
 * REAL pixel aspect, read off the loaded image — so a wide prescription line renders as a wide
 * strip rather than being squashed into a thumbnail's shape.
 *
 * THE IMAGE IS FETCHED, NOT LINKED. Every document route requires a bearer token and an
 * `<img src>` cannot carry one; pointing at the URL directly returns 403 and renders as a
 * broken image, which reads to a patient as "your document is gone" rather than "you are not
 * authorised". `api.fetchImage` sends the token and hands back an object URL, and preserves
 * the audit entry the route writes. One page is fetched per document, not one per row.
 */
import { useEffect, useState } from 'react';
import { api } from '../shared/api';

/** page URL -> object URL, so N rows on one page cost one fetch. Module scope because the
 *  rows are siblings and each would otherwise start its own request before any resolved. */
const pageCache = new Map<string, Promise<string>>();

function loadPage(path: string): Promise<string> {
  let pending = pageCache.get(path);
  if (!pending) {
    pending = api.fetchImage(path);
    pageCache.set(path, pending);
  }
  return pending;
}

interface Props {
  /** Path to the full-page PNG. FETCHED, not assigned to `src` — see above. */
  pageUrl: string;
  /** Normalised against the PREPARED page, origin top-left, each in [0, 1]. */
  bbox: { x: number; y: number; width: number; height: number };
  /** Described to a screen reader, which cannot see the crop. */
  label: string;
  /** Never taller than this, however tall the box is. */
  maxHeight?: number;
}

/** Padding around the box, as a fraction of its own size. Vertical is generous because a bbox
 *  fitted to the glyphs clips ascenders and descenders; horizontal is small because the line
 *  is already the full width of what was read. */
const PAD_X = 0.04;
const PAD_Y = 0.55;

export function SourceCrop({ pageUrl, bbox, label, maxHeight = 96 }: Props): JSX.Element {
  const [failed, setFailed] = useState(false);
  const [page, setPage] = useState<{ url: string; width: number; height: number } | null>(null);

  useEffect(() => {
    let live = true;
    loadPage(pageUrl)
      .then((url) => {
        // The natural size is needed to know the crop's real aspect ratio — a text line is a
        // wide strip, and a container shaped like a thumbnail would distort it.
        const probe = new Image();
        probe.onload = () => {
          if (live) setPage({ url, width: probe.naturalWidth, height: probe.naturalHeight });
        };
        probe.onerror = () => {
          if (live) setFailed(true);
        };
        probe.src = url;
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
    // Deliberately not revoking: the object URL is shared by every row on this page through
    // `pageCache`, so revoking on one row's unmount would break its siblings. The blobs die
    // with the document, and a kiosk session is minutes.
  }, [pageUrl]);

  // A degenerate bbox — some engines emit zero-area boxes — would divide by zero below and
  // blow the scale up. Falling back to the whole page is still useful: the patient sees their
  // document, just not zoomed.
  const raw = {
    x: Number.isFinite(bbox?.x) ? bbox.x : 0,
    y: Number.isFinite(bbox?.y) ? bbox.y : 0,
    width: bbox?.width > 0.001 ? bbox.width : 1,
    height: bbox?.height > 0.001 ? bbox.height : 1,
  };

  const padX = raw.width * PAD_X;
  const padY = raw.height * PAD_Y;
  const x = Math.max(0, raw.x - padX);
  const y = Math.max(0, raw.y - padY);
  const width = Math.min(1 - x, raw.width + padX * 2);
  const height = Math.min(1 - y, raw.height + padY * 2);

  if (failed) {
    return (
      <div className="kx-crop kx-crop--missing" role="note">
        <span>Original not available</span>
      </div>
    );
  }

  if (!page) {
    return <div className="kx-crop kx-crop--loading" aria-hidden="true" />;
  }

  // `background-size` as a percentage of the container: showing a `width` fraction of the
  // image across the full container means scaling the image to 1/width of the container.
  // `background-position` as a percentage uses the "extra space" model, hence the /(1-f).
  const style = {
    backgroundImage: `url(${page.url})`,
    backgroundSize: `${(1 / width) * 100}% ${(1 / height) * 100}%`,
    backgroundPositionX: width >= 1 ? '0%' : `${(x / (1 - width)) * 100}%`,
    backgroundPositionY: height >= 1 ? '0%' : `${(y / (1 - height)) * 100}%`,
    // The crop's true shape, so a line of text looks like a line of text.
    aspectRatio: `${Math.max(1, width * page.width)} / ${Math.max(1, height * page.height)}`,
    maxHeight,
  };

  return (
    <div
      className="kx-crop"
      data-loaded="true"
      style={style}
      role="img"
      aria-label={`The part of your document that says: ${label}`}
    />
  );
}

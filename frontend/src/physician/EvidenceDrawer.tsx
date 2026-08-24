/**
 * "Show me where that came from" — the original page, with the OCR region drawn on it.
 *
 * §12 is explicit that a blank bounding-box viewer does not count as evidence, and it was
 * right to be: the box was being drawn over nothing, because the uploaded bytes were never
 * persisted. They are now, and this renders them underneath the box.
 *
 * The page always arrives as a rendered PNG, never as the raw PDF. A browser asked to show a
 * PDF inline may render it, may offer a download, or may show nothing, and none of those can
 * carry an overlay positioned in page coordinates — a box drawn at the wrong scale is worse
 * than no box, because it tells a physician the system read a line it did not read.
 */
import { useEffect, useState } from 'react';
import { api, type ExtractedItem } from '../shared/api';

interface Props {
  /** A route returning a PNG of the page. See `render_page_png` for why it is never a PDF. */
  fileUrl: string;
  item: ExtractedItem | null;
  documentLabel: string;
  onClose: () => void;
}

export function EvidenceDrawer({
  fileUrl,
  item,
  documentLabel,
  onClose,
}: Props): JSX.Element {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  // The page is fetched rather than linked: an <img src> cannot carry the bearer token the
  // document routes require, and the audit entry is written by the route, not by the tag.
  useEffect(() => {
    let revoked: string | null = null;
    let live = true;
    setObjectUrl(null);
    setFailed(null);
    api
      .fetchImage(fileUrl)
      .then((url) => {
        revoked = url;
        if (live) setObjectUrl(url);
        else URL.revokeObjectURL(url);
      })
      .catch((exc) => {
        if (live) setFailed(exc instanceof Error ? exc.message : 'Could not load the page.');
      });
    return () => {
      live = false;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [fileUrl]);

  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="evi-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="evi" onClick={(event) => event.stopPropagation()}>
        <header className="evi-head">
          <div>
            <div className="evi-kicker">Source</div>
            <div className="evi-title">{documentLabel}</div>
            {item && <div className="evi-sub">Page {item.page}</div>}
          </div>
          <button type="button" className="btn sm" onClick={onClose}>
            Close <kbd>esc</kbd>
          </button>
        </header>

        <div className="evi-page">
          {failed && <div className="source-empty">{failed}</div>}
          {!failed && !objectUrl && <div className="source-empty">Loading the page…</div>}

          {!failed && objectUrl && (
            <div className="evi-frame">
              <img src={objectUrl} alt={documentLabel} />
              {item?.bbox && (
                // The bbox is normalised to the page, so percentages line up with the image
                // at whatever size it renders — no scale factor to get wrong.
                <span
                  className="evi-box"
                  style={{
                    left: `${item.bbox.x * 100}%`,
                    top: `${item.bbox.y * 100}%`,
                    width: `${item.bbox.width * 100}%`,
                    height: `${item.bbox.height * 100}%`,
                  }}
                />
              )}
            </div>
          )}

        </div>

        {item && (
          <footer className="evi-foot">
            <div className="evi-label">Text OCR read here</div>
            <blockquote className="evi-quote">{item.sourceText}</blockquote>
            {item.patientReading && (
              <>
                <div className="evi-label">Read by a person as</div>
                <blockquote className="evi-quote human">{item.patientReading}</blockquote>
              </>
            )}
            <div className="evi-meta">
              <span>
                OCR confidence {Math.round((item.confidence ?? 0) * 100)}%
                {item.handwritten ? ' · handwritten' : ''}
              </span>
              {item.patientDisputed && (
                <span className="evi-dispute">The patient does not agree with this line</span>
              )}
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}

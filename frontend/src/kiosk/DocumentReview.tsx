/**
 * "Is this what your paper says?" — the screen that stops OCR becoming truth quietly.
 *
 * Two lanes, and the patient is not told which is which in those words:
 *
 *   pending   nothing was recorded. The patient tapping *Yes* is what admits it.
 *   recorded  a clean scan. It is already in the record as what the document SAYS, and the
 *             patient cannot delete that by disagreeing — they can dispute it, and a
 *             physician resolves it. A kiosk that let a patient erase a line off their own
 *             prescription would be a kiosk that loses the medicine they stopped taking.
 *
 * Confidence is shown as a word, never a percentage. "81%" reads to a patient as an 81%
 * chance the medicine is right, which is not what an OCR confidence means.
 */
import { useState } from 'react';
import { ApiError, api, type ExtractedItem } from '../shared/api';
import { Icon } from '../shared/Icon';

interface Props {
  sessionRef: string;
  documentId: string;
  filename: string;
  kind: string;
  items: ExtractedItem[];
  onDone: () => void;
}

const KIND_LABEL: Record<string, string> = {
  prescription: 'Prescription',
  lab_report: 'Laboratory report',
  discharge_summary: 'Discharge summary',
  other: 'Medical record',
};

export function DocumentReview({
  sessionRef,
  documentId,
  filename,
  kind,
  items,
  onDone,
}: Props): JSX.Element {
  const [reviewed, setReviewed] = useState<Record<string, string>>({});
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const readable = items.filter((item) => item.kind === 'medication' || item.kind === 'investigation');
  const shown = readable.length ? readable : items;
  const outstanding = shown.filter((item) => item.pending && !reviewed[item.itemId]);

  async function send(item: ExtractedItem, action: string, correctedText?: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await api.reviewDocumentItem(sessionRef, documentId, {
        itemId: item.itemId,
        action,
        correctedText,
      });
      setReviewed((current) => ({ ...current, [item.itemId]: action }));
      setCorrecting(null);
      setDraft('');
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not save that. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">Is this what your paper says?</h1>
      <p className="kiosk-lead">
        We read your {KIND_LABEL[kind]?.toLowerCase() ?? 'record'}. Please check it before your
        doctor sees it. Nothing here is a diagnosis.
      </p>

      <div className="doc-chip">
        <Icon name="camera" />
        <span>{filename}</span>
        <span className="doc-chip-kind">{KIND_LABEL[kind] ?? 'Medical record'}</span>
      </div>

      {error && <div className="kiosk-error">{error}</div>}

      <div className="extract-list">
        {shown.map((item) => {
          const outcome = reviewed[item.itemId];
          const needsCheck = item.confidenceBand === 'verify';
          return (
            <div
              key={item.itemId}
              className={`extract-row${needsCheck ? ' unsure' : ''}${outcome ? ` done-${outcome}` : ''}`}
            >
              <div className="extract-mark">
                <Icon name={needsCheck ? 'other' : 'check'} />
              </div>

              <div className="extract-body">
                <div className="extract-name">{item.text}</div>
                <div className="extract-detail">{describe(item)}</div>
                <div className={`extract-band band-${item.confidenceBand}`}>
                  {needsCheck
                    ? 'Not clear — please check this one'
                    : item.confidenceBand === 'high'
                      ? 'Read clearly'
                      : 'Read, please confirm'}
                </div>

                {outcome && (
                  <div className="extract-outcome">
                    {outcome === 'confirm' && 'You confirmed this.'}
                    {outcome === 'dispute' &&
                      (item.pending
                        ? 'Removed — this will not be sent to your doctor.'
                        : 'Your doctor will be told you do not agree with this line.')}
                    {outcome === 'correct' && 'Thank you — your correction was saved.'}
                  </div>
                )}
              </div>

              {!outcome && correcting !== item.itemId && (
                <div className="extract-actions">
                  <button
                    type="button"
                    className="btn-small btn-yes"
                    disabled={busy}
                    onClick={() => void send(item, 'confirm')}
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    className="btn-small"
                    disabled={busy}
                    onClick={() => {
                      setCorrecting(item.itemId);
                      setDraft(item.text);
                    }}
                  >
                    Fix
                  </button>
                  <button
                    type="button"
                    className="btn-small btn-no"
                    disabled={busy}
                    onClick={() => void send(item, 'dispute')}
                  >
                    No
                  </button>
                </div>
              )}

              {correcting === item.itemId && (
                <div className="extract-correct">
                  <label htmlFor={`fix-${item.itemId}`}>What does it say?</label>
                  <input
                    id={`fix-${item.itemId}`}
                    value={draft}
                    autoFocus
                    onChange={(event) => setDraft(event.target.value)}
                  />
                  <div className="kiosk-actions" style={{ marginTop: 12 }}>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={busy || !draft.trim()}
                      onClick={() => void send(item, 'correct', draft.trim())}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="btn-quiet"
                      onClick={() => setCorrecting(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {shown.length === 0 && (
        <p className="kiosk-lead">
          We could not read anything from this paper. Your doctor will still see the original.
        </p>
      )}

      <div className="kiosk-actions">
        <button type="button" className="btn-primary" onClick={onDone} disabled={busy}>
          {outstanding.length
            ? `Continue — ${outstanding.length} still to check`
            : 'Looks right — continue'}
        </button>
      </div>
    </div>
  );
}

/** Dose, frequency and duration in the patient's words, and only what was actually found. */
function describe(item: ExtractedItem): string {
  const detail = item.detail ?? {};
  const parts: string[] = [];
  if (detail.dose) parts.push(String(detail.dose));
  if (detail.frequencyText || detail.frequencyRaw) {
    parts.push(String(detail.frequencyText ?? detail.frequencyRaw));
  }
  if (detail.durationDays) parts.push(`for ${detail.durationDays} days`);
  if (detail.value !== undefined && detail.value !== null) {
    parts.push(`${detail.value}${detail.unit ? ` ${detail.unit}` : ''}`);
  }
  return parts.join(' · ');
}

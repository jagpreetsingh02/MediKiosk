/**
 * "This is what I read off your paper. Is it right?"
 *
 * OCR must never silently become truth, and the patient holding the prescription is the
 * cheapest, best-informed check available — long before a physician sees it.
 *
 * The two lanes are treated differently on purpose:
 *
 *  - A **low-confidence** item was never recorded. Confirming it is what admits it, so the
 *    buttons read as a decision the patient is making.
 *  - A **high-confidence** item is already recorded as document-tier: it is what the paper
 *    *says*. A patient disagreeing does not delete it, because the paper still says what it
 *    says. It is flagged for the physician instead. That is not a technicality — "the
 *    prescription says metformin but the patient says they never took it" is a real and
 *    clinically important state, and collapsing it to either side loses information.
 */
import { useState } from 'react';
import { ApiError, api, type ExtractedItem, type InterpretedMedication } from '../shared/api';
import { Icon } from '../shared/Icon';
import { PrescriptionReading } from './PrescriptionReading';

interface Props {
  sessionRef: string;
  documentId: string;
  filename: string;
  /** prescription | lab_report | discharge_summary | other, from what was found on it. */
  kind: string;
  items: ExtractedItem[];
  /** The page as it literally appears to read. Rendered beside the interpretation, never
   *  instead of it. */
  rawOcrText?: string;
  medications?: InterpretedMedication[];
  backend?: string;
  onDone: () => void;
}

/** Medicines and results are what a patient can meaningfully check. Dates and headings are
 *  extraction plumbing, and asking about them buys nothing but fatigue. */
const CHECKABLE = new Set(['medication', 'investigation', 'diagnosis']);

/** What to call the document to the patient. "discharge_summary" is not a phrase. */
const KIND_LABEL: Record<string, string> = {
  prescription: 'prescription',
  lab_report: 'test report',
  discharge_summary: 'hospital paper',
  other: 'paper',
};

export function DocumentReview({
  sessionRef,
  documentId,
  filename,
  kind,
  items,
  rawOcrText = '',
  medications = [],
  backend,
  onDone,
}: Props): JSX.Element {
  const [decided, setDecided] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkable = items.filter((item) => CHECKABLE.has(item.kind));

  async function decide(item: ExtractedItem, action: 'confirm' | 'dispute'): Promise<void> {
    setBusy(item.itemId);
    setError(null);
    try {
      await api.reviewDocumentItem(sessionRef, documentId, { itemId: item.itemId, action });
      setDecided((current) => ({ ...current, [item.itemId]: action }));
    } catch (exc) {
      setError(
        exc instanceof ApiError ? exc.message : 'Could not save that. Please try again.',
      );
    } finally {
      setBusy(null);
    }
  }

  if (!checkable.length) {
    return (
      <div className="kiosk-panel">
        <h1 className="kiosk-title">We could not read that paper</h1>
        <p className="kiosk-lead">
          Nothing could be read from {filename}. The doctor will still see the picture you
          took, so nothing is lost. You can try another photo if you like.
        </p>
        <div className="kiosk-actions">
          <button type="button" className="btn-primary" onClick={onDone}>
            Continue
          </button>
        </div>
      </div>
    );
  }

  const pending = checkable.filter((item) => item.pending && !decided[item.itemId]);

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">Is this right?</h1>
      <p className="kiosk-lead">
        This is what we read from your {KIND_LABEL[kind] ?? 'paper'}. Please check the
        medicines and results.
      </p>

      {error && <div className="kiosk-error">{error}</div>}

      {/* Above the confirmation list, not instead of it. The list is where a patient makes
          decisions; this is where they see what those decisions are about — the words on
          their paper, and the reading of them, side by side. */}
      <PrescriptionReading
        rawOcrText={rawOcrText}
        medications={medications}
        backend={backend}
      />

      <div className="extract-list">
        {checkable.map((item) => {
          const outcome = decided[item.itemId];
          const needsCheck = item.confidenceBand === 'verify';
          return (
            <div
              key={item.itemId}
              className={`extract-item${needsCheck ? ' needs-check' : ''}${
                outcome ? ` decided ${outcome}` : ''
              }`}
            >
              <div className="extract-mark">
                <Icon name={needsCheck ? 'other' : 'check'} />
              </div>

              <div className="extract-body">
                <div className="extract-name">{item.text}</div>
                <div className="extract-detail">{describe(item)}</div>
                <div className="extract-band">
                  {needsCheck
                    ? 'Not clear — please check this one'
                    : 'Read clearly'}
                </div>
              </div>

              <div className="extract-actions">
                {outcome ? (
                  <span className={`extract-outcome ${outcome}`}>
                    {outcome === 'confirm' ? 'Confirmed' : 'Marked for the doctor'}
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn-small primary"
                      disabled={busy === item.itemId}
                      onClick={() => void decide(item, 'confirm')}
                    >
                      Yes
                    </button>
                    <button
                      type="button"
                      className="btn-small"
                      disabled={busy === item.itemId}
                      onClick={() => void decide(item, 'dispute')}
                    >
                      No
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {pending.length > 0 && (
        <p className="kiosk-help" style={{ color: 'var(--warn)', marginTop: 16 }}>
          {pending.length === 1
            ? 'One item still needs checking. Anything you do not check is left for the doctor.'
            : `${pending.length} items still need checking. Anything you do not check is left for the doctor.`}
        </p>
      )}

      <div className="kiosk-actions">
        <button type="button" className="btn-primary" onClick={onDone}>
          Done
        </button>
      </div>
    </div>
  );
}

/** Dose and frequency in the patient's words, not the extractor's field names. */
function describe(item: ExtractedItem): string {
  const detail = item.detail ?? {};
  const parts = [detail.dose, detail.frequencyRaw ?? detail.frequency, detail.duration]
    .filter((part): part is string => typeof part === 'string' && part.trim().length > 0);
  if (parts.length) return parts.join(' · ');
  if (item.kind === 'investigation' && detail.value != null) {
    return `${detail.value}${detail.unit ? ` ${detail.unit}` : ''}`;
  }
  return item.sourceText;
}

/**
 * The patient's confirmed visits, and the report for each one.
 *
 * Lifted out of `PatientPortal` unchanged in behaviour when that screen became a workspace
 * with five tabs rather than one list. The reasoning it carries is unchanged too:
 *
 * ⛔ ONLY WHAT A PHYSICIAN CONFIRMED APPEARS HERE, and that is not a filter this component
 * applies. An `Encounter` row is created solely by `promote()`, reachable only from the
 * commit route, so a visit still being written up does not exist as an encounter yet and
 * there is nothing here to hide. The note from the server says so in words, because "you have
 * one visit" and "you have one visit and another we are not showing you" look identical.
 *
 * The report opens INLINE rather than navigating, so a patient comparing two visits does not
 * lose their place in the list to do it. The PDF is the same deterministic generator the
 * clinician report uses, in its patient variant — not a screenshot, not a second assembly.
 */
import { useState } from 'react';
import { PatientBriefView } from '../brief/PatientBriefView';
import { api } from '../shared/api';
import { Icon } from '../shared/Icon';
import type { ConfirmedVisit } from './PatientChanges';

interface Props {
  patientRef: string;
  visits: ConfirmedVisit[] | null;
  /** The server's own sentence about what is and is not in this list. Rendered verbatim. */
  note: string | null;
  onError: (message: string) => void;
}

export function PatientVisits({ patientRef, visits, note, onError }: Props): JSX.Element {
  const [open, setOpen] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  async function download(encounterRef: string): Promise<void> {
    setDownloading(encounterRef);
    try {
      const { url, filename } = await api.briefPdf(patientRef, 'patient', encounterRef);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch {
      onError('That report could not be prepared. Please try again.');
    } finally {
      setDownloading(null);
    }
  }

  if (visits === null) return <div className="bx-loading" aria-label="Loading your visits" />;

  if (visits.length === 0) {
    return (
      <p className="bx-empty">
        You have no confirmed visits yet. A visit appears here once a doctor has finished
        reviewing it.
      </p>
    );
  }

  return (
    <>
      {note && <p className="kx-footnote">{note}</p>}

      <ol className="pp-visits">
        {visits.map((v) => (
          <li key={v.encounterRef} className="pp-visit">
            <div className="pp-visit__when">
              <strong>{v.occurredOn}</strong>
              <span className="kx-footnote">Confirmed by {v.confirmedBy}</span>
            </div>
            <div className="pp-visit__what">{v.headline ?? 'Clinical history'}</div>
            <div className="pp-visit__actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setOpen(open === v.encounterRef ? null : v.encounterRef)}
                aria-expanded={open === v.encounterRef}
              >
                {open === v.encounterRef ? 'Hide my report' : 'View my report'}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void download(v.encounterRef)}
                disabled={downloading !== null}
              >
                <Icon name="image" />
                {downloading === v.encounterRef ? 'Preparing…' : 'Download PDF'}
              </button>
            </div>

            {open === v.encounterRef && (
              <div className="pp-visit__report">
                {/* The same patient view the kiosk shows, for THIS visit. */}
                <PatientBriefView patientRef={patientRef} encounterRef={v.encounterRef} />
              </div>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}

/**
 * Download the brief as a PDF — both audiences.
 *
 * THE FILE IS FETCHED, NOT LINKED. Every report route requires a bearer token and an
 * `<a href>` cannot carry one; pointing at the URL directly returns 403 and the browser shows
 * a broken download with no explanation. So it is fetched like any other API call and handed
 * to the browser as a blob, and the object URL is revoked afterwards rather than leaked.
 *
 * The rendering happens SERVER-SIDE from the same deterministic payload the screen uses — no
 * html2canvas, no screenshot of the glass theme. See `app/modules/report/pdf.py`.
 */
import { useState } from 'react';
import { api } from '../shared/api';
import { Icon } from '../shared/Icon';

interface Props {
  patientRef: string;
}

export function ExportButtons({ patientRef }: Props): JSX.Element {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(audience: 'clinician' | 'patient'): Promise<void> {
    setBusy(audience);
    setError(null);
    try {
      const { url, filename } = await api.briefPdf(patientRef, audience);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoked on the next tick: revoking synchronously can cancel the download in some
      // browsers before it has actually started reading the blob.
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch {
      setError('The report could not be prepared. Please try again.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="bx-export">
      <button
        type="button"
        className="btn-secondary"
        onClick={() => download('clinician')}
        disabled={busy !== null}
      >
        <Icon name="image" />
        {busy === 'clinician' ? 'Preparing…' : "Download doctor's report (PDF)"}
      </button>
      <button
        type="button"
        className="btn-secondary"
        onClick={() => download('patient')}
        disabled={busy !== null}
      >
        <Icon name="image" />
        {busy === 'patient' ? 'Preparing…' : 'Download my copy (PDF)'}
      </button>
      {error && <p className="bx-empty bx-empty--error">{error}</p>}
    </div>
  );
}

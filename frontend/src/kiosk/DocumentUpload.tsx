/**
 * Scanning prior prescriptions and reports.
 *
 * Anything the OCR was unsure about is shown here as "a person will check this", not hidden.
 * The patient should know a scan was imperfect, and the physician gets it in the verification
 * lane either way.
 */
import { useRef, useState } from 'react';
import { ApiError, api } from '../shared/api';
import { Icon } from '../shared/Icon';

interface Uploaded {
  documentId: string;
  filename: string;
  backend: string;
  meanConfidence: number;
  factsRecorded: number;
  lowConfidenceCount: number;
}

interface Props {
  sessionRef: string;
  onDone: () => void;
}

export function DocumentUpload({ sessionRef, onDone }: Props): JSX.Element {
  const [uploads, setUploads] = useState<Uploaded[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function upload(files: FileList | null): Promise<void> {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    for (const file of Array.from(files)) {
      try {
        const result = await api.upload(sessionRef, file);
        setUploads((current) => [...current, result]);
      } catch (exc) {
        setError(exc instanceof ApiError ? exc.message : `Could not read ${file.name}.`);
      }
    }
    setBusy(false);
  }

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">Your old prescriptions and reports</h1>
      <p className="kiosk-lead">
        If you have brought any papers from before, show them to the camera or choose a file.
        The doctor will see them alongside your answers. You can skip this.
      </p>

      {error && <div className="kiosk-error">{error}</div>}

      <button
        type="button"
        className="upload-drop"
        style={{ width: '100%' }}
        onClick={() => input.current?.click()}
        disabled={busy}
      >
        <Icon name="camera" />
        <div style={{ marginTop: 12 }}>
          {busy ? 'Reading your document…' : 'Touch here to add a prescription or report'}
        </div>
      </button>
      <input
        ref={input}
        type="file"
        accept="application/pdf,image/png,image/jpeg,text/plain"
        multiple
        hidden
        onChange={(event) => void upload(event.target.files)}
      />

      {uploads.map((upload) => (
        <div
          key={upload.documentId}
          className={`upload-item${upload.lowConfidenceCount ? ' needs-check' : ''}`}
        >
          <div>
            <strong>{upload.filename}</strong>
            <div style={{ fontSize: 18, color: 'var(--ink-2)', marginTop: 4 }}>
              {upload.factsRecorded} item(s) read
              {upload.lowConfidenceCount > 0
                ? ` · ${upload.lowConfidenceCount} unclear, a person will check these`
                : ' · read clearly'}
            </div>
          </div>
          <Icon name={upload.lowConfidenceCount ? 'other' : 'check'} />
        </div>
      ))}

      <div className="kiosk-actions">
        <button type="button" className="btn-primary" onClick={onDone} disabled={busy}>
          {uploads.length ? 'Done — continue' : 'I have no papers'}
        </button>
      </div>
    </div>
  );
}

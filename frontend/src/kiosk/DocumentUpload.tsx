/**
 * Scanning prior prescriptions and reports.
 *
 * Anything the OCR was unsure about is shown here as "a person will check this", not hidden.
 * The patient should know a scan was imperfect, and the physician gets it in the verification
 * lane either way.
 */
import { useRef, useState } from 'react';
import { ApiError, api, type UploadResult } from '../shared/api';
import { DocumentReview } from './DocumentReview';
import { Icon } from '../shared/Icon';

interface Props {
  sessionRef: string;
  /** How many records this session already holds, so a return visit reads correctly. */
  alreadyUploaded: number;
  /** Whether the `documents` consent scope is granted. */
  consented: boolean;
  /** Ask for the documents scope in place, at the moment the patient wants to use it. */
  onGrantConsent: () => Promise<void>;
  onDone: (uploaded: number) => void;
}

export function DocumentUpload({
  sessionRef,
  alreadyUploaded,
  consented,
  onGrantConsent,
  onDone,
}: Props): JSX.Element {
  const [uploads, setUploads] = useState<UploadResult[]>([]);
  /** The document just scanned, held on screen until the patient has read it back. */
  const [reviewing, setReviewing] = useState<UploadResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [granting, setGranting] = useState(false);
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
        // Straight into the readback. An extraction the patient never saw is an extraction
        // that became true without anybody agreeing to it.
        setReviewing(result);
      } catch (exc) {
        setError(exc instanceof ApiError ? exc.message : `Could not read ${file.name}.`);
      }
    }
    setBusy(false);
  }

  if (reviewing) {
    return (
      <DocumentReview
        sessionRef={sessionRef}
        documentId={reviewing.documentId}
        filename={reviewing.filename}
        kind={reviewing.documentKind}
        items={reviewing.extracted}
        onDone={() => setReviewing(null)}
      />
    );
  }

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">Your old prescriptions and reports</h1>
      <p className="kiosk-lead">
        If you have brought any papers from before, show them to the camera or choose a file.
        The doctor will see them alongside your answers. You can skip this.
      </p>

      {error && <div className="kiosk-error">{error}</div>}

      {!consented && (
        <div
          style={{
            border: '3px solid var(--accent)',
            background: 'var(--accent-soft)',
            borderRadius: 'var(--radius-lg)',
            padding: 22,
            marginBottom: 20,
            fontSize: 21,
            lineHeight: 1.5,
          }}
        >
          To read your papers I need your permission to process them. They are deleted after
          your visit.
          <div className="kiosk-actions" style={{ marginTop: 18 }}>
            <button
              type="button"
              className="btn-primary"
              disabled={granting}
              onClick={async () => {
                setGranting(true);
                setError(null);
                try {
                  await onGrantConsent();
                } catch (exc) {
                  setError(
                    exc instanceof ApiError ? exc.message : 'Could not record your permission.',
                  );
                } finally {
                  setGranting(false);
                }
              }}
            >
              I agree — read my papers
            </button>
            <button type="button" className="btn-quiet" onClick={() => onDone(alreadyUploaded)}>
              No thank you
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        className="upload-drop"
        style={{ width: '100%' }}
        onClick={() => input.current?.click()}
        disabled={busy || !consented}
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
              {upload.extracted.length} item(s) read
              {upload.lowConfidenceCount > 0
                ? ` · ${upload.lowConfidenceCount} unclear`
                : ' · read clearly'}
            </div>
            <button
              type="button"
              className="btn-link"
              onClick={() => setReviewing(upload)}
            >
              Check what we read
            </button>
          </div>
          <Icon name={upload.lowConfidenceCount ? 'other' : 'check'} />
        </div>
      ))}

      <div className="kiosk-actions">
        <button
          type="button"
          className="btn-primary"
          onClick={() => onDone(alreadyUploaded + uploads.length)}
          disabled={busy}
        >
          {uploads.length || alreadyUploaded ? 'Done — continue' : 'I have no papers'}
        </button>
      </div>
    </div>
  );
}

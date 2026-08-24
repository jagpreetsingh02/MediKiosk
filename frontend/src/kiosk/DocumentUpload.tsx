/**
 * Scanning prior prescriptions and reports.
 *
 * Anything the OCR was unsure about is shown here as "a person will check this", not hidden.
 * The patient should know a scan was imperfect, and the physician gets it in the verification
 * lane either way.
 */
import { useRef, useState } from 'react';
import { ApiError, api, type UploadResult } from '../shared/api';
import { Icon } from '../shared/Icon';
import { CameraCapture } from './CameraCapture';
import { DocumentReview } from './DocumentReview';

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
  const [camera, setCamera] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Two pickers, because "a photo" and "a PDF" are different things to a patient and the
   *  file dialog should not offer both when they have already said which they have. */
  const imageInput = useRef<HTMLInputElement>(null);
  const pdfInput = useRef<HTMLInputElement>(null);

  async function send(file: File): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const result = await api.upload(sessionRef, file);
      setUploads((current) => [...current, result]);
      // Straight into the readback. An extraction the patient never saw is an extraction
      // that became true without anybody agreeing to it.
      setReviewing(result);
    } catch (exc) {
      // Whatever went wrong — a missing OCR engine, an unreadable file, a dead network —
      // the patient gets one sentence they can act on. The detail is in the server log,
      // where the person who can fix it will look.
      setError(
        exc instanceof ApiError && exc.status === 413
          ? 'That file is too large. Please take a photo instead.'
          : 'We could not read that paper. Please try another photo, or skip this step.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function upload(files: FileList | null): Promise<void> {
    if (!files?.length) return;
    for (const file of Array.from(files)) await send(file);
  }

  if (camera) {
    return (
      <CameraCapture
        onCancel={() => setCamera(false)}
        onCaptured={(file) => {
          setCamera(false);
          void send(file);
        }}
      />
    );
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

      {busy ? (
        <div className="upload-working" role="status">
          <Icon name="camera" />
          <div>
            <strong>Reading your paper…</strong>
            <div className="upload-working-step">Finding the words, then the medicines.</div>
          </div>
        </div>
      ) : (
        <div className="doc-actions">
          <button
            type="button"
            className="doc-action primary"
            disabled={!consented}
            onClick={() => setCamera(true)}
          >
            <Icon name="camera" />
            <span>Take Photo</span>
          </button>
          <button
            type="button"
            className="doc-action"
            disabled={!consented}
            onClick={() => imageInput.current?.click()}
          >
            <Icon name="other" />
            <span>Upload Image</span>
          </button>
          <button
            type="button"
            className="doc-action"
            disabled={!consented}
            onClick={() => pdfInput.current?.click()}
          >
            <Icon name="checkup" />
            <span>Upload PDF</span>
          </button>
          <button
            type="button"
            className="doc-action quiet"
            onClick={() => onDone(alreadyUploaded + uploads.length)}
          >
            <Icon name="cross" />
            <span>Skip</span>
          </button>
        </div>
      )}

      <input
        ref={imageInput}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        hidden
        onChange={(event) => void upload(event.target.files)}
      />
      <input
        ref={pdfInput}
        type="file"
        accept="application/pdf,text/plain"
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

      {(uploads.length > 0 || alreadyUploaded > 0) && (
        <div className="kiosk-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={() => onDone(alreadyUploaded + uploads.length)}
            disabled={busy}
          >
            Done — continue
          </button>
        </div>
      )}
    </div>
  );
}

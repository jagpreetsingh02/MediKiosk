/**
 * The doctor adding a paper to the open session.
 *
 * A patient hands over a prescription across the desk, or a report arrives after the intake
 * has already finished. Before this, the only way to get that page into the record was to
 * send the patient back to the kiosk — so in practice it was retyped, and a retyped line has
 * no page, no bounding box and no document tier behind it.
 *
 * ⛔ THE SAME FRONT DOOR AS THE KIOSK, deliberately. This posts to
 * `POST /api/v1/sessions/{ref}/documents` — the one route into OCR — so the page goes through
 * `ingest()`, the consent gate, the size limit, the entity grammar and `record_fact()`,
 * exactly as a patient's own upload does. There is no clinician fast path, and
 * `tests/test_ocr_has_one_front_door.py` is what keeps it that way.
 *
 * ⛔ CONSENT IS NOT THE DOCTOR'S TO GRANT. If the patient declined the `documents` scope, the
 * server refuses with 403 and its own sentence, and that sentence is what appears on screen.
 * `consent.grant` belongs to `patient` in `config/policy.yaml` and is not being widened here:
 * a permission a clinician can give themselves over a patient's papers is not a permission.
 * The correct next step is the patient granting it, and the message says so.
 *
 * The readback is the doctor's own verification lane, which already exists — an upload lands
 * unverified entities in it, and pressing `v` is where they are accepted or corrected. This
 * component therefore ends at "read, N items found"; it does not build a second review UI.
 */
import { useRef, useState } from 'react';
import { ApiError, api, type UploadResult } from '../shared/api';

interface Props {
  sessionRef: string;
  /** Reload the session so the new document and its pending entities appear. */
  onUploaded: () => void | Promise<void>;
}

export function DocumentIntake({ sessionRef, onUploaded }: Props): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<UploadResult | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function send(files: FileList | null): Promise<void> {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      let result: UploadResult | null = null;
      for (const file of Array.from(files)) result = await api.upload(sessionRef, file);
      setLast(result);
      await onUploaded();
    } catch (exc) {
      // The server's wording, verbatim. A refused consent scope and a file that is too large
      // are different problems with different next steps, and the route says which.
      setError(exc instanceof ApiError ? exc.message : 'That file could not be read.');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  return (
    <div className="phys-intake">
      <div className="phys-intake__row">
        <button
          type="button"
          className="btn sm primary"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {busy ? 'Reading…' : 'Add a document'}
        </button>
        <span className="phys-intake__note">
          Photograph or file. Goes through the same OCR pipeline as a patient upload; anything
          unclear lands in the verification lane.
        </span>
      </div>

      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif,application/pdf,text/plain"
        multiple
        hidden
        onChange={(event) => void send(event.target.files)}
      />

      {error && <div className="phys-error">{error}</div>}

      {last && !error && (
        <div className="phys-intake__result" role="status">
          <strong>{last.filename}</strong> · {last.extracted.length} item(s) read
          {last.lowConfidenceCount > 0
            ? ` · ${last.lowConfidenceCount} to verify`
            : ' · read clearly'}
        </div>
      )}
    </div>
  );
}

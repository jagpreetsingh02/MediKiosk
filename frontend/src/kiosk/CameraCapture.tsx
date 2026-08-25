/**
 * Photographing a prescription, with a live preview and a chance to retake.
 *
 * The old "Take Photo" was `<input type="file" accept="image/*" capture>`, which hands the
 * whole job to the OS camera app. On a desktop kiosk that is not a camera at all — it is a
 * file picker — and on a phone it returns whatever the camera app produced with no chance to
 * check the page was in frame before it was uploaded and read. A prescription photographed
 * with the bottom third missing produces an OCR result that is *confidently wrong*, which is
 * worse than a failed scan.
 *
 * So: real `getUserMedia`, a live preview, an explicit Capture, and Retake before anything is
 * sent. The rear camera is requested on devices that have one, at the highest resolution the
 * device will give us — text recognition is resolution-bound, and downscaling before OCR
 * throws away the strokes that distinguish a 5 from a 6.
 *
 * ⛔ THE CAMERA NEVER BLOCKS THE ENCOUNTER. A refused permission, a device with no camera, or
 * a page served over plain HTTP are all ORDINARY STATES here, not errors — they are rendered
 * as a calm explanation with "Choose a file instead" as the primary action, never as a red
 * error banner. A patient who declined the camera has done nothing wrong, and a kiosk that
 * shouts at them for it will lose the document altogether.
 *
 * SECURE CONTEXT. `getUserMedia` is undefined on anything but https:// or localhost, so on a
 * phone reaching a laptop over the LAN it is simply absent — and the honest message is about
 * the connection, not about the camera. See docs/DEMO-DAY.md for the HTTPS path.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../shared/Icon';

interface Props {
  onCaptured: (file: File) => void;
  onCancel: () => void;
  /** Hand the patient straight to the file picker. The camera must never be the only door. */
  onUseFileInstead?: () => void;
}

type Phase = 'starting' | 'live' | 'captured' | 'unavailable';

/** Why the camera is not available. Each is an ordinary situation with its own sentence —
 *  none of them is the patient's mistake. */
type Unavailable = 'denied' | 'absent' | 'insecure' | 'busy' | 'unknown';

const UNAVAILABLE_COPY: Record<Unavailable, string> = {
  denied:
    'The camera is turned off for this page. You can allow it in your browser and try again, ' +
    'or simply choose a photo you have already taken — either works just as well.',
  absent:
    'This device does not have a camera we can use. Choosing a photo or a PDF works just as ' +
    'well.',
  insecure:
    'The camera only works when this page is opened securely. On this device you can still ' +
    'choose a photo or a PDF, which works just as well.',
  busy:
    'Another app is using the camera at the moment. You can close it and try again, or choose ' +
    'a photo you have already taken.',
  unknown:
    'The camera could not be opened just now. Choosing a photo or a PDF works just as well.',
};

export function CameraCapture({
  onCaptured,
  onCancel,
  onUseFileInstead,
}: Props): JSX.Element {
  const video = useRef<HTMLVideoElement | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const [phase, setPhase] = useState<Phase>('starting');
  const [reason, setReason] = useState<Unavailable>('unknown');
  const [error, setError] = useState<string | null>(null);
  const [shot, setShot] = useState<{ url: string; file: File } | null>(null);
  const [attempt, setAttempt] = useState(0);

  const stopCamera = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  // `attempt` is what reopens the stream: Retake bumps it, the effect runs again. One code
  // path for opening the camera instead of two that drift apart.
  useEffect(() => {
    let cancelled = false;

    async function open(): Promise<void> {
      if (!navigator.mediaDevices?.getUserMedia) {
        // `getUserMedia` is absent for two very different reasons, and conflating them sends
        // the patient looking for a camera that is present and working.
        setPhase('unavailable');
        setReason(window.isSecureContext ? 'absent' : 'insecure');
        return;
      }
      try {
        const media = await navigator.mediaDevices.getUserMedia({
          video: {
            // The rear camera on a phone or tablet; ignored on a laptop, which has one.
            facingMode: { ideal: 'environment' },
            // Ask high and let the browser clamp. Small frames lose the thin strokes that
            // separate a 5 from a 6 on a printed dose.
            width: { ideal: 2560 },
            height: { ideal: 1440 },
          },
          audio: false,
        });
        if (cancelled) {
          media.getTracks().forEach((t) => t.stop());
          return;
        }
        stream.current = media;
        if (video.current) {
          video.current.srcObject = media;
          await video.current.play().catch(() => undefined);
        }
        setPhase('live');
      } catch (exc) {
        if (cancelled) return;
        const name = (exc as { name?: string }).name;
        setPhase('unavailable');
        setReason(
          name === 'NotAllowedError' || name === 'SecurityError'
            ? 'denied'
            : name === 'NotFoundError' || name === 'OverconstrainedError'
              ? 'absent'
              : name === 'NotReadableError' || name === 'AbortError'
                ? 'busy'
                : 'unknown',
        );
      }
    }

    void open();
    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [attempt, stopCamera]);

  function capture(): void {
    const element = video.current;
    if (!element || !element.videoWidth) return;

    const canvas = document.createElement('canvas');
    // The full frame, at the sensor's own size. No cropping: a prescription with its top
    // cut off reads as a prescription with fewer medicines on it.
    canvas.width = element.videoWidth;
    canvas.height = element.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) return;
    context.drawImage(element, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        // An empty or trivially small blob means the frame never arrived. Sending it would
        // start an OCR run on nothing and report an extraction failure for a capture bug.
        if (!blob || blob.size < 1024) {
          setError('That photo did not come out. Please try again.');
          return;
        }
        const file = new File([blob], `prescription-${Date.now()}.jpg`, { type: 'image/jpeg' });
        setShot({ url: URL.createObjectURL(blob), file });
        setPhase('captured');
        stopCamera();
      },
      'image/jpeg',
      // High quality deliberately. JPEG artefacts around small text are exactly what makes
      // OCR misread a dose, and the file is read once and discarded.
      0.95,
    );
  }

  function retake(): void {
    if (shot) URL.revokeObjectURL(shot.url);
    setShot(null);
    setError(null);
    setPhase('starting');
    setAttempt((n) => n + 1);
  }

  // AN ORDINARY STATE, NOT AN ERROR. No red banner, no apology, and the way forward is the
  // primary action. Trying again stays available where trying again could plausibly work.
  if (phase === 'unavailable') {
    return (
      <div className="camera camera--unavailable kiosk-panel">
        <h1 className="kiosk-title">Let us use a photo you already have</h1>
        <p className="kiosk-lead">{UNAVAILABLE_COPY[reason]}</p>

        <div className="kiosk-actions">
          {onUseFileInstead && (
            <button type="button" className="btn-primary" onClick={onUseFileInstead}>
              <Icon name="camera" />
              Choose a photo instead
            </button>
          )}
          {(reason === 'denied' || reason === 'busy' || reason === 'unknown') && (
            <button type="button" className="btn-secondary" onClick={retake}>
              Try the camera again
            </button>
          )}
          <button
            type="button"
            className="btn-quiet"
            onClick={() => {
              stopCamera();
              onCancel();
            }}
          >
            Go back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="camera">
      <h1 className="kiosk-title">Take a photo of your paper</h1>

      {phase !== 'captured' && (
        <p className="kiosk-lead">
          Place the whole page inside the frame. Keep it flat, and make sure the writing is
          readable.
        </p>
      )}

      {error && <div className="kiosk-error">{error}</div>}

      <div className="camera-stage">
        {phase === 'captured' && shot ? (
          <img src={shot.url} alt="The photo you just took" className="camera-shot" />
        ) : (
          <>
            <video ref={video} className="camera-video" playsInline muted />
            {phase === 'live' && <div className="camera-guide" aria-hidden="true" />}
            {phase === 'starting' && <div className="camera-status">Opening the camera…</div>}
          </>
        )}
      </div>

      <div className="kiosk-actions">
        {phase === 'live' && (
          <button type="button" className="btn-primary" onClick={capture}>
            <Icon name="camera" />
            Take the photo
          </button>
        )}
        {phase === 'captured' && shot && (
          <>
            <button type="button" className="btn-primary" onClick={() => onCaptured(shot.file)}>
              <Icon name="check" />
              Use this photo
            </button>
            <button type="button" className="btn-quiet" onClick={retake}>
              Take it again
            </button>
          </>
        )}
        <button
          type="button"
          className="btn-quiet"
          onClick={() => {
            stopCamera();
            if (shot) URL.revokeObjectURL(shot.url);
            onCancel();
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

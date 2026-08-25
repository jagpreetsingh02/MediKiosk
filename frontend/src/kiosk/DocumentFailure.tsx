/**
 * What the patient sees when a document could not be read.
 *
 * WHAT THIS REPLACES. One screen, for everything: "We could not read that paper." It is true
 * for every failure and useful for none of them — it names no cause, so the patient cannot
 * tell whether to move the paper into better light, use a different file, or stop trying. The
 * only action offered was Continue, which is a dead end wearing a friendly hat.
 *
 * A failure state has to answer two questions: what went wrong, and what do I do now. So each
 * cause gets its own sentence and its own most-likely-useful action first:
 *
 *   too small        Retake, closer. Nothing else will help — the detail is not in the file.
 *   unreadable       Retake, better light. The bytes did not open as a photograph.
 *   HEIC             Retake with the camera button. Names the iPhone setting, because that
 *                    is a thing the patient can actually change.
 *   wrong type       Upload a different file. Retaking would produce the same result.
 *   too large        Retake — a capture is smaller than a gallery original almost always.
 *   nothing found    The file opened and was read; there was simply no printed text. Handwriting
 *                    lands here, and this is the honest answer to it.
 *
 * ⛔ HANDWRITING IS EXPECTED TO FAIL, AND IS NOT FAKED. Tesseract does not read handwriting,
 * and no wording here pretends otherwise. What it says instead is true and useful: the doctor
 * will see the picture, and you can type the important parts yourself. Inventing a plausible
 * reading of a handwritten prescription would be the single most dangerous thing this product
 * could do.
 *
 * NO BACKEND NAME, NO CONFIG STRING, EVER. Not "tesseract", not "textlayer", not
 * "max_upload_bytes", not an HTTP status. The operator's detail goes to the log, where the
 * operator is. `test_failure_ux` asserts this on every branch.
 */
import type { ReactNode } from 'react';
import { Icon } from '../shared/Icon';

export type FailureReason =
  | 'too_small'
  | 'unreadable_image'
  | 'heic_unreadable'
  | 'unsupported_type'
  | 'too_large'
  | 'empty_file'
  | 'no_text_found'
  | 'unknown';

interface Props {
  reason: FailureReason;
  /** The kiosk's own sentence, when the server sent one worth showing. */
  message?: string | null;
  filename?: string;
  onRetake: () => void;
  onChooseAnother: () => void;
  onEnterManually: () => void;
  onSkip: () => void;
}

interface Copy {
  title: string;
  body: ReactNode;
  /** Which action is most likely to work. Rendered first and as the primary. */
  primary: 'retake' | 'another' | 'manual';
}

const COPY: Record<FailureReason, Copy> = {
  too_small: {
    title: 'The photo is too small to read',
    body: 'The writing is there, but not clearly enough for us to read it. Taking another photo a little closer to the paper usually fixes this.',
    primary: 'retake',
  },
  unreadable_image: {
    title: 'We could not open that photo',
    body: 'Something about that file stopped us opening it as a picture. Taking a new photo with the camera button on this screen is the quickest way round it.',
    primary: 'retake',
  },
  heic_unreadable: {
    title: 'That photo is in a format we could not open',
    body: (
      <>
        iPhone photos are sometimes saved in a format this kiosk cannot read. Taking the photo
        again with the camera button here will work. If you would rather use a photo you
        already have, changing your iPhone camera setting to <strong>Most Compatible</strong>{' '}
        also fixes it.
      </>
    ),
    primary: 'retake',
  },
  unsupported_type: {
    title: 'We cannot read that kind of file',
    body: 'This kiosk reads photographs and PDF files. Taking a photo of the paper is usually easiest.',
    primary: 'another',
  },
  too_large: {
    title: 'That file is too big for this kiosk',
    body: 'Taking a photo with the camera button on this screen makes a smaller file, which will work. If the file has many pages, you can also add one page at a time.',
    primary: 'retake',
  },
  empty_file: {
    title: 'That file was empty',
    body: 'Nothing came through when that file was chosen. Please pick it again, or take a photo of the paper.',
    primary: 'another',
  },
  no_text_found: {
    title: 'We could not find any printed writing on that page',
    body: (
      <>
        The picture came through clearly — there was just no printed text on it that we could
        read. This is normal for <strong>handwritten</strong> notes: we do not try to guess at
        handwriting, because guessing at a medicine name is not safe.
        <br />
        <br />
        The doctor will still see the picture you took, so nothing is lost. You can also type
        the important parts yourself.
      </>
    ),
    primary: 'manual',
  },
  unknown: {
    title: 'We could not read that paper',
    body: 'Something went wrong while reading it. The doctor will still see the picture you took, so nothing is lost.',
    primary: 'retake',
  },
};

export function DocumentFailure({
  reason,
  message,
  filename,
  onRetake,
  onChooseAnother,
  onEnterManually,
  onSkip,
}: Props): JSX.Element {
  const copy = COPY[reason] ?? COPY.unknown;

  const actions = {
    retake: (
      <button key="retake" type="button" className="btn-primary" onClick={onRetake}>
        <Icon name="camera" />
        Take the photo again
      </button>
    ),
    another: (
      <button key="another" type="button" className="btn-secondary" onClick={onChooseAnother}>
        Upload a different file
      </button>
    ),
    manual: (
      <button key="manual" type="button" className="btn-secondary" onClick={onEnterManually}>
        Type it in myself
      </button>
    ),
  };

  // The most useful action first and styled as the primary; the other two stay available,
  // because "most likely" is not "only", and a patient who knows their file is fine should
  // not have to fight the screen's guess.
  const order: Array<keyof typeof actions> = [
    copy.primary,
    ...(['retake', 'another', 'manual'] as const).filter((k) => k !== copy.primary),
  ];

  return (
    <div className="kiosk-panel kx-failure" data-reason={reason}>
      <div className="kx-failure__glyph" aria-hidden="true">
        <Icon name="other" />
      </div>

      <h1 className="kiosk-title">{copy.title}</h1>
      <p className="kiosk-lead">{copy.body}</p>

      {/* The server's own sentence, when it sent one — it is written for the patient too, and
          often more specific than ours (it can name the actual file size, for instance). */}
      {message && <p className="kx-failure__detail">{message}</p>}

      {filename && <p className="kx-footnote">File: {filename}</p>}

      <div className="kiosk-actions kx-failure__actions">{order.map((key) => actions[key])}</div>

      <button type="button" className="btn-link kx-failure__skip" onClick={onSkip}>
        Carry on without this paper
      </button>
    </div>
  );
}

/** Map whatever the server said onto a screen. Unknown codes fall back rather than throwing —
 *  a failure screen that itself fails is the worst possible outcome here. */
export function failureReasonFrom(
  serverReason: string | undefined,
  status: number | undefined,
): FailureReason {
  const known: FailureReason[] = [
    'too_small',
    'unreadable_image',
    'heic_unreadable',
    'unsupported_type',
    'too_large',
    'empty_file',
    'no_text_found',
  ];
  if (serverReason && (known as string[]).includes(serverReason)) {
    return serverReason as FailureReason;
  }
  if (status === 413) return 'too_large';
  return 'unknown';
}

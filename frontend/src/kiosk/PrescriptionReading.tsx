/**
 * "This is what your paper says. This is what we think it means."
 *
 * The two columns are the entire safety model of the handwriting lane, rendered. On the left
 * is the OCR transcription, unedited, including its mistakes. On the right is what MediKiosk
 * made of it. They are never merged, and the left column is never replaced by the right —
 * so an interpretation that is wrong is *visibly* wrong to the person holding the paper,
 * rather than authoritative.
 *
 * The three states a line can be in are given three different visual treatments on purpose,
 * because they are three different claims:
 *
 *  - **read** — the name matched the medicine list outright, or was corrected past the point
 *    of doubt. Stated plainly.
 *  - **needs confirmation** — something resembles a known medicine but not enough to say so.
 *    Rendered as a QUESTION ("possibly Augmentin — 91% match"), never as an answer, because
 *    the difference between "possibly Augmentin" and "Augmentin" is the whole point.
 *  - **not read** — the characters were not legible. Shown as a gap, which is the honest
 *    thing, and is also visibly a gap so nobody assumes the paper had nothing else on it.
 */
import type { InterpretedMedication } from '../shared/api';
import { Icon } from '../shared/Icon';

interface Props {
  rawOcrText: string;
  medications: InterpretedMedication[];
  /** Which engine read it. Shown because "read by a handwriting model" and "read by a
   *  printed-text engine" are different levels of certainty about the same page. */
  backend?: string;
}

type Certainty = 'read' | 'confirm' | 'unread';

function certaintyOf(medication: InterpretedMedication): Certainty {
  if (medication.medication.name) {
    return medication.needsVerification ? 'confirm' : 'read';
  }
  return medication.nameMatch.candidates.length ? 'confirm' : 'unread';
}

const CERTAINTY_LABEL: Record<Certainty, string> = {
  read: 'Read clearly',
  confirm: 'Please confirm this one',
  unread: 'Could not be read',
};

export function PrescriptionReading({
  rawOcrText,
  medications,
  backend,
}: Props): JSX.Element | null {
  if (!medications.length) return null;

  const unsure = medications.filter((m) => certaintyOf(m) !== 'read').length;

  return (
    <section className="reading" aria-label="What we read from your prescription">
      <div className="reading-head">
        <h2 className="reading-title">What your prescription says</h2>
        {backend === 'trocr' && (
          <p className="reading-engine">
            <Icon name="other" /> Read with handwriting recognition. Handwriting is harder to
            read than print, so please check each line.
          </p>
        )}
      </div>

      <ol className="reading-list">
        {medications.map((medication, index) => {
          const certainty = certaintyOf(medication);
          const best = medication.nameMatch.candidates[0];
          const detail = medication.medication;
          return (
            <li key={`${medication.rawText}-${index}`} className={`reading-row ${certainty}`}>
              <div className="reading-side">
                <div className="reading-label">Written on the paper</div>
                {/* The transcription is rendered in a monospaced face and in quotes so it
                    reads as a QUOTATION of the document rather than as MediKiosk's own
                    words. It is the one string on this screen that nothing has edited. */}
                <div className="reading-raw">&ldquo;{medication.rawText}&rdquo;</div>
              </div>

              {/* Plain text, not an icon: the arrow is read out by a screen reader as
                  nothing at all, and the two sides are already labelled. */}
              <div className="reading-arrow" aria-hidden="true">
                →
              </div>

              <div className="reading-side">
                <div className="reading-label">What we understand it to mean</div>
                {detail.name ? (
                  <>
                    <div className="reading-name">
                      {detail.name}
                      {detail.strength ? ` ${detail.strength}` : ''}
                    </div>
                    {detail.generic && detail.generic !== detail.name && (
                      <div className="reading-generic">The medicine in it is {detail.generic}</div>
                    )}
                    <div className="reading-instruction">{instructionOf(medication)}</div>
                  </>
                ) : best ? (
                  <>
                    <div className="reading-name unsure">
                      Possibly {best.display}
                      {detail.strength ? ` ${detail.strength}` : ''}
                    </div>
                    <div className="reading-generic">
                      {Math.round(best.score * 100)}% match — not confirmed
                    </div>
                  </>
                ) : (
                  <div className="reading-name unsure">We could not read this medicine name</div>
                )}

                <div className={`reading-certainty ${certainty}`}>
                  {CERTAINTY_LABEL[certainty]}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {unsure > 0 && (
        <p className="reading-warning">
          <Icon name="other" />{' '}
          {unsure === 1
            ? 'One medicine could not be read with certainty. Please check it with your doctor or pharmacist before taking it.'
            : `${unsure} medicines could not be read with certainty. Please check them with your doctor or pharmacist before taking them.`}
        </p>
      )}

      <details className="reading-full">
        <summary>Show everything we read from the page</summary>
        {/* The complete transcription, mistakes included. It is here rather than on the main
            view because a patient does not need it — but a pharmacist checking a disputed
            line does, and it must never require a second request to obtain. */}
        <pre className="reading-transcript">{rawOcrText}</pre>
      </details>
    </section>
  );
}

/** The schedule as one sentence, built only from the parts that were actually found.
 *
 *  Assembled rather than templated: a template renders "Take  for " when half the line was
 *  unreadable, which teaches a patient that the machine is broken rather than that the line
 *  was unclear. */
function instructionOf(medication: InterpretedMedication): string {
  const { dose, frequency, timing, instruction, duration, route } = medication.medication;
  const parts = [
    dose ? `Take ${dose}` : null,
    frequency,
    timing,
    instruction,
    route,
    duration ? `for ${duration}` : null,
  ].filter((part): part is string => Boolean(part));
  return parts.length ? capitalise(parts.join(', ')) : 'No instructions could be read';
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

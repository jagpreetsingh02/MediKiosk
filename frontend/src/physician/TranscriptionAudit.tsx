/**
 * What the page appears to say, what MediKiosk made of it, and how it got there.
 *
 * The patient's version of this screen (`kiosk/PrescriptionReading.tsx`) shows the same two
 * columns in coarse bands, because "0.8137" means nothing to a patient and inviting them to
 * read it as an 81% chance the medicine is right is worse than saying nothing.
 *
 * A physician is the opposite case. They are being asked to accept or reject a machine
 * reading, and they cannot do that without the numbers behind it — so this shows both
 * confidences separately, and the provenance of every field:
 *
 *  - **OCR confidence** — how sure the recogniser was about the CHARACTERS.
 *  - **Interpretation confidence** — how sure the parser was about the MEANING.
 *
 * They are genuinely independent. A crisply-photographed line reading "Xyzqw 200 BD" has a
 * high OCR confidence and no interpretation at all; a smudged "Augmentin 625 BD" has the
 * reverse. Collapsing them into one number destroys the distinction a reviewer needs most.
 */
import type { InterpretedMedication } from '../shared/api';

interface Props {
  filename: string;
  rawOcrText: string;
  medications: InterpretedMedication[];
  backend: string;
}

/** How a field's value came to be what it is. Four different claims, four different labels. */
const SOURCE_LABEL: Record<string, string> = {
  ocr: 'read from the page',
  bare: 'read from the page, no unit written',
  abbreviation: 'abbreviation table',
  positional: 'positional notation',
  dictionary: 'supplied from the medication list',
};

const FIELD_ORDER = [
  'form',
  'strength',
  'dose',
  'frequency',
  'timing',
  'instruction',
  'route',
  'duration',
];

export function TranscriptionAudit({
  filename,
  rawOcrText,
  medications,
  backend,
}: Props): JSX.Element | null {
  if (!medications.length) return null;

  return (
    <section className="audit" aria-label={`Transcription and interpretation for ${filename}`}>
      <header className="audit-head">
        <span className="audit-engine">read by {backend}</span>
        {backend === 'trocr' && (
          <span className="audit-engine warn">handwriting model — line by line</span>
        )}
      </header>

      {medications.map((medication, index) => {
        const { medication: detail, nameMatch } = medication;
        return (
          <article
            key={`${medication.rawText}-${index}`}
            className={`audit-row${medication.needsVerification ? ' unsure' : ''}`}
          >
            <div className="audit-raw">
              <span className="audit-tag">transcribed</span>
              <code>{medication.rawText}</code>
            </div>

            <div className="audit-interpreted">
              <span className="audit-tag">interpreted</span>
              {detail.name ? (
                <strong>{medication.sentence}</strong>
              ) : (
                <strong className="unresolved">{medication.sentence}</strong>
              )}
            </div>

            {/* The candidates are shown ONLY when nothing was auto-applied. Listing
                alternatives beside a name that was accepted invites a reviewer to
                second-guess a decision the system did not actually make. */}
            {!detail.name && nameMatch.candidates.length > 0 && (
              <ul className="audit-candidates">
                {nameMatch.candidates.map((candidate) => (
                  <li key={candidate.matchedOn}>
                    {candidate.display} — {Math.round(candidate.score * 100)}% match against{' '}
                    {candidate.matchedKind} &ldquo;{candidate.matchedOn}&rdquo;
                  </li>
                ))}
              </ul>
            )}

            <dl className="audit-fields">
              {FIELD_ORDER.filter((key) => medication.fields[key]).map((key) => {
                const field = medication.fields[key];
                return (
                  <div key={key} className="audit-field">
                    <dt>{key}</dt>
                    <dd>
                      {field.value}
                      <span className="audit-provenance">
                        &ldquo;{field.raw}&rdquo; · {SOURCE_LABEL[field.source] ?? field.source}
                      </span>
                    </dd>
                  </div>
                );
              })}
            </dl>

            <div className="audit-scores">
              <span>
                OCR <b>{medication.ocrConfidence.toFixed(2)}</b>
              </span>
              <span>
                interpretation <b>{medication.interpretationConfidence.toFixed(2)}</b>
              </span>
              <span className={medication.needsVerification ? 'warn' : 'ok'}>
                {medication.needsVerification ? 'needs verification' : 'no verification needed'}
              </span>
              <span className="audit-status">name resolved as: {nameMatch.status}</span>
            </div>
          </article>
        );
      })}

      <details className="audit-full">
        <summary>Full OCR transcription of this page</summary>
        <pre>{rawOcrText}</pre>
      </details>
    </section>
  );
}

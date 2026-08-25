/**
 * What a clinical line actually came from, opened by clicking it.
 *
 * FOUR KINDS OF SOURCE, FOUR DIFFERENT SCREENS. Rendering them identically would be the
 * quiet failure here: a voice transcript and a typed answer look the same as text, but one
 * carries an ASR confidence and a degradation policy behind it and the other is exactly what
 * the patient typed. Collapsing them tells a physician less than the record actually knows.
 *
 *   document   the cropped page region OCR read, with its confidence and any human reading
 *   voice      the transcript segment, with the score the engine gave it — or "not measured"
 *   touch      the option the patient pressed
 *   typed      the words the patient typed
 *
 * ⛔ AN UNMEASURED CONFIDENCE IS NOT A LOW ONE. Several browsers report no ASR score at all
 * for Indic locales, and the backend preserves that as null rather than substituting a
 * number. This renders it as "not measured" — never as 0, never as a bar at zero width, both
 * of which read as "the engine was unsure" when the truth is "nobody measured".
 */
import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { api, type BriefEvidence, type FactEvidence } from '../shared/api';
import { SourceCrop } from '../kiosk/SourceCrop';
import { Icon } from '../shared/Icon';
import { springSoft } from '../design/motion';

interface Props {
  patientRef: string;
  encounterRef: string;
  factRef: string | null;
  onClose: () => void;
}

/** The modality names are ours; these are the words a person uses. */
const ORIGIN_LABEL: Record<string, string> = {
  document: 'Read from a document',
  voice: 'Spoken by the patient',
  touch: 'Chosen by the patient',
  typed: 'Typed by the patient',
};

function originOf(e: BriefEvidence): string {
  if (e.sourceType === 'document') return 'document';
  return e.modality ?? 'typed';
}

function OneSource({ evidence, patientRef }: { evidence: BriefEvidence; patientRef: string }) {
  const origin = originOf(evidence);

  return (
    <div className="bx-source" data-origin={origin}>
      <div className="bx-source__head">
        <Icon name={origin === 'document' ? 'image' : origin === 'voice' ? 'mic' : 'other'} />
        <span className="bx-source__kind">{ORIGIN_LABEL[origin] ?? origin}</span>
      </div>

      {/* The page region the words were lifted from. Shown ABOVE the text, because the
          image is the evidence and the text is our reading of it. */}
      {origin === 'document' && evidence.documentRef && evidence.bbox && (
        <SourceCrop
          pageUrl={api.documentFileUrl(patientRef, evidence.documentRef, evidence.page ?? 1)}
          bbox={evidence.bbox}
          label={evidence.verbatim}
          maxHeight={120}
        />
      )}

      <blockquote className="bx-source__verbatim">{evidence.verbatim}</blockquote>

      <dl className="bx-source__meta">
        {origin === 'voice' && (
          <>
            <dt>Recognition confidence</dt>
            <dd>
              {evidence.asrConfidence === null ? (
                // Not a zero, and not a low score. Nobody measured it.
                <span className="bx-unmeasured">not measured</span>
              ) : (
                evidence.asrConfidence.toFixed(2)
              )}
            </dd>
          </>
        )}
        {origin === 'document' && evidence.ocrConfidence !== null && (
          <>
            <dt>OCR confidence</dt>
            <dd>{evidence.ocrConfidence.toFixed(2)}</dd>
          </>
        )}
        {evidence.page !== null && (
          <>
            <dt>Page</dt>
            <dd>{evidence.page}</dd>
          </>
        )}
        {evidence.questionId && (
          <>
            <dt>Question</dt>
            <dd>{evidence.questionId}</dd>
          </>
        )}
        <dt>Language</dt>
        <dd>{evidence.language}</dd>
      </dl>

      {evidence.handwritten && (
        <p className="bx-source__flag">
          Handwritten. OCR does not read handwriting, and no reading here is guessed from it.
        </p>
      )}

      {/* A named human's reading sits BESIDE the scrawl, never instead of it. */}
      {evidence.humanReading && (
        <p className="bx-source__human">
          Read as <strong>{evidence.humanReading}</strong>
          {evidence.readBy ? ` by ${evidence.readBy}` : ''}
        </p>
      )}
    </div>
  );
}

export function EvidencePanel({ patientRef, encounterRef, factRef, onClose }: Props): JSX.Element {
  const [detail, setDetail] = useState<FactEvidence | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!factRef) return;
    let live = true;
    setDetail(null);
    setError(null);
    api
      .briefEvidence(patientRef, encounterRef, factRef)
      .then((d) => live && setDetail(d))
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Could not open the source.'));
    return () => {
      live = false;
    };
  }, [patientRef, encounterRef, factRef]);

  return (
    <AnimatePresence>
      {factRef && (
        <motion.aside
          className="bx-evidence mk-glass"
          role="dialog"
          aria-label="Where this came from"
          initial={{ opacity: 0, x: 32 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 32, transition: { duration: 0.16 } }}
          transition={springSoft}
        >
          <header className="bx-evidence__head">
            <h3>Where this came from</h3>
            <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
              <Icon name="cross" />
            </button>
          </header>

          {error && <p className="bx-evidence__error">{error}</p>}
          {!detail && !error && <div className="bx-evidence__loading" aria-hidden="true" />}

          {detail && (
            <>
              <div className="bx-evidence__value">
                <span className="bx-evidence__path">{detail.path}</span>
                <strong>{detail.displayValue ?? String(detail.value ?? '')}</strong>
              </div>

              <div className="bx-evidence__tier">
                <span className={`mk-badge mk-badge--${detail.tier}`}>{detail.tier}</span>
                {detail.confirmedByPhysician ? (
                  <span className="mk-badge mk-badge--ok">confirmed by a physician</span>
                ) : (
                  <span className="mk-badge">not yet confirmed</span>
                )}
              </div>

              {detail.evidence.length === 0 ? (
                // Should be unreachable: a fact with no evidence is never rendered as a line.
                // Saying so is better than an empty panel that looks like a loading failure.
                <p className="bx-evidence__error">
                  This fact has no recorded source, so it should not have appeared. Please
                  report it.
                </p>
              ) : (
                detail.evidence.map((e, i) => (
                  <OneSource key={i} evidence={e} patientRef={patientRef} />
                ))
              )}
            </>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

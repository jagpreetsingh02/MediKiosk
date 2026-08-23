/**
 * The patient reads back what they told us, before the doctor sees it.
 *
 * This is the cheapest guard in the whole system against a mishearing reaching a physician:
 * the person who said it checks it. It is deliberately NOT the doctor's summary — no tiers,
 * no confidence, no clinical vocabulary. Just the question they were asked and the words that
 * were recorded, with one button to fix any of it.
 *
 * Correcting re-presents that single question. The old answer is superseded rather than
 * deleted, so the physician still sees the correction and what it corrected.
 */
import { useEffect, useState } from 'react';
import { ApiError, api, type ReviewAnswer } from '../shared/api';

interface Props {
  sessionRef: string;
  onCorrect: (questionId: string) => void;
  onConfirm: () => void;
}

export function PatientReview({ sessionRef, onCorrect, onConfirm }: Props): JSX.Element {
  const [answers, setAnswers] = useState<ReviewAnswer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .review(sessionRef)
      .then(body => setAnswers(body.answers))
      .catch(exc => setError(exc instanceof ApiError ? exc.message : 'Could not load your answers.'));
  }, [sessionRef]);

  if (error) return <div className="kiosk-panel"><div className="kiosk-error">{error}</div></div>;
  if (!answers) return <div className="kiosk-panel"><p className="kiosk-lead">Loading…</p></div>;

  const sections = answers.reduce<Record<string, ReviewAnswer[]>>((acc, answer) => {
    (acc[answer.sectionTitle] ??= []).push(answer);
    return acc;
  }, {});

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">Please check what you told us</h1>
      <p className="kiosk-lead">
        If anything here is wrong, touch <strong>Change this</strong> and we will ask you again.
      </p>

      {Object.entries(sections).map(([title, entries]) => (
        <section key={title} style={{ marginBottom: 26 }}>
          <div className="kiosk-section-label">{title}</div>
          {entries.map(entry => (
            <div key={entry.questionId} className="review-row">
              <div>
                <div className="review-q">{entry.question}</div>
                <div className="review-a">{entry.answer}</div>
              </div>
              {entry.canCorrect && (
                <button
                  type="button"
                  className="btn-quiet"
                  style={{ minHeight: 62, fontSize: 19, padding: '0 22px', flex: '0 0 auto' }}
                  onClick={() => onCorrect(entry.questionId)}
                >
                  Change this
                </button>
              )}
            </div>
          ))}
        </section>
      ))}

      <div className="kiosk-actions">
        <button type="button" className="btn-primary" onClick={onConfirm}>
          Yes, this is right
        </button>
      </div>
    </div>
  );
}

/**
 * The handwriting lane.
 *
 * Nothing here is in the patient's record yet. These are entities the OCR read with low
 * confidence, and they become facts only when a human presses Accept — which is the whole
 * point of the lane existing rather than the values being merged with a warning icon.
 */
import { useState } from 'react';

export interface PendingEntity {
  entityIndex: number;
  kind: string;
  text: string;
  confidence: number;
  sourceText: string;
  page: number;
  documentId: string;
}

interface Props {
  pending: PendingEntity[];
  busy: boolean;
  onDecide: (entity: PendingEntity, accepted: boolean, correctedText?: string) => void;
}

export function VerificationLane({ pending, busy, onDecide }: Props): JSX.Element {
  const [edits, setEdits] = useState<Record<number, string>>({});

  if (!pending.length) {
    return (
      <div className="source-empty">
        Nothing is waiting for verification. Anything the OCR read with low confidence would
        appear here, and would not be in the record until you accepted it.
      </div>
    );
  }

  return (
    <div>
      {pending.map((entity) => (
        <div key={`${entity.documentId}-${entity.entityIndex}`} className="lane-item">
          <div>
            <span className="badge">{entity.kind}</span>{' '}
            <strong>{entity.text}</strong>{' '}
            <span style={{ color: 'var(--ink-3)' }}>
              · {(entity.confidence * 100).toFixed(0)}% confidence · page {entity.page}
            </span>
          </div>
          <div className="lane-source">read as: “{entity.sourceText}”</div>
          <input
            className="btn"
            style={{ width: '100%', marginBottom: 7, fontWeight: 400 }}
            value={edits[entity.entityIndex] ?? entity.text}
            onChange={(event) =>
              setEdits((current) => ({ ...current, [entity.entityIndex]: event.target.value }))
            }
            aria-label="Corrected text"
          />
          <div className="lane-actions">
            <button
              type="button"
              className="btn sm ok"
              disabled={busy}
              onClick={() => {
                const corrected = edits[entity.entityIndex];
                onDecide(entity, true, corrected !== entity.text ? corrected : undefined);
              }}
            >
              Accept
            </button>
            <button
              type="button"
              className="btn sm danger"
              disabled={busy}
              onClick={() => onDecide(entity, false)}
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Prior visits of THE SAME PATIENT that share recorded features with this one.
 *
 * Deterministic set intersection, and the result lists the features rather than scoring the
 * match. That is a deliberate refusal: a percentage next to two clinical encounters reads as
 * a probability of recurrence however it is labelled, and this system does not predict
 * disease. The physician sees which features overlap and decides what it means.
 */
import type { SimilarEncounter } from '../shared/api';

interface Props {
  similar: SimilarEncounter[];
  onOpenEncounter: (encounterRef: string) => void;
}

export function SimilarEncounters({ similar, onOpenEncounter }: Props): JSX.Element {
  if (!similar.length) {
    return (
      <div className="source-empty">
        No previous visit of this patient shares recorded features with today&apos;s.
      </div>
    );
  }

  return (
    <div className="sim">
      {similar.map((match) => (
        <section key={match.encounterRef} className="sim-card">
          <header className="sim-head">
            <h3>{formatDate(match.occurredOn)}</h3>
            <span className="sim-band">{match.band}</span>
          </header>
          {match.headline && <p className="sim-headline">{match.headline}</p>}

          <ul className="sim-shared">
            {match.shared.map((entry) => (
              <li key={`${entry.path}-${entry.value}`}>
                <span className="sim-tick">✓</span>
                <span className="sim-feature">{entry.feature}</span>
                <span className="sim-value">{entry.value}</span>
              </li>
            ))}
          </ul>

          <button
            type="button"
            className="btn sm"
            onClick={() => onOpenEncounter(match.encounterRef)}
          >
            Open encounter
          </button>
          <p className="sim-note">{match.note}</p>
        </section>
      ))}
    </div>
  );
}

function formatDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

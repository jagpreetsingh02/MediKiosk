/**
 * TODAY beside HISTORY — the screen the whole longitudinal build exists to produce.
 *
 * A physician with three minutes does not open a second tab to remember whether this patient
 * came in with the same abdominal pain eighteen months ago. Two columns, the same features
 * lined up on both sides, and the shared ones marked. The marking is a set intersection over
 * recorded values, so every tick is a value the patient actually stated at both visits — not
 * a similarity model's opinion about them.
 *
 * There is deliberately no percentage anywhere on this component. "92% similar" reads as a
 * probability of recurrence, and this system does not do that (Invariant 1).
 */
import type { PatientContext, SimilarEncounter } from '../shared/api';

interface Props {
  context: PatientContext;
  /** Today's features, from the live ledger. */
  onOpenEncounter: (encounterRef: string) => void;
}

export function CurrentVsHistory({ context, onOpenEncounter }: Props): JSX.Element | null {
  const match: SimilarEncounter | undefined = context.similar[0];
  if (!context.known || !match) return null;

  const sharedByPath = new Map<string, Set<string>>();
  for (const entry of match.shared) {
    if (!sharedByPath.has(entry.path)) sharedByPath.set(entry.path, new Set());
    sharedByPath.get(entry.path)?.add(entry.value);
  }

  // Labels come from the backend, which already holds them for the shared-feature list.
  const rows = (context.currentFeatures ?? []).filter((row) => row.values.length > 0);

  // Collapsed by default — this is a lot of screen real estate for something that matters
  // less than the summary itself, and the summary line below already says what it would
  // have told you: how many features this visit shares with the last one.
  return (
    <details className="cvh">
      <summary className="cvh-head">
        <div>
          <span className="cvh-tag today">Today</span>
          <span className="cvh-date">This visit</span>
        </div>
        <div>
          <span className="cvh-tag past">History</span>
          <span className="cvh-date">
            {formatDate(match.occurredOn)}
            {match.headline ? ` · ${match.headline}` : ''}
          </span>
        </div>
        {/* `match.band` is already words, not the count — see `_band()` on the backend, which
            exists specifically so this never reads like a percentage or a probability. */}
        <span className="cvh-band">{match.band}</span>
      </summary>

      <div className="cvh-grid">
        {rows.map((row) => {
          const shared = sharedByPath.get(row.path) ?? new Set<string>();
          return (
            <div className="cvh-row" key={row.path}>
              <div className="cvh-label">{row.label}</div>
              <div className="cvh-cell">
                {row.values.map((value) => (
                  <span
                    key={value}
                    className={`cvh-value${shared.has(value) ? ' shared' : ''}`}
                  >
                    {value}
                  </span>
                ))}
              </div>
              <div className="cvh-cell past">
                {shared.size ? (
                  [...shared].map((value) => (
                    <span key={value} className="cvh-value shared">
                      {value}
                    </span>
                  ))
                ) : (
                  <span className="cvh-absent">not recorded then</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="cvh-foot">
        <button
          type="button"
          className="btn sm"
          onClick={() => onOpenEncounter(match.encounterRef)}
        >
          Open previous visit
        </button>
      </div>
      <p className="cvh-note">{match.note}</p>
    </details>
  );
}

function formatDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

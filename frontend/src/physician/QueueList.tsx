/**
 * The triage queue, highest priority first.
 *
 * Ordering is the backend's — `immediate`, then `urgent`, then `routine`, each by arrival.
 * Sorting it here would put a second ordering policy in the codebase, and the two would drift.
 */
import type { QueueEntry } from '../shared/api';

interface Props {
  entries: QueueEntry[];
  activeRef: string | null;
  onSelect: (ref: string) => void;
}

export function QueueList({ entries, activeRef, onSelect }: Props): JSX.Element {
  return (
    <nav aria-label="Patient queue">
      <div className="queue-head">
        Queue · {entries.length} waiting
      </div>
      {!entries.length && (
        <div style={{ padding: 14, fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          No sessions in progress. Start one on the kiosk surface.
        </div>
      )}
      {entries.map((entry, index) => (
        <button
          key={entry.sessionRef}
          type="button"
          className={`queue-item ${entry.priority}${entry.sessionRef === activeRef ? ' active' : ''}`}
          onClick={() => onSelect(entry.sessionRef)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className={`badge ${entry.priority}`}>{entry.priority}</span>
            {index < 9 && <kbd>{index + 1}</kbd>}
          </div>
          <div className="queue-ref" style={{ marginTop: 5 }}>{entry.sessionRef}</div>
          <div className="queue-meta">
            <span>{entry.waitingMinutes}m waiting</span>
            <span>·</span>
            <span>{entry.language}</span>
            {entry.ayushMode && <span>· AYUSH</span>}
            <span>·</span>
            <span>{entry.status.replace(/_/g, ' ')}</span>
          </div>
        </button>
      ))}
    </nav>
  );
}

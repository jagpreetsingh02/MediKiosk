/**
 * Who to see next, and one key to open them.
 *
 * The workspace used to open on "Select a patient from the queue, or press 1–9". That is an
 * instruction, not an answer: the doctor's actual first question is *which one*, and the
 * system already knows — the queue arrives priority-ordered from the server, so the head of
 * it is the answer. Making the doctor read a sidebar to rediscover the ordering the backend
 * had already computed was the whole cost of not saying it.
 *
 * ⛔ THE ORDERING IS THE SERVER'S, and this component does not re-derive it. `entries[0]` is
 * the next patient because `/api/v1/queue` sorted by `immediate → urgent → routine`, then by
 * arrival. Sorting here would put a second triage policy in the codebase, and the day the two
 * disagreed, the screen that says "next" would be the one that was wrong. Same reasoning as
 * `QueueList`.
 *
 * ⛔ NO CLINICAL CONTENT. A queue entry carries a priority band, a wait, a language and a
 * status — never why someone is urgent. That is the same line `triage_nurse` sits on in
 * `config/policy.yaml`, and this panel renders before a session is opened, so it must hold
 * to it: what is shown here is what a triage desk is allowed to see.
 */
import type { QueueEntry } from '../shared/api';

interface Props {
  entries: QueueEntry[];
  onOpen: (sessionRef: string) => void;
}

const PRIORITY_NOTE: Record<string, string> = {
  immediate: 'A red flag rule fired. See this patient first.',
  urgent: 'Flagged for early review.',
  routine: 'No escalation rule fired.',
};

export function NextPatient({ entries, onOpen }: Props): JSX.Element {
  const next = entries[0];

  if (!next) {
    return (
      <div className="phys-next phys-next--empty">
        <h2>Nobody is waiting</h2>
        <p>
          Sessions appear here as patients complete their intake. Start one from the patient
          surface, or open a synthetic case from the demo launcher.
        </p>
      </div>
    );
  }

  const behind = entries.length - 1;

  return (
    <div className="phys-next">
      <div className="phys-next__head">
        <span className="phys-next__eyebrow">Next to assess</span>
        <span className={`badge ${next.priority}`}>{next.priority}</span>
      </div>

      <div className="phys-next__ref">{next.sessionRef}</div>

      <div className="phys-next__meta">
        <span>{next.waitingMinutes}m waiting</span>
        <span>·</span>
        <span>{next.language}</span>
        {next.ayushMode && <span>· AYUSH</span>}
        <span>·</span>
        <span>{next.status.replace(/_/g, ' ')}</span>
      </div>

      <p className="phys-next__why">{PRIORITY_NOTE[next.priority] ?? ''}</p>

      <button
        type="button"
        className="btn primary"
        onClick={() => onOpen(next.sessionRef)}
      >
        Open this patient <kbd>1</kbd>
      </button>

      <p className="phys-next__behind">
        {behind > 0
          ? `${behind} more ${behind === 1 ? 'patient' : 'patients'} waiting behind this one.`
          : 'Nobody else is waiting.'}
      </p>

      <p className="phys-next__hint">
        Opening a patient loads their prepared history: the clinical brief, today&apos;s intake,
        their whole timeline, medications, past visits and every document on file.
      </p>
    </div>
  );
}

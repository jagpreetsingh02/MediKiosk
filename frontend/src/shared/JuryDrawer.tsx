/**
 * The jury drawer — the engineering a demo otherwise hides.
 *
 * The interesting properties of this system are invisible in a screenshot. That the question
 * order came from a state machine and not a model; that twenty-two rules were evaluated and
 * two fired; that every recorded fact names a source span; that the audit chain still
 * verifies. A judge should be able to see all of that without reading the repository — and
 * without it cluttering the screen a clinician is trying to work on.
 *
 * Toggled with `d`. Closed by default.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { api, type Inspect } from './api';

interface Props {
  sessionRef: string | null;
}

export function JuryDrawer({ sessionRef }: Props): JSX.Element | null {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Inspect | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionRef) return;
    try {
      setData(await api.inspect(sessionRef));
      setError(null);
    } catch {
      setError('Could not read the session internals.');
    }
  }, [sessionRef]);

  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.key === 'd') setOpen(current => !current);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  if (!sessionRef) return null;

  if (!open) {
    return (
      <button type="button" className="jury-tab" onClick={() => setOpen(true)}>
        Jury view <kbd>d</kbd>
      </button>
    );
  }

  const row = (label: string, value: ReactNode) => (
    <div className="jury-row" key={label}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );

  return (
    <aside className="jury">
      <div className="jury-head">
        <strong>Under the hood</strong>
        <div style={{ display: 'flex', gap: 6 }}>
          <button type="button" className="btn sm" onClick={() => void refresh()}>
            Refresh
          </button>
          <button type="button" className="btn sm" onClick={() => setOpen(false)}>
            Close <kbd>d</kbd>
          </button>
        </div>
      </div>

      {error && <div className="phys-error">{error}</div>}
      {!data && !error && <div className="source-empty">Reading…</div>}

      {data && (
        <div className="jury-body">
          <div className="jury-section">State machine</div>
          {row('current node', <code>{data.stateMachine.currentNode}</code>)}
          {row('turns taken', data.stateMachine.turnsTaken)}
          {row('questions open', data.stateMachine.askable)}
          {row('declined', data.stateMachine.declined)}
          {row('degraded to touch', data.stateMachine.degradedToTouch)}
          <p className="jury-note">{data.stateMachine.note}</p>

          <div className="jury-section">Facts and provenance</div>
          {row('active facts', data.facts.active)}
          {row('superseded, kept', data.facts.superseded)}
          {Object.entries(data.facts.byTier).map(([tier, count]) => row(`· ${tier}`, count))}
          {row('absences recorded', data.facts.absences)}
          {row(
            'facts with no source',
            <strong style={{ color: data.facts.withoutSource ? 'var(--danger)' : 'var(--ok)' }}>
              {data.facts.withoutSource}
            </strong>,
          )}

          <div className="jury-section">Red flags</div>
          {row('rules evaluated', data.redFlags.rulesEvaluated)}
          {row('fired', data.redFlags.fired.length ? data.redFlags.fired.join(', ') : 'none')}
          {row(
            'priority',
            <span className={`badge ${data.redFlags.priority}`}>{data.redFlags.priority}</span>,
          )}
          <p className="jury-note">{data.redFlags.note}</p>

          <div className="jury-section">Conflicts and consent</div>
          {row('contradictions open', data.contradictions)}
          {row('consent scopes', data.consent.scopes.join(', ') || 'none')}

          <div className="jury-section">Backends actually running</div>
          {row(
            'extraction',
            `${data.backends.llm.name}${data.backends.llm.offline ? ' (offline)' : ''}`,
          )}
          {row(
            'speech',
            `${data.backends.speech.name}${data.backends.speech.offline ? ' (offline)' : ''}`,
          )}
          {row('ocr', data.backends.ocr)}

          <div className="jury-section">Audit</div>
          {row(
            'hash chain',
            <strong style={{ color: data.audit.intact ? 'var(--ok)' : 'var(--danger)' }}>
              {data.audit.intact ? 'VALID' : 'BROKEN'}
            </strong>,
          )}
          {row('events', data.audit.events)}
          {row('this query took', `${data.inspectLatencyMs} ms`)}
        </div>
      )}
    </aside>
  );
}

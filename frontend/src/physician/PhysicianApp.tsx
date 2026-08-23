/**
 * The physician review surface.
 *
 * Keyboard-first, because a physician with 2–5 minutes per patient does not reach for a
 * mouse: 1–9 jumps to a queue entry, j/k moves through summary lines, s re-reads the source,
 * ⌘↵ commits. The whole review is doable without touching the trackpad.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  api,
  type QueueEntry,
  type Summary,
  type TimelinePeriod,
} from '../shared/api';
import { CommitBar } from './CommitBar';
import { QueueList } from './QueueList';
import { RedFlagBanner } from './RedFlagBanner';
import { SourcePanel } from './SourcePanel';
import { StaffLogin } from './StaffLogin';
import { SummaryPane } from './SummaryPane';
import { TimelineView } from './TimelineView';
import { VerificationLane, type PendingEntity } from './VerificationLane';

type SidePanel = 'source' | 'timeline' | 'verify';

export function PhysicianApp(): JSX.Element {
  const [role, setRole] = useState<string | null>(null);
  const [actor, setActor] = useState('');
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [periods, setPeriods] = useState<TimelinePeriod[]>([]);
  const [pending, setPending] = useState<PendingEntity[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [panel, setPanel] = useState<SidePanel>('source');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState<{ bundleId: string; entries: number; hisStatus: string } | null>(null);

  const refreshQueue = useCallback(async () => {
    try {
      const result = await api.queue();
      setQueue(result.queue);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not load the queue.');
    }
  }, []);

  useEffect(() => {
    if (!role) return;
    void refreshQueue();
    const timer = setInterval(() => void refreshQueue(), 8000);
    return () => clearInterval(timer);
  }, [role, refreshQueue]);

  const open = useCallback(async (ref: string) => {
    setBusy(true);
    setError(null);
    setActiveRef(ref);
    setSelected(null);
    setReviewed(false);
    setCommitted(null);
    setPanel('source');
    try {
      const [loaded, timeline] = await Promise.all([api.summary(ref), api.timeline(ref)]);
      setSummary(loaded);
      setPeriods(timeline.periods);
      setPending([]);
    } catch (exc) {
      setSummary(null);
      setError(exc instanceof ApiError ? exc.message : 'Could not load this session.');
    } finally {
      setBusy(false);
    }
  }, []);

  const commit = useCallback(async () => {
    if (!activeRef) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.commit(activeRef);
      setCommitted({
        bundleId: result.bundleId,
        entries: result.entries,
        hisStatus: result.hisPush.status,
      });
      await refreshQueue();
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Commit failed.');
    } finally {
      setBusy(false);
    }
  }, [activeRef, refreshQueue]);

  // --- keyboard ------------------------------------------------------------
  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;

      if (event.key >= '1' && event.key <= '9') {
        const entry = queue[Number(event.key) - 1];
        if (entry) void open(entry.sessionRef);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        if (reviewed && !committed) void commit();
        return;
      }
      if (!summary) return;

      const factIndexes = summary.lines
        .map((line, index) => (line.kind === 'fact' && line.sources.length ? index : -1))
        .filter((index) => index >= 0);
      if (!factIndexes.length) return;

      if (event.key === 'j' || event.key === 'ArrowDown') {
        event.preventDefault();
        const position = selected === null ? -1 : factIndexes.indexOf(selected);
        const next = factIndexes[Math.min(position + 1, factIndexes.length - 1)];
        setSelected(next);
        if (next === factIndexes[factIndexes.length - 1]) setReviewed(true);
        document.querySelector(`[data-index="${next}"]`)?.scrollIntoView({ block: 'nearest' });
      }
      if (event.key === 'k' || event.key === 'ArrowUp') {
        event.preventDefault();
        const position = selected === null ? factIndexes.length : factIndexes.indexOf(selected);
        const next = factIndexes[Math.max(position - 1, 0)];
        setSelected(next);
        document.querySelector(`[data-index="${next}"]`)?.scrollIntoView({ block: 'nearest' });
      }
      if (event.key === 's') setPanel('source');
      if (event.key === 't') setPanel('timeline');
      if (event.key === 'v') setPanel('verify');
    }

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [queue, summary, selected, reviewed, committed, open, commit]);

  // Scrolling to the bottom of the summary counts as having read it.
  function onScroll(event: React.UIEvent<HTMLElement>): void {
    const el = event.currentTarget;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) setReviewed(true);
  }

  if (!role) {
    return (
      <StaffLogin
        onSignedIn={(signedRole, signedActor) => {
          setRole(signedRole);
          setActor(signedActor);
        }}
      />
    );
  }

  const selectedLine = selected !== null ? summary?.lines[selected] ?? null : null;

  return (
    <div className="phys">
      <header className="phys-top">
        <span className="phys-brand">MediKiosk</span>
        <span style={{ opacity: 0.7 }}>physician review</span>
        <span className="phys-top-spacer" />
        <span style={{ opacity: 0.75 }}>
          <kbd>1-9</kbd> patient · <kbd>j</kbd>/<kbd>k</kbd> line · <kbd>s</kbd>/<kbd>t</kbd>/
          <kbd>v</kbd> panel · <kbd>⌘↵</kbd> commit
        </span>
        <span style={{ opacity: 0.9 }}>
          {actor} · {role}
        </span>
      </header>

      <aside className="phys-queue">
        <QueueList entries={queue} activeRef={activeRef} onSelect={(ref) => void open(ref)} />
      </aside>

      <main className="phys-main" onScroll={onScroll}>
        {error && <div className="phys-error">{error}</div>}

        {!summary && !error && (
          <div className="source-empty">
            Select a patient from the queue, or press <kbd>1</kbd>–<kbd>9</kbd>.
          </div>
        )}

        {summary && (
          <>
            <div className="phys-notice">{summary.notice}</div>
            <RedFlagBanner
              escalation={summary.escalation}
              onSelectFlag={(factIds) => {
                const index = summary.lines.findIndex((line) =>
                  line.sources.some((source) => factIds.includes(source.factId)),
                );
                if (index >= 0) {
                  setSelected(index);
                  setPanel('source');
                  document.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: 'center' });
                }
              }}
            />
            <SummaryPane
              lines={summary.lines}
              selectedIndex={selected}
              onSelect={(index) => {
                setSelected(index);
                setPanel('source');
              }}
            />
          </>
        )}
      </main>

      <aside className="phys-side">
        <div style={{ display: 'flex', gap: 5, marginBottom: 12 }}>
          <button
            type="button"
            className={`btn sm${panel === 'source' ? ' primary' : ''}`}
            onClick={() => setPanel('source')}
          >
            Source <kbd>s</kbd>
          </button>
          <button
            type="button"
            className={`btn sm${panel === 'timeline' ? ' primary' : ''}`}
            onClick={() => setPanel('timeline')}
          >
            Timeline <kbd>t</kbd>
          </button>
          <button
            type="button"
            className={`btn sm${panel === 'verify' ? ' primary' : ''}`}
            onClick={() => setPanel('verify')}
          >
            Verify <kbd>v</kbd>
            {pending.length > 0 && ` (${pending.length})`}
          </button>
        </div>

        {panel === 'source' && (
          <SourcePanel sources={selectedLine?.sources ?? []} lineText={selectedLine?.text ?? null} />
        )}
        {panel === 'timeline' && <TimelineView periods={periods} />}
        {panel === 'verify' && (
          <VerificationLane
            pending={pending}
            busy={busy}
            onDecide={async (entity, accepted, correctedText) => {
              if (!activeRef) return;
              setBusy(true);
              try {
                await api.verifyEntity(
                  activeRef,
                  entity.documentId,
                  entity.entityIndex,
                  accepted,
                  correctedText,
                );
                setPending((current) =>
                  current.filter((item) => item.entityIndex !== entity.entityIndex),
                );
                await open(activeRef);
              } catch (exc) {
                setError(exc instanceof ApiError ? exc.message : 'Verification failed.');
              } finally {
                setBusy(false);
              }
            }}
          />
        )}
      </aside>

      <footer className="phys-bottom">
        {summary ? (
          <CommitBar
            status={summary.status}
            traceable={summary.traceability.ok}
            completeness={summary.completeness}
            reviewed={reviewed}
            busy={busy}
            committed={committed}
            onCommit={() => void commit()}
          />
        ) : (
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>No patient selected.</span>
        )}
      </footer>
    </div>
  );
}

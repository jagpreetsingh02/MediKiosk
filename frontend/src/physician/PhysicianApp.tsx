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
  type ExtractedItem,
  type PatientContext,
  type QueueEntry,
  type SessionDocument,
  type Summary,
  type TimelinePeriod,
} from '../shared/api';
import { JuryDrawer } from '../shared/JuryDrawer';
import { CommitBar } from './CommitBar';
import { ContradictionPanel } from './ContradictionPanel';
import { CurrentVsHistory } from './CurrentVsHistory';
import { EvidenceDrawer } from './EvidenceDrawer';
import { LongitudinalTimeline } from './LongitudinalTimeline';
import { MedicationHistory } from './MedicationHistory';
import { SimilarEncounters } from './SimilarEncounters';
import { QueueList } from './QueueList';
import { RedFlagBanner } from './RedFlagBanner';
import { SourcePanel } from './SourcePanel';
import { StaffLogin } from './StaffLogin';
import { SummaryPane } from './SummaryPane';
import { TimelineView } from './TimelineView';
import { VerificationLane, type PendingEntity } from './VerificationLane';

type SidePanel = 'source' | 'timeline' | 'verify' | 'conflicts';

/**
 * The main column is no longer only the draft. A physician reviewing a returning patient
 * needs the record, not just today's answers, and §23 is explicit that the summary becomes
 * one view inside clinical memory rather than the product itself.
 */
type MainView = 'visit' | 'timeline' | 'medications' | 'similar' | 'documents';

const MAIN_VIEWS: { id: MainView; label: string }[] = [
  { id: 'visit', label: 'Current visit' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'medications', label: 'Medications' },
  { id: 'similar', label: 'Similar visits' },
  { id: 'documents', label: 'Documents' },
];

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
  const [view, setView] = useState<MainView>('visit');
  const [context, setContext] = useState<PatientContext | null>(null);
  const [documents, setDocuments] = useState<SessionDocument[]>([]);
  const [evidence, setEvidence] = useState<{
    documentId: string;
    label: string;
    item: ExtractedItem | null;
  } | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState<{ bundleId: string; entries: number; hisStatus: string } | null>(null);
  /** Set once, from ?session= — the demo launcher links straight to a loaded case. */
  const [deepLink] = useState(() => new URLSearchParams(window.location.search).get('session'));

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

  // ?session=… arrives from the demo launcher. Open it without making the judge hunt the
  // queue for a session ref they have never seen.
  useEffect(() => {
    if (role && deepLink && !activeRef) void open(deepLink);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, deepLink]);

  const open = useCallback(async (ref: string) => {
    setBusy(true);
    setError(null);
    setActiveRef(ref);
    setSelected(null);
    setReviewed(false);
    setCommitted(null);
    setPanel('source');
    setView('visit');
    setContext(null);
    setDocuments([]);
    setEvidence(null);
    try {
      // Sequential, not Promise.all: if the session is gone the summary already says so, and
      // firing the timeline anyway only puts a second failed request in the console.
      const loaded = await api.summary(ref);
      setSummary(loaded);
      setPeriods((await api.timeline(ref)).periods);

      // The verification lane was being handed an empty array on every open — there was no
      // route to fetch pending entities from, so the panel could never show anything.
      const listed = (await api.sessionDocuments(ref)).documents;
      setDocuments(listed);
      setPending(
        listed.flatMap((document) =>
          document.extracted
            .filter((item) => item.pending && !item.patientReview)
            .map((item) => ({
              documentId: document.documentId,
              entityIndex: item.entityIndex as number,
              kind: item.kind,
              text: item.text,
              confidence: item.confidence,
              sourceText: item.sourceText,
              page: item.page,
            })),
        ),
      );

      // History is a separate request on purpose: a patient with no record is a normal
      // outcome, and it must not take the draft down with it.
      try {
        setContext(await api.patientContext(ref));
      } catch {
        setContext(null);
      }
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
      if (event.key === 'c') setPanel('conflicts');
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
  const conflicts = summary?.history.contradictions ?? [];

  /**
   * Open the original page behind a document-derived claim. The documentRef may name a
   * document from THIS session or one promoted at an earlier visit, and the two live behind
   * different routes; the session's own documents are checked first because that is where a
   * physician mid-review is looking.
   */
  function showOriginal(documentRef: string, item: ExtractedItem | null = null): void {
    if (!activeRef) return;
    const local = documents.find((document) => document.documentId === documentRef);
    if (local) {
      setEvidence({
        documentId: documentRef,
        label: local.filename,
        item: item ?? local.extracted.find((entry) => entry.sourceText) ?? null,
      });
      return;
    }
    setEvidence({
      documentId: documentRef,
      label: 'Previously uploaded record',
      item,
    });
  }

  /**
   * Always the rendered page, never the raw file. A bounding box is in normalised page
   * coordinates: it can be drawn precisely over an image and not at all over the browser's
   * own PDF viewer, which picks its own scale and offset.
   */
  function evidenceUrl(documentId: string, page: number): string {
    const local = documents.some((document) => document.documentId === documentId);
    if (local && activeRef) return api.sessionDocumentFileUrl(activeRef, documentId, page);
    return context?.patientRef
      ? api.documentFileUrl(context.patientRef, documentId, page)
      : '';
  }

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

        {summary && context?.known && context.overview && (
          <div className="phys-patient">
            <div className="phys-patient-id">
              <strong>{context.overview.displayName ?? 'Patient'}</strong>
              <span>ABHA {context.overview.abhaMasked}</span>
              {context.overview.ageYears && <span>{context.overview.ageYears} yrs</span>}
              {context.overview.gender && <span>{context.overview.gender}</span>}
            </div>
            <div className="phys-patient-counts">
              <span>{context.overview.counts.encounters} previous visits</span>
              <span>{context.overview.counts.prescriptions} prescriptions</span>
              <span>{context.overview.counts.labReports} lab reports</span>
            </div>
          </div>
        )}

        {summary && context && !context.known && (
          <div className="phys-patient first">
            First recorded visit for this patient — no prior history on file.
          </div>
        )}

        {summary && context?.reconciliation?.length ? (
          <div className="phys-rec">
            {context.reconciliation.map((finding, index) => (
              <div key={`${finding.kind}-${index}`} className="phys-rec-row">
                <div className="phys-rec-status">{finding.status}</div>
                <div className="phys-rec-current">{finding.currentStatement}</div>
                <div className="phys-rec-hist">
                  {finding.historicalEvidence.map((evidenceItem) => (
                    <span key={evidenceItem.name}>
                      {evidenceItem.name}
                      {evidenceItem.mentions[0]?.observedOn
                        ? ` · ${evidenceItem.mentions[0].observedOn}`
                        : ''}
                    </span>
                  ))}
                </div>
                <p className="phys-rec-note">{finding.note}</p>
              </div>
            ))}
          </div>
        ) : null}

        {summary && (
          <RedFlagBanner
            escalation={summary.escalation}
            onSelectFlag={(factIds) => {
              const index = summary.lines.findIndex((line) =>
                line.sources.some((source) => factIds.includes(source.factId)),
              );
              if (index >= 0) {
                setView('visit');
                setSelected(index);
                setPanel('source');
                document.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: 'center' });
              }
            }}
          />
        )}

        {summary && context?.known && (
          <nav className="phys-views">
            {MAIN_VIEWS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                className={`btn sm${view === entry.id ? ' primary' : ''}`}
                onClick={() => setView(entry.id)}
              >
                {entry.label}
                {entry.id === 'similar' && context.similar.length
                  ? ` (${context.similar.length})`
                  : ''}
              </button>
            ))}
          </nav>
        )}

        {summary && view === 'timeline' && context && (
          <LongitudinalTimeline events={context.timeline} onOpenDocument={showOriginal} />
        )}
        {summary && view === 'medications' && context && (
          <MedicationHistory medications={context.medications} onOpenDocument={showOriginal} />
        )}
        {summary && view === 'similar' && context && (
          <SimilarEncounters
            similar={context.similar}
            onOpenEncounter={() => setView('timeline')}
          />
        )}
        {summary && view === 'documents' && (
          <div className="lt">
            {documents.length === 0 && (
              <div className="source-empty">No documents uploaded in this visit.</div>
            )}
            {documents.map((document) => (
              <section key={document.documentId} className="lt-year">
                <h3 className="lt-year-label">{document.filename}</h3>
                {document.extracted.map((item) => (
                  <article
                    key={item.itemId}
                    className={`lt-row${item.confidenceBand === 'verify' ? ' unsure' : ''}`}
                  >
                    <div className="lt-date">{item.kind}</div>
                    <div className="lt-body">
                      <div className="lt-label">{item.text}</div>
                      <div className="lt-detail">{item.sourceText}</div>
                      {item.patientDisputed && (
                        <div className="lt-flag">the patient does not agree with this line</div>
                      )}
                      <button
                        type="button"
                        className="lt-source"
                        onClick={() => showOriginal(document.documentId, item)}
                      >
                        Show the original
                      </button>
                    </div>
                  </article>
                ))}
              </section>
            ))}
          </div>
        )}

        {summary && view === 'visit' && (
          <>
            <div className="phys-notice">{summary.notice}</div>
            {context && (
              <CurrentVsHistory context={context} onOpenEncounter={() => setView('similar')} />
            )}
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
          <button
            type="button"
            className={`btn sm${panel === 'conflicts' ? ' primary' : ''}`}
            onClick={() => setPanel('conflicts')}
          >
            Conflicts <kbd>c</kbd>
            {conflicts.length > 0 && ` (${conflicts.length})`}
          </button>
        </div>

        {panel === 'source' && (
          <SourcePanel
            sources={selectedLine?.sources ?? []}
            lineText={selectedLine?.text ?? null}
            onShowOriginal={(documentId, source) =>
              showOriginal(documentId, {
                itemId: `source:${source.factId}`,
                kind: 'source',
                text: source.verbatim,
                page: source.page ?? 1,
                confidence: source.confidence,
                confidenceBand: 'high',
                pending: false,
                handwritten: Boolean(source.handwritten),
                sourceText: source.verbatim,
                bbox: source.bbox ?? { x: 0, y: 0, width: 1, height: 1 },
                detail: {},
                observedOn: null,
              })
            }
          />
        )}
        {panel === 'timeline' && <TimelineView periods={periods} />}
        {panel === 'conflicts' && (
          <ContradictionPanel
            contradictions={conflicts}
            onSelectFact={factId => {
              const index = summary?.lines.findIndex(line =>
                line.sources.some(source => source.factId === factId),
              );
              if (index !== undefined && index >= 0) {
                setSelected(index);
                setPanel('source');
                document.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: 'center' });
              }
            }}
          />
        )}
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

      {evidence && (
        <EvidenceDrawer
          fileUrl={evidenceUrl(evidence.documentId, evidence.item?.page ?? 1)}
          item={evidence.item}
          documentLabel={evidence.label}
          onClose={() => setEvidence(null)}
        />
      )}

      <JuryDrawer sessionRef={activeRef} />

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

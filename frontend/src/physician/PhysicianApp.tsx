/**
 * The doctor's workspace — the whole of it, and nothing that is not theirs.
 *
 * Reached from the Doctor door on the front screen (`/doctor`, and `/physician` which is the
 * original path kept alive for the demo launcher's `?session=` deep links). Everything a
 * doctor does with this system is here and only here:
 *
 *   who is waiting        the queue, priority-ordered by the server         QueueList
 *   who is next           the head of that queue, said rather than implied  NextPatient
 *   their prepared report the clinical brief, assembled deterministically   ClinicalReport
 *   today's intake        the draft summary, line by line, with sources     SummaryPane
 *   their whole record    timeline, medications, past visits, documents     record/, Similar…
 *   adding a document     the same OCR front door the kiosk posts to        DocumentIntake
 *   verifying and         the lane, the conflicts panel, and the commit —
 *   committing            Invariant 4 lives at the bottom of this screen    CommitBar
 *
 * ⛔ NOTHING FROM THE PATIENT'S WORKSPACE APPEARS HERE, and structurally: this folder never
 * imports from `patient/` or `kiosk/`. The three views both roles genuinely need live in
 * `record/`, owned by neither. `tests/test_role_separation.py` fails the build if that
 * changes. See ADR-0016.
 *
 * Keyboard-first, because a physician with 2–5 minutes per patient does not reach for a
 * mouse: 1–9 jumps to a queue entry, j/k moves through summary lines, s re-reads the source,
 * ⌘↵ commits. The whole review is doable without touching the trackpad.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
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
import { AppNav } from '../design/AppNav';
import { useSummaryReviewed } from './useSummaryReviewed';
import { JuryDrawer } from '../shared/JuryDrawer';
import { CommitBar } from './CommitBar';
import { ContradictionPanel } from './ContradictionPanel';
import { CurrentVsHistory } from './CurrentVsHistory';
import { EvidenceDrawer } from '../record/EvidenceDrawer';
import { ClinicalReport } from './ClinicalReport';
import { DocumentIntake } from './DocumentIntake';
import { NextPatient } from './NextPatient';
import { LongitudinalTimeline } from '../record/LongitudinalTimeline';
import { MedicationHistory } from '../record/MedicationHistory';
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
type MainView = 'brief' | 'visit' | 'timeline' | 'medications' | 'similar' | 'documents';

const MAIN_VIEWS: { id: MainView; label: string; title?: string }[] = [
  // First, and the default: the brief is the answer to "what did we get back for
  // all that input". Everything after it is a way of drilling into one part of it.
  { id: 'brief', label: 'Clinical brief' },
  { id: 'visit', label: 'Current visit' },
  {
    id: 'timeline',
    label: 'Timeline',
    // Distinct from the side panel's "Uploads" tab, which is only today's documents — this
    // is the patient's whole record, and the two used to share the name "Timeline".
    title: "The patient's whole record across every past visit, not just this session",
  },
  { id: 'medications', label: 'Medications' },
  { id: 'similar', label: 'Similar visits' },
  {
    id: 'documents',
    label: 'Documents',
    // THIS visit's papers, and where a new one is added. Documents from earlier visits are
    // on the Timeline, filtered to Documents — the same distinction the side panel's
    // "Timeline" tab draws, and worth naming here for the same reason.
    title: "Papers uploaded during this visit, and where to add another. Earlier papers are on the Timeline.",
  },
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
  /** Both default open — these hide chrome that is useful sometimes, not chrome that should
   *  start hidden. A judge or a physician sees the same screen either way until they choose
   *  to simplify it. */
  const [queueVisible, setQueueVisible] = useState(true);
  const [juryVisible, setJuryVisible] = useState(true);
  const [sideVisible, setSideVisible] = useState(true);
  const [context, setContext] = useState<PatientContext | null>(null);
  const [documents, setDocuments] = useState<SessionDocument[]>([]);
  const [evidence, setEvidence] = useState<{
    documentId: string;
    label: string;
    item: ExtractedItem | null;
  } | null>(null);
  /** The physician's attestation — the actual arming condition for commit. Reaching the end
   *  of the summary is a separate, measured signal (`reachedEnd`) that gates the checkbox.
   *  See CommitBar and useSummaryReviewed for why scroll position is not sufficient. */
  const [attested, setAttested] = useState(false);
  const { containerRef, sentinelRef, reachedEnd, reset: resetReview } = useSummaryReviewed();
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
    setAttested(false);
    resetReview();
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
        if (attested && !committed) void commit();
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
        // Traversing to the last line no longer *asserts* a review — the IntersectionObserver
        // reports whether the end is genuinely on screen, and the physician still attests.
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
  }, [queue, summary, selected, attested, committed, open, commit]);

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
    // A document reached from the clinical brief belongs to a PAST encounter, so there
    // is no live session behind it. Requiring one here made every historical lab report
    // unopenable from the brief — the evidence drawer simply did nothing.
    if (!activeRef && !context?.patientRef) return;
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
    // `data-surface="clinical"` selects the dense scale in design/tokens.css —
    // smaller targets, smaller reading sizes, tighter gutters. It no longer
    // changes a single colour: this surface and the kiosk share one ground and
    // one material, and differ only in how much of the record fits on screen.
    <div
      className="phys"
      data-surface="clinical"
      data-queue-hidden={!queueVisible}
      data-side-hidden={!sideVisible}
    >
      {/* The same bar the hero wears, at clinical density. A physician arriving
          from the landing page keeps the mark, the material and the centre pill;
          only what the pill contains is theirs rather than the patient's. */}
      <AppNav
        dense
        context="Doctor workspace"
        center={
          summary && context?.known ? (
            <nav className="phys-views" aria-label="Record views">
              {MAIN_VIEWS.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  className={view === entry.id ? 'active' : undefined}
                  aria-selected={view === entry.id}
                  onClick={() => setView(entry.id)}
                  title={entry.title}
                >
                  {entry.label}
                  {entry.id === 'similar' && context.similar.length
                    ? ` (${context.similar.length})`
                    : ''}
                </button>
              ))}
            </nav>
          ) : undefined
        }
        actions={
          <>
            <Link to="/" className="btn sm" title="Back to home">
              ← Home
            </Link>
            <button
              type="button"
              className={`btn sm${queueVisible ? ' primary' : ''}`}
              aria-pressed={queueVisible}
              onClick={() => setQueueVisible((current) => !current)}
              title="Show or hide the patient queue"
            >
              {queueVisible ? 'Hide queue' : 'Show queue'}
            </button>
            <button
              type="button"
              className={`btn sm${juryVisible ? ' primary' : ''}`}
              aria-pressed={juryVisible}
              onClick={() => setJuryVisible((current) => !current)}
              title="Show or hide the engineering detail panel"
            >
              {juryVisible ? 'Hide jury view' : 'Show jury view'}
            </button>
            <button
              type="button"
              className={`btn sm${sideVisible ? ' primary' : ''}`}
              aria-pressed={sideVisible}
              onClick={() => setSideVisible((current) => !current)}
              title="Show or hide the source, timeline, verify and conflicts panel"
            >
              {sideVisible ? 'Hide side panel' : 'Show side panel'}
            </button>
            <button
              type="button"
              className="btn sm"
              title={
                '1-9 opens a queued patient · j/k moves between summary lines\n' +
                's/t/v/c switches the side panel · ⌘/Ctrl+Enter commits'
              }
            >
              Shortcuts
            </button>
            <span className="phys-actor">
              {actor} · {role}
            </span>
          </>
        }
      />

      {queueVisible && (
        <aside className="phys-queue">
          <QueueList entries={queue} activeRef={activeRef} onSelect={(ref) => void open(ref)} />
        </aside>
      )}

      <main className="phys-main" ref={containerRef}>
        {error && <div className="phys-error">{error}</div>}

        {/* Not "select a patient" — the queue is already ordered, so the screen says who.
            Still reachable by 1–9 and by the sidebar; this only stops the doctor having to
            work the ordering out for themselves. */}
        {!summary && !error && (
          <NextPatient entries={queue} onOpen={(ref) => void open(ref)} />
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
          // Collapsed by default — the finding is real and worth surfacing, but not worth
          // pushing the actual summary (what the physician is here to read) further down the
          // screen for every patient who has one.
          <details className="phys-rec">
            <summary className="phys-rec-summary">
              Needs medication reconciliation · {context.reconciliation.length}{' '}
              {context.reconciliation.length === 1 ? 'finding' : 'findings'}
            </summary>
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
          </details>
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

        {view === 'brief' && context?.patientRef && (
          <ClinicalReport
            patientRef={context.patientRef}
            onOpenDocument={(documentRef) => documentRef && showOriginal(documentRef)}
          />
        )}

        {view === 'brief' && !context?.patientRef && (
          <div className="source-empty">
            This session has no durable patient record yet. The brief appears once a
            physician has confirmed an encounter for this patient.
          </div>
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
        {/* A paper handed across the desk, or one that arrived after the intake ended.
            Same route, same pipeline, same verification lane — see DocumentIntake. */}
        {summary && view === 'documents' && activeRef && (
          <DocumentIntake sessionRef={activeRef} onUploaded={() => open(activeRef)} />
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

        {/* The end of the record. The IntersectionObserver in `useSummaryReviewed` watches
            this, which is what makes "the physician reached the end" a measured fact rather
            than an inference from scroll position. It is inside the scrolling column and
            after every view's content, so it works for the brief and the timeline too — not
            only the visit summary. Zero height and aria-hidden: it is an instrument, not
            content, and a screen reader has no use for it. */}
        <div ref={sentinelRef} className="phys-end-sentinel" aria-hidden="true" />
      </main>

      {sideVisible && (
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
            title="Documents uploaded during this visit, organised by their own dates"
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
      )}

      {evidence && (
        <EvidenceDrawer
          fileUrl={evidenceUrl(evidence.documentId, evidence.item?.page ?? 1)}
          item={evidence.item}
          documentLabel={evidence.label}
          onClose={() => setEvidence(null)}
        />
      )}

      {juryVisible && <JuryDrawer sessionRef={activeRef} />}

      <footer className="phys-bottom">
        {summary ? (
          <CommitBar
            status={summary.status}
            traceable={summary.traceability.ok}
            completeness={summary.completeness}
            reachedEnd={reachedEnd}
            attested={attested}
            onAttest={setAttested}
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

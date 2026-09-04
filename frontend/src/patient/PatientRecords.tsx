/**
 * The patient's papers: what has already been read, and how to add another.
 *
 * TWO HALVES, AND THE ORDER IS THE POINT. What is already on file comes first, because the
 * question a returning patient opens this tab with is "did my prescription actually get
 * saved?", not "let me upload something". The add-a-record panel is underneath it — until a
 * paper is actually being read, at which point the upload takes the whole tab, because its
 * readback is a question the patient has to answer and it must not open below the fold.
 *
 * ⛔ THIS SCREEN INVENTS NO STORAGE. There is no patient-side document store in this system
 * and this tab does not pretend there is one. A paper becomes part of the record exactly one
 * way — it is read during a visit, and a physician confirms that visit — which is Invariant 2
 * and Invariant 4 doing their job, not a limitation to be routed around in the UI. So:
 *
 *   the list      reads the patient's OWN durable timeline and shows the rows that came off
 *                 a document, which is precisely the set of papers that made it in
 *
 *   adding one    opens a real intake session with the `documents` permission and runs the
 *                 SAME upload component the kiosk runs, against the SAME route. The doctor
 *                 then sees it in their list. Nothing here is a second pipeline.
 *
 * The copy says all of that in the patient's own words, before they upload rather than after,
 * because "your paper is waiting for the doctor" and "your paper is on your record" are
 * different promises and only one of them is true at the moment the upload finishes.
 */
import { useState } from 'react';
import { ApiError, api, type TimelineRow } from '../shared/api';
import { DocumentUpload } from '../kiosk/DocumentUpload';
import { Icon } from '../shared/Icon';

interface Props {
  /** Every event on the patient's record. Filtered here rather than refetched. */
  events: TimelineRow[] | null;
  /** The language of their last visit, so a new session is not silently English. */
  language: string;
  onOpenDocument: (documentRef: string, label: string) => void;
  /** An upload run finished — the shell drops its cached timeline and reloads. */
  onUploaded: () => void;
}

interface Paper {
  documentRef: string;
  occurredOn: string | null;
  rows: TimelineRow[];
}

/** One card per document, newest first, each holding everything read off that page. */
function group(events: TimelineRow[]): Paper[] {
  const papers = new Map<string, Paper>();
  for (const event of events) {
    if (!event.documentRef) continue;
    const found = papers.get(event.documentRef);
    if (found) {
      found.rows.push(event);
      // The earliest date on the page is the page's own date — a prescription carries the
      // day it was written, and the lines on it inherit that rather than the day we read it.
      if (event.occurredOn && (!found.occurredOn || event.occurredOn < found.occurredOn)) {
        found.occurredOn = event.occurredOn;
      }
    } else {
      papers.set(event.documentRef, {
        documentRef: event.documentRef,
        occurredOn: event.occurredOn,
        rows: [event],
      });
    }
  }
  return [...papers.values()].sort((a, b) => (b.occurredOn ?? '').localeCompare(a.occurredOn ?? ''));
}

export function PatientRecords({
  events,
  language,
  onOpenDocument,
  onUploaded,
}: Props): JSX.Element {
  /** The session an upload runs against. Null until the patient asks to add something. */
  const [sessionRef, setSessionRef] = useState<string | null>(null);
  const [scoped, setScoped] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState(0);

  async function startAdding(): Promise<void> {
    setStarting(true);
    setError(null);
    try {
      // `history` is a required scope — a session cannot exist without it — and `documents`
      // is the one this screen is actually for. Both are named here rather than assumed, so
      // the consent record says exactly what the patient agreed to when they tapped Add.
      const created = await api.createSession(language, ['history', 'documents'], false);
      setSessionRef(created.sessionRef);
      setScoped(true);
    } catch (exc) {
      setError(
        exc instanceof ApiError
          ? exc.message
          : 'We could not start that just now. Please try again in a moment.',
      );
    } finally {
      setStarting(false);
    }
  }

  const papers = events ? group(events) : null;

  return (
    <div className="pp-records">
      {/* While a paper is being read, the upload takes the whole tab. The readback ("is this
          right?") is a question the patient has to answer, and putting it below four cards of
          existing records means it opens off-screen — which is how a question gets ignored. */}
      {!sessionRef && (
        <section className="pp-records__have">
          <h2 className="pp-section-title">Papers already on your record</h2>

          {papers === null && <div className="bx-loading" aria-label="Loading your records" />}

          {papers !== null && papers.length === 0 && (
            <p className="bx-empty">
              No prescriptions or reports have been read into your record yet. If you have papers
              from before, you can add them below.
            </p>
          )}

          {papers !== null && papers.length > 0 && (
            <ol className="pp-papers">
              {papers.map((paper) => (
                <li key={paper.documentRef} className="pp-paper">
                  <div className="pp-paper__when">
                    <strong>{paper.occurredOn ?? 'Undated'}</strong>
                    <span className="kx-footnote">
                      {paper.rows.length} {paper.rows.length === 1 ? 'line' : 'lines'} read from
                      this page
                    </span>
                  </div>

                  <ul className="pp-paper__lines">
                    {paper.rows.map((row) => (
                      <li key={row.eventRef}>
                        <span className="pp-paper__label">{row.label}</span>
                        {row.detail && <span className="pp-paper__detail">{row.detail}</span>}
                        {/* Never softened away. A patient who does not know a reading was
                            unclear cannot ask anyone to look at it again. */}
                        {row.lowConfidence && (
                          <span className="pp-paper__unsure">this line was hard to read</span>
                        )}
                      </li>
                    ))}
                  </ul>

                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() =>
                      onOpenDocument(paper.documentRef, paper.occurredOn ?? 'Your document')
                    }
                  >
                    <Icon name="image" />
                    Show me the paper
                  </button>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}

      <section className="pp-records__add" data-solo={sessionRef ? 'true' : undefined}>
        <h2 className="pp-section-title">Add a prescription or a report</h2>

        {error && <p className="kiosk-error">{error}</p>}

        {!sessionRef && (
          <>
            <p className="kiosk-lead">
              Photograph a paper or choose a file, and we will read it straight away and show
              you what we found.
            </p>
            {/* Said BEFORE the upload, not after it. */}
            <p className="kx-footnote">
              What we read goes to the doctor to check. It joins your record here once a doctor
              has confirmed it — the same as everything else on this screen.
            </p>
            <button
              type="button"
              className="btn-primary"
              onClick={() => void startAdding()}
              disabled={starting}
            >
              {starting ? 'One moment…' : 'Add a paper'}
            </button>
          </>
        )}

        {sessionRef && (
          <DocumentUpload
            sessionRef={sessionRef}
            alreadyUploaded={added}
            consented={scoped}
            onGrantConsent={async () => {
              await api.grantScope(sessionRef, 'documents');
              setScoped(true);
            }}
            onDone={(uploaded) => {
              setAdded(uploaded);
              setSessionRef(null);
              // The new page is not on the record yet — a doctor has to confirm it — so the
              // reload is for anything ELSE that was confirmed since this tab opened, not a
              // promise that what was just uploaded will appear.
              if (uploaded > 0) onUploaded();
            }}
          />
        )}

        {!sessionRef && added > 0 && (
          <p className="pp-records__sent" role="status">
            {added} {added === 1 ? 'paper' : 'papers'} sent to the doctor. You will see it here
            once they have checked it.
          </p>
        )}
      </section>
    </div>
  );
}

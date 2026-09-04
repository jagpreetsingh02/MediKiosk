/**
 * What each visit added to the record, and who signed it off.
 *
 * THE QUESTION THIS ANSWERS is "what changed about what you hold on me, and when?" — which
 * is a different question from "what is on my record" (the Timeline tab) and from "what
 * happened at that visit" (the Visits tab). A record that can only be read as a current
 * state is one the person it is about cannot audit; they can see what it says today and have
 * no way to see it becoming that.
 *
 * DERIVED, NOT FETCHED. Every row here is a join between two things the patient can already
 * read: their confirmed visits (`/encounters`) and their own timeline (`/timeline`), which
 * carries the `encounterRef` that put each event on the record. No new route, no new stored
 * field — the "when did this appear" was already in the data, it had just never been grouped
 * that way.
 *
 * ⛔ ONLY CONFIRMED CHANGES EXIST HERE, and the screen says so rather than implying
 * completeness. An `Encounter` row is written only by `promote()`, off the commit route, so a
 * visit still being written up has not changed the record yet and correctly has nothing to
 * show. That is the honest statement, and it is the one at the bottom of the list.
 */
import { useMemo } from 'react';
import type { TimelineRow } from '../shared/api';

/** The visit shape the workspace already loads. Repeated structurally, not re-fetched. */
export interface ConfirmedVisit {
  encounterRef: string;
  occurredOn: string;
  headline: string | null;
  confirmedBy: string;
  confirmedAt: string | null;
}

interface Props {
  visits: ConfirmedVisit[] | null;
  events: TimelineRow[] | null;
}

/**
 * How many of each kind of thing a visit put on the record.
 *
 * Counted rather than listed at the top of each card, because the useful first glance is
 * "that visit added four things" — the four things themselves are underneath it, and a card
 * that opens with twelve rows of detail is one nobody scans.
 */
function summarise(rows: TimelineRow[]): string {
  const papers = new Set(rows.filter((r) => r.documentRef).map((r) => r.documentRef)).size;
  const parts: string[] = [];
  parts.push(`${rows.length} ${rows.length === 1 ? 'entry' : 'entries'}`);
  if (papers) parts.push(`from ${papers} ${papers === 1 ? 'paper' : 'papers'} you showed us`);
  return parts.join(' · ');
}

export function PatientChanges({ visits, events }: Props): JSX.Element {
  const byVisit = useMemo(() => {
    const groups = new Map<string, TimelineRow[]>();
    for (const event of events ?? []) {
      if (!event.encounterRef) continue;
      const found = groups.get(event.encounterRef);
      if (found) found.push(event);
      else groups.set(event.encounterRef, [event]);
    }
    return groups;
  }, [events]);

  if (visits === null || events === null) {
    return <div className="bx-loading" aria-label="Loading the changes to your record" />;
  }

  if (!visits.length) {
    return (
      <p className="bx-empty">
        Nothing has been added to your record yet. It changes when a doctor confirms a visit.
      </p>
    );
  }

  return (
    <div className="pp-changes">
      <p className="kiosk-lead">
        Every time a doctor confirms a visit, what was agreed that day is added to your record.
        This is that list, newest first.
      </p>

      <ol className="pp-changelist">
        {visits.map((visit) => {
          const rows = byVisit.get(visit.encounterRef) ?? [];
          return (
            <li key={visit.encounterRef} className="pp-change">
              <div className="pp-change__when">
                <strong>{visit.occurredOn}</strong>
                <span className="kx-footnote">Confirmed by {visit.confirmedBy}</span>
              </div>

              <div className="pp-change__what">{visit.headline ?? 'Clinical history'}</div>

              {rows.length === 0 ? (
                // A confirmed visit that put nothing on the longitudinal record is a real
                // outcome — an interview with no documents and no dated findings — and it
                // reads better said than left as an empty card.
                <p className="kx-footnote">
                  This visit was confirmed, and added nothing new to the parts of your record
                  shown on the timeline.
                </p>
              ) : (
                <>
                  <p className="pp-change__count">Added {summarise(rows)}</p>
                  <ul className="pp-change__rows">
                    {rows.map((row) => (
                      <li key={row.eventRef}>
                        <span className="pp-change__label">{row.label}</span>
                        {row.detail && <span className="pp-change__detail">{row.detail}</span>}
                        {row.documentRef && (
                          <span className="pp-change__from">read off a paper you showed us</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </li>
          );
        })}
      </ol>

      <p className="kx-footnote">
        A visit appears here only after a doctor has confirmed it. Anything still being written
        up has not changed your record yet.
      </p>
    </div>
  );
}

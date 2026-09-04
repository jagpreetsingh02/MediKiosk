/**
 * The patient's whole record on one axis, grouped by year — not this session's documents.
 *
 * Every row names where it came from, because a timeline that cannot say why it believes a
 * date is a timeline the physician has to double-check elsewhere, which is worse than not
 * having one. Rows derived from a document open the original.
 *
 * ROLE-NEUTRAL, and in `record/` for that reason: the doctor's workspace and the patient's
 * own record show the SAME rows from the SAME route, at different densities. There is no
 * clinician-only field in this payload to filter out — see ADR-0015 — so there is nothing
 * here that varies by who is reading. ADR-0016 is why it does not live in either role's
 * folder.
 */
import { useMemo, useState } from 'react';
import type { TimelineRow } from '../shared/api';

interface Props {
  events: TimelineRow[];
  onOpenDocument: (documentRef: string) => void;
}

/**
 * The filter set, mapped onto the kinds the promotion step actually writes.
 *
 * These are checked against the emitters in `promote.py` and `seed.py` rather than copied
 * from the brief's wish list: a filter chip for a kind nothing ever emits is a control that
 * is permanently empty, which reads as a broken feature rather than an honest absence. A
 * chip whose kind exists but has no rows for THIS patient is disabled with its count, which
 * is a different and useful statement.
 */
const FILTERS: { id: string; label: string; kinds: string[] | null }[] = [
  { id: 'all', label: 'All', kinds: null },
  { id: 'visits', label: 'Visits', kinds: ['encounter', 'intake'] },
  { id: 'medicines', label: 'Medicines', kinds: ['medication', 'prescription'] },
  { id: 'labs', label: 'Labs', kinds: ['investigation', 'lab_report'] },
  { id: 'diagnoses', label: 'Diagnoses', kinds: ['diagnosis'] },
  { id: 'documents', label: 'Documents', kinds: ['document', 'prescription', 'lab_report'] },
];

export function LongitudinalTimeline({ events, onOpenDocument }: Props): JSX.Element {
  const [filter, setFilter] = useState('all');

  const visible = useMemo(() => {
    const wanted = FILTERS.find((f) => f.id === filter)?.kinds;
    return wanted ? events.filter((e) => wanted.includes(e.kind)) : events;
  }, [events, filter]);

  const byYear = useMemo(() => {
    const groups = new Map<string, TimelineRow[]>();
    for (const event of visible) {
      const year = event.occurredOn ? event.occurredOn.slice(0, 4) : 'Undated';
      if (!groups.has(year)) groups.set(year, []);
      groups.get(year)?.push(event);
    }
    return [...groups.entries()].sort(([a], [b]) => {
      if (a === 'Undated') return 1;
      if (b === 'Undated') return -1;
      return b.localeCompare(a);
    });
  }, [visible]);

  return (
    <div className="lt">
      <div className="lt-filters">
        {FILTERS.map((entry) => {
          const count = entry.kinds
            ? events.filter((e) => entry.kinds?.includes(e.kind)).length
            : events.length;
          return (
            <button
              key={entry.id}
              type="button"
              className={`btn sm${filter === entry.id ? ' primary' : ''}`}
              disabled={count === 0 && entry.id !== 'all'}
              onClick={() => setFilter(entry.id)}
            >
              {entry.label}
              {count > 0 ? ` ${count}` : ''}
            </button>
          );
        })}
      </div>

      {byYear.length === 0 && (
        <div className="source-empty">Nothing on file under this filter.</div>
      )}

      {byYear.map(([year, rows]) => (
        <section key={year} className="lt-year">
          <h3 className="lt-year-label">{year}</h3>
          {rows.map((event) => (
            <article
              key={event.eventRef}
              className={`lt-row${event.lowConfidence ? ' unsure' : ''}`}
            >
              <div className="lt-date">{shortDate(event.occurredOn)}</div>
              <div className="lt-body">
                <div className="lt-kind">{event.kind}</div>
                <div className="lt-label">{event.label}</div>
                {event.detail && <div className="lt-detail">{event.detail}</div>}
                {event.lowConfidence && (
                  <div className="lt-flag">read with low confidence — verified by a human</div>
                )}
                {event.documentRef && (
                  <button
                    type="button"
                    className="lt-source"
                    onClick={() => onOpenDocument(event.documentRef as string)}
                  >
                    Show the original
                  </button>
                )}
              </div>
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}

function shortDate(iso: string | null): string {
  if (!iso) return '—';
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
}

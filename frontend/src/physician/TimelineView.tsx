/**
 * Chronological view of everything extracted from the patient's prior records.
 *
 * Undated events get their own labelled group at the end rather than being dropped. The
 * oldest and most important record is often the one whose date the OCR could not read, and a
 * timeline that silently omits it looks complete while being wrong.
 */
import type { TimelinePeriod } from '../shared/api';

interface Props {
  periods: TimelinePeriod[];
}

export function TimelineView({ periods }: Props): JSX.Element {
  if (!periods.length) {
    return <div className="source-empty">No prior records were uploaded for this patient.</div>;
  }

  return (
    <div>
      {periods.map((period) => (
        <div key={period.period} className="tl-period">
          <div className="tl-period-label">{period.label}</div>
          {period.events.map((event) => (
            <div
              key={event.eventId}
              className={`tl-event${event.lowConfidence ? ' low-confidence' : ''}`}
              title={event.detail ?? undefined}
            >
              <span className="tl-date">
                {event.occurredOn ?? '—'}
                {event.datePrecision === 'year' && '*'}
              </span>
              <span className={`tl-kind ${event.kind}`}>{event.kind.slice(0, 4)}</span>
              <span>
                {event.label}
                {event.detail && (
                  <span style={{ color: 'var(--ink-3)', display: 'block', fontSize: 11.5 }}>
                    {event.detail}
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      ))}
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 8, lineHeight: 1.5 }}>
        * year-precision only. Shaded rows came from a low-confidence scan and need verifying.
      </div>
    </div>
  );
}

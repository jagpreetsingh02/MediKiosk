/**
 * The patient memory screen — the first thing that says MediKiosk already knows this person.
 *
 * It sits between login and consent, and it is the single screen that distinguishes this
 * product from a form: before the patient answers anything, they see the visits,
 * prescriptions and reports already on file. A first-time patient sees an honest empty state
 * instead, which is a different message and deserves different words.
 */
import { useEffect, useState } from 'react';
import { ApiError, api, type PatientOverview } from '../shared/api';
import { Icon } from '../shared/Icon';

interface Props {
  onStartVisit: () => void;
  onBack: () => void;
}

export function PatientHome({ onStartVisit, onBack }: Props): JSX.Element {
  const [record, setRecord] = useState<PatientOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .myRecord()
      .then(setRecord)
      .catch(exc =>
        setError(exc instanceof ApiError ? exc.message : 'Could not load your record.'),
      );
  }, []);

  if (error) {
    return (
      <div className="kiosk-panel">
        <div className="kiosk-error">{error}</div>
        <div className="kiosk-actions">
          <button type="button" className="btn-primary" onClick={onStartVisit}>
            Start today's visit anyway
          </button>
        </div>
      </div>
    );
  }

  if (!record) {
    return <div className="kiosk-panel"><p className="kiosk-lead">Loading your record…</p></div>;
  }

  const { counts } = record;

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">
        {record.known ? 'Welcome back' : 'Welcome'}
      </h1>

      <div className="memory-id">
        <div>
          <div className="memory-name">{record.displayName ?? 'Patient'}</div>
          <div className="memory-meta">
            {record.abhaMasked && <>ABHA {record.abhaMasked}</>}
            {record.ageYears && <> · {record.ageYears} years</>}
            {record.gender && <> · {record.gender}</>}
          </div>
        </div>
      </div>

      {record.known ? (
        <>
          <div className="kiosk-section-label">Your clinical history</div>
          <div className="memory-counts">
            <div className="memory-count">
              <strong>{counts.encounters}</strong>
              <span>previous {counts.encounters === 1 ? 'visit' : 'visits'}</span>
            </div>
            <div className="memory-count">
              <strong>{counts.prescriptions}</strong>
              <span>{counts.prescriptions === 1 ? 'prescription' : 'prescriptions'}</span>
            </div>
            <div className="memory-count">
              <strong>{counts.labReports}</strong>
              <span>{counts.labReports === 1 ? 'laboratory report' : 'laboratory reports'}</span>
            </div>
          </div>

          {record.recent.length > 0 && (
            <>
              <div className="kiosk-section-label" style={{ marginTop: 28 }}>
                Recent history
              </div>
              <div className="memory-list">
                {record.recent.map(entry => (
                  <div key={entry.encounterRef} className="memory-row">
                    <div className="memory-date">{formatDate(entry.occurredOn)}</div>
                    <div className="memory-headline">{entry.headline}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      ) : (
        <p className="kiosk-lead">
          {record.note ?? 'This will be your first visit recorded here.'}
        </p>
      )}

      <div className="kiosk-actions">
        <button type="button" className="btn-primary" onClick={onStartVisit}>
          <Icon name="checkup" />
          Start today's visit
        </button>
        <button type="button" className="btn-quiet" onClick={onBack}>
          Not me
        </button>
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

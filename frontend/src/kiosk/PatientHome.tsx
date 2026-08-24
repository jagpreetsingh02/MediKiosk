/**
 * The patient memory screen — the first thing that says MediKiosk already knows this person.
 *
 * It sits between login and consent, and it is the single screen that distinguishes this
 * product from a form: before the patient answers anything, they see the visits,
 * prescriptions and reports already on file. A first-time patient sees an honest empty state
 * instead, which is a different message and deserves different words.
 *
 * The counts are deliberately large and the history is a real timeline with a spine, because
 * the message is continuity. A list of bordered rows says "records exist"; a spine says "this
 * is one story and today is the next entry in it".
 */
import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ApiError, api, type PatientOverview } from '../shared/api';
import { Icon } from '../shared/Icon';
import { Button, EmptyState, Skeleton } from '../design/ui';
import { reduced, rise, stagger } from '../design/motion';

interface Props {
  onStartVisit: () => void;
  onBack: () => void;
}

export function PatientHome({ onStartVisit, onBack }: Props): JSX.Element {
  const [record, setRecord] = useState<PatientOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prefersReduced = useReducedMotion() ?? false;
  const riseV = reduced(prefersReduced, rise);

  useEffect(() => {
    api
      .myRecord()
      .then(setRecord)
      .catch((exc) =>
        setError(exc instanceof ApiError ? exc.message : 'Could not load your record.'),
      );
  }, []);

  if (error) {
    return (
      <div>
        <EmptyState
          glyph={<Icon name="other" />}
          title="We could not open your record"
          body="Your visit can still go ahead — the doctor will see everything you tell us today."
          action={
            <Button onClick={onStartVisit} size="lg">
              Start today's visit
            </Button>
          }
        />
      </div>
    );
  }

  if (!record) {
    return (
      <div className="mk-stack" style={{ gap: 'var(--mk-space-6)' }} aria-busy="true">
        <span className="mk-sr-only" role="status">
          Loading your record
        </span>
        <Skeleton height={112} radius="var(--mk-radius-xl)" />
        <div className="kx-counts">
          <Skeleton height={104} radius="var(--mk-radius-lg)" />
          <Skeleton height={104} radius="var(--mk-radius-lg)" />
          <Skeleton height={104} radius="var(--mk-radius-lg)" />
        </div>
        <Skeleton height={220} radius="var(--mk-radius-lg)" />
      </div>
    );
  }

  const { counts } = record;
  const initials = (record.displayName ?? 'P')
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');

  return (
    <motion.div variants={stagger(0.06)} initial="hidden" animate="visible">
      <motion.p className="kx-eyebrow" variants={riseV}>
        {record.known ? 'Welcome back' : 'Welcome'}
      </motion.p>

      <motion.div className="kx-identity" variants={riseV}>
        <div className="kx-identity__avatar" aria-hidden="true">
          {initials}
        </div>
        <div style={{ position: 'relative' }}>
          <div className="kx-identity__name">{record.displayName ?? 'Patient'}</div>
          <div className="kx-identity__meta">
            {record.abhaMasked && <>ABHA {record.abhaMasked}</>}
            {record.ageYears != null && <> · {record.ageYears} years</>}
            {record.gender && <> · {record.gender}</>}
          </div>
        </div>
      </motion.div>

      {record.known ? (
        <>
          <motion.h1 className="kx-title" variants={riseV} style={{ marginTop: 'var(--mk-space-10)' }}>
            Your health history is already here
          </motion.h1>

          <motion.div className="kx-counts" variants={riseV} style={{ marginTop: 'var(--mk-space-5)' }}>
            <Count value={counts.encounters} one="previous visit" many="previous visits" />
            <Count value={counts.prescriptions} one="prescription" many="prescriptions" />
            <Count value={counts.labReports} one="laboratory report" many="laboratory reports" />
          </motion.div>

          {record.recent.length > 0 && (
            <motion.div variants={riseV} style={{ marginTop: 'var(--mk-space-10)' }}>
              <p className="kx-eyebrow">Recent history</p>
              <div className="kx-history">
                {record.recent.map((entry) => (
                  <div
                    key={entry.encounterRef}
                    className="kx-history__row"
                    data-kind={entry.headline?.toLowerCase().includes('prescription')
                      ? 'prescription'
                      : 'encounter'}
                  >
                    <span className="kx-history__date">{formatDate(entry.occurredOn)}</span>
                    <span className="kx-history__label">{entry.headline}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </>
      ) : (
        <motion.div variants={riseV} style={{ marginTop: 'var(--mk-space-8)' }}>
          <EmptyState
            glyph={<Icon name="checkup" />}
            title="This will be your first visit here"
            body={
              record.note ??
              'After today, everything you and your doctor confirm stays on file — so your next visit starts from what is already known.'
            }
          />
        </motion.div>
      )}

      <motion.div className="kx-actions" variants={riseV} style={{ marginTop: 'var(--mk-space-10)' }}>
        <Button size="lg" onClick={onStartVisit} icon={<Icon name="checkup" />}>
          Start today's visit
        </Button>
        <Button variant="quiet" onClick={onBack}>
          Not me
        </Button>
      </motion.div>
    </motion.div>
  );
}

function Count({ value, one, many }: { value: number; one: string; many: string }) {
  return (
    <div className="kx-count">
      <div className="kx-count__value">{value}</div>
      <div className="kx-count__label">{value === 1 ? one : many}</div>
    </div>
  );
}

function formatDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

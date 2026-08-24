/**
 * The clinical brief — the answer to "what did we get back for all that input".
 *
 * Everything before this screen is capture. This is the return value: what the record now
 * knows about this patient, arranged so a physician can take it in before the patient has
 * finished sitting down.
 *
 * FIVE QUESTIONS, IN THE ORDER A CLINICIAN ASKS THEM:
 *
 *   1. What is today about, and did any rule fire?
 *   2. What has changed since I last saw them?
 *   3. What do their numbers look like over time?
 *   4. What are they actually taking — and how do we know?
 *   5. Have they been here for this before?
 *
 * Nothing here is an assessment. Every figure is a recorded measurement or arithmetic
 * between recorded measurements — a difference, a count, a set intersection. There are no
 * scores, no probabilities and no percentages, because a number between two encounters is
 * read as a likelihood no matter how it is labelled.
 */
import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { ApiError, api, type ClinicalReport as Report } from '../shared/api';
import { Badge, EmptyState, Skeleton } from '../design/ui';
import { rise, stagger } from '../design/motion';
import { LabTrend } from './LabTrend';

interface Props {
  patientRef: string;
  onOpenDocument?: (documentRef: string | null) => void;
}

export function ClinicalReport({ patientRef, onOpenDocument }: Props): JSX.Element {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setReport(null);
    setError(null);
    api
      .clinicalReport(patientRef)
      .then((r) => live && setReport(r))
      .catch((exc) =>
        live && setError(exc instanceof ApiError ? exc.message : 'Could not build the report.'),
      );
    return () => {
      live = false;
    };
  }, [patientRef]);

  if (error) {
    return <EmptyState title="The report could not be built" body={error} />;
  }

  if (!report) {
    return (
      <div className="mk-stack" style={{ gap: 'var(--mk-space-4)' }} aria-busy="true">
        <span className="mk-sr-only" role="status">
          Building the clinical report
        </span>
        <Skeleton height={72} radius="var(--mk-radius-lg)" />
        <div className="rep-grid">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} height={150} radius="var(--mk-radius-lg)" />
          ))}
        </div>
      </div>
    );
  }

  const { current, trends, medications, recurrence, redFlags, changed } = report;
  const outOfRange = trends.filter((t) => t.latest.rangeFlag !== 'in_range');

  return (
    <motion.div className="rep" variants={stagger(0.05)} initial="hidden" animate="visible">
      {/* 1 ─ what today is, in one line, with the numbers that back it */}
      <motion.header className="rep-head" variants={rise}>
        <div>
          <p className="rep-kicker">Clinical brief</p>
          <h2 className="rep-title">{current?.headline ?? 'No confirmed visit yet'}</h2>
          <p className="rep-sub">
            {current
              ? `${longDate(current.occurredOn)} · ${current.factCount} recorded facts · confirmed by ${current.confirmedBy}`
              : 'This patient has no confirmed encounter on the record.'}
          </p>
        </div>
        <div className="rep-stats">
          <Stat value={recurrence.visits} label={recurrence.visits === 1 ? 'visit' : 'visits'} />
          <Stat value={report.counts.observations} label="tracked results" />
          <Stat value={medications.count} label="medicines" />
          {/* Only when rules were actually recorded against this encounter. "0 of 0"
              is not reassurance, it is an absence of data wearing the costume of one. */}
          {redFlags.evaluated > 0 && (
            <Stat
              value={redFlags.fired.length}
              label={`of ${redFlags.evaluated} rules fired`}
              tone={redFlags.fired.length ? 'alert' : 'neutral'}
            />
          )}
        </div>
      </motion.header>

      {/* Red flags first when they exist — nothing outranks an escalation. */}
      {redFlags.fired.length > 0 && (
        <motion.section className="rep-flags" variants={rise}>
          {redFlags.fired.map((flag) => (
            <div key={flag.ruleId} className="rep-flag">
              <Badge tone="alert" dot>
                {flag.level ?? 'flag'}
              </Badge>
              <div>
                <div className="rep-flag__id">{flag.ruleId}</div>
                <div className="rep-flag__why">{flag.rationale}</div>
              </div>
            </div>
          ))}
        </motion.section>
      )}

      {/* 2 ─ what changed since last time: a set difference, stated as one */}
      {changed.comparedWith && (
        <motion.section className="rep-section" variants={rise}>
          <SectionHead
            title="Since the last visit"
            note={`Compared with ${longDate(changed.comparedWith.occurredOn)} — ${changed.comparedWith.headline ?? 'previous visit'}`}
          />
          <div className="rep-changed">
            <ChangeColumn label="New this visit" tone="warn" items={changed.new} />
            <ChangeColumn label="Not reported this time" tone="neutral" items={changed.resolved} />
            <ChangeColumn label="Still present" tone="ok" items={changed.persisting} />
          </div>
        </motion.section>
      )}

      {/* 3 ─ the numbers over time */}
      <motion.section className="rep-section" variants={rise}>
        <SectionHead
          title="Results over time"
          note={
            trends.length
              ? `${trends.length} analytes with more than one measurement. The shaded band is the reference interval printed on the source report; ${outOfRange.length} are currently outside it.`
              : undefined
          }
        />
        {trends.length === 0 ? (
          <EmptyState
            title="No result has been measured twice yet"
            body="A single value is a reading, not a trend. When this patient has a second report for the same analyte, it appears here as a series."
          />
        ) : (
          <div className="rep-grid">
            {trends.map((series) => (
              <LabTrend
                key={series.analyteKey}
                series={series}
                onOpenSource={onOpenDocument}
              />
            ))}
          </div>
        )}
      </motion.section>

      {/* 4 ─ medicines, and how each one is known */}
      <motion.section className="rep-section" variants={rise}>
        <SectionHead title="Medicines on the record" note={medications.note} />
        {medications.threads.length === 0 ? (
          <EmptyState
            title="No medicines recorded"
            body="Nothing has been read from a prescription or reported by the patient."
          />
        ) : (
          <div className="rep-meds">
            {medications.threads.map((thread) => (
              <div
                key={thread.normalized}
                className={`rep-med${thread.needsReconciliation ? ' rep-med--warn' : ''}`}
              >
                <div className="rep-med__head">
                  <span className="rep-med__name">{thread.name}</span>
                  {thread.needsReconciliation && <Badge tone="warn">needs reconciliation</Badge>}
                </div>
                {thread.reason && <div className="rep-med__why">{thread.reason}</div>}
                <ol className="rep-med__track">
                  {thread.mentions.map((m, i) => (
                    <li key={i} className="rep-med__mention" data-status={m.status}>
                      <span className="rep-med__pip" aria-hidden="true" />
                      <span className="rep-med__when">{shortDate(m.observedOn ?? m.encounterOn)}</span>
                      <span className="rep-med__how">{m.howWeKnow}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        )}
      </motion.section>

      {/* 5 ─ has this happened before */}
      <motion.section className="rep-section" variants={rise}>
        <SectionHead title="Why this patient has come in" note={recurrence.note} />
        <ul className="rep-recur">
          {recurrence.groups.map((group) => (
            <li key={group.headline ?? 'unspecified'} className="rep-recur__row">
              <span className="rep-recur__count">{group.count}×</span>
              <span className="rep-recur__what">{group.headline ?? 'Unspecified'}</span>
              <span className="rep-recur__when">
                {group.occurredOn.map((d) => shortDate(d)).join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      </motion.section>

      <motion.p className="rep-notice" variants={rise}>
        {report.notice}
      </motion.p>
    </motion.div>
  );
}

function SectionHead({ title, note }: { title: string; note?: string }) {
  return (
    <div className="rep-section__head">
      <h3 className="rep-section__title">{title}</h3>
      {note && <p className="rep-section__note">{note}</p>}
    </div>
  );
}

function Stat({
  value,
  label,
  tone = 'neutral',
}: {
  value: number;
  label: string;
  tone?: 'neutral' | 'alert';
}) {
  return (
    <div className={`rep-stat${tone === 'alert' ? ' rep-stat--alert' : ''}`}>
      <span className="rep-stat__value">{value}</span>
      <span className="rep-stat__label">{label}</span>
    </div>
  );
}

function ChangeColumn({
  label,
  tone,
  items,
}: {
  label: string;
  tone: 'warn' | 'neutral' | 'ok';
  items: { path: string; value: string }[];
}) {
  return (
    <div className="rep-change" data-tone={tone}>
      <div className="rep-change__label">
        {label} <span className="rep-change__n">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <div className="rep-change__none">none</div>
      ) : (
        <ul>
          {items.slice(0, 8).map((item) => (
            <li key={`${item.path}:${item.value}`}>{item.value.replace(/_/g, ' ')}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
}

function longDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

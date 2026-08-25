/**
 * The Clinical Intelligence Brief, for the physician.
 *
 * CLINICIAN DENSITY. This screen is read in ninety seconds by someone with a queue outside
 * the door, so it is dense on purpose — `data-density="clinical"` tightens the shared scale
 * rather than inventing a second one. The patient view of the same payload is the calm one.
 *
 * EVERY CLINICAL LINE IS A BUTTON. Not a decorative hover: `factRef` opens the actual source.
 * A brief that asserts "burning, comes and goes" without being able to show where that came
 * from is a summary, and summaries are what this project exists not to produce.
 *
 * WHAT CHANGED? IS FIRST AFTER THE ALERTS, deliberately. It is the question a follow-up
 * consultation actually opens with, and burying it under a full history is how a physician
 * ends up re-taking a history the record already holds.
 *
 * EMPTY SECTIONS SAY WHY. `emptyReason` comes from the backend in plain words and is rendered
 * verbatim — never replaced with "None" or "No significant findings", which are clinical
 * assertions nobody made.
 */
import { useEffect, useState } from 'react';
import { api, type Brief, type BriefLine } from '../shared/api';
import { EvidencePanel } from './EvidencePanel';
import { StateGlyph } from '../design/ui/StateGlyph';
import { Icon } from '../shared/Icon';
import { ExportButtons } from './ExportButtons';

interface Props {
  patientRef: string;
}

/** A section shell, so every empty state looks the same and none can be silently skipped. */
function Section({
  title,
  note,
  emptyReason,
  children,
  count,
}: {
  title: string;
  note?: string | null;
  emptyReason?: string | null;
  children?: React.ReactNode;
  count?: number;
}): JSX.Element {
  return (
    <section className="bx-section" aria-label={title}>
      <header className="bx-section__head">
        <h2>{title}</h2>
        {count !== undefined && count > 0 && <span className="bx-count">{count}</span>}
      </header>
      {emptyReason ? (
        <p className="bx-empty">{emptyReason}</p>
      ) : (
        <>
          {children}
          {note && <p className="bx-note">{note}</p>}
        </>
      )}
    </section>
  );
}

/** One clickable clinical line. The whole row is the target — a small icon would not be. */
function Line({ line, onOpen }: { line: BriefLine; onOpen: (ref: string) => void }): JSX.Element {
  const modality = line.evidenceModalities[0] ?? line.evidenceKinds[0] ?? 'source';
  return (
    <button
      type="button"
      className="bx-line"
      onClick={() => onOpen(line.factRef)}
      data-modality={modality}
      // The accessible name has to say what clicking does; "headache" alone does not.
      aria-label={`${line.label}: ${line.displayValue ?? ''} — open the source`}
    >
      <span className="bx-line__label">{line.label}</span>
      <span className="bx-line__value">{line.displayValue ?? String(line.value ?? '')}</span>
      <span className="bx-line__origin" title={`Source: ${modality}`}>
        <Icon name={modality === 'document' ? 'image' : modality === 'voice' ? 'mic' : 'other'} />
      </span>
      {!line.confirmedByPhysician && <span className="bx-line__unverified">unverified</span>}
    </button>
  );
}

export function DoctorBrief({ patientRef }: Props): JSX.Element {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openFact, setOpenFact] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .brief(patientRef)
      .then((b) => live && setBrief(b))
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Could not load the brief.'));
    return () => {
      live = false;
    };
  }, [patientRef]);

  if (error) return <p className="bx-empty bx-empty--error">{error}</p>;
  if (!brief) return <div className="bx-loading" aria-label="Loading the brief" />;

  const { header, snapshot, whatChanged, observations } = brief;
  const encounterRef = header.encounter?.encounterRef ?? '';

  return (
    <div className="bx" data-density="clinical">
      <div className="bx-main">
        {/* ── header ─────────────────────────────────────────────── */}
        <header className="bx-header">
          <div>
            <h1>{header.displayName ?? header.patientRef}</h1>
            <p className="bx-header__sub">
              {[
                header.ageYears !== null ? `${header.ageYears} years` : null,
                header.gender,
                header.encounter ? `Visit of ${header.encounter.occurredOn}` : null,
                `${header.encounterCount} recorded visit(s)`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </div>
          {header.encounter && header.encounter.priority !== 'routine' && (
            <StateGlyph
              state={header.encounter.priority === 'immediate' ? 'critical' : 'caution'}
              title={`Priority: ${header.encounter.priority}`}
            />
          )}
        </header>

        {/* ── red flags, above everything ─────────────────────────── */}
        <Section
          title="Escalations"
          note={brief.redFlags.note}
          emptyReason={brief.redFlags.emptyReason}
          count={brief.redFlags.items.length}
        >
          <ul className="bx-flags">
            {brief.redFlags.items.map((f) => (
              <li key={f.ruleId} className="bx-flag" data-level={f.level ?? 'urgent'}>
                <StateGlyph state={f.level === 'immediate' ? 'critical' : 'caution'} />
                <span>{f.rationale ?? f.ruleId}</span>
              </li>
            ))}
          </ul>
        </Section>

        {/* ── What Changed? — the follow-up question, answered first ─ */}
        <Section
          title="What changed?"
          note={whatChanged.note}
          emptyReason={whatChanged.emptyReason}
        >
          {whatChanged.comparedWith && (
            <p className="bx-comparedwith">
              Compared with the visit of <strong>{whatChanged.comparedWith.occurredOn}</strong>
              {whatChanged.comparedWith.headline ? ` — ${whatChanged.comparedWith.headline}` : ''}
            </p>
          )}
          <div className="bx-changed">
            {(
              [
                ['New this visit', whatChanged.new, 'new'],
                ['Not recorded this visit', whatChanged.resolved, 'resolved'],
                ['Same as before', whatChanged.persisting, 'persisting'],
              ] as const
            ).map(([label, items, kind]) => (
              <div key={kind} className="bx-changed__col" data-kind={kind}>
                <h3>
                  {label} <span className="bx-count">{items.length}</span>
                </h3>
                <ul>
                  {items.map((it, i) => (
                    <li key={`${it.path}-${i}`}>
                      {it.factRef ? (
                        <button
                          type="button"
                          className="bx-chip"
                          onClick={() => setOpenFact(it.factRef!)}
                        >
                          {it.value}
                        </button>
                      ) : (
                        // No factRef: a `resolved` item belongs to the PRIOR encounter, and
                        // this panel resolves refs against the current one. Showing it as
                        // plain text is honest; a dead button would not be.
                        <span className="bx-chip bx-chip--static">{it.value}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>

        {/* ── current snapshot ────────────────────────────────────── */}
        <Section
          title="Current clinical snapshot"
          emptyReason={snapshot.emptyReason}
          count={snapshot.items.length}
        >
          <div className="bx-lines">
            {snapshot.items.map((l) => (
              <Line key={l.factRef} line={l} onOpen={setOpenFact} />
            ))}
          </div>

          {snapshot.allergies.length > 0 && (
            <>
              <h3 className="bx-subhead">Allergies</h3>
              <div className="bx-lines">
                {snapshot.allergies.map((l) => (
                  <Line key={l.factRef} line={l} onOpen={setOpenFact} />
                ))}
              </div>
            </>
          )}

          {snapshot.reportedMedications.length > 0 && (
            <>
              <h3 className="bx-subhead">Medicines on the patient&rsquo;s papers</h3>
              <div className="bx-lines">
                {snapshot.reportedMedications.map((m, i) => (
                  <div key={i} className="bx-medgroup">
                    <strong>{m.name}</strong>
                    <span>{[m.dose, m.frequency].filter(Boolean).join(' · ')}</span>
                    <div className="bx-medgroup__lines">
                      {m.lines.map((l) => (
                        <Line key={l.factRef} line={l} onOpen={setOpenFact} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </Section>

        {/* ── labs ───────────────────────────────────────────────── */}
        <Section
          title="Laboratory values"
          note={observations.note}
          emptyReason={observations.emptyReason}
        >
          {observations.series.map((s) => (
            <div key={s.analyteKey} className="bx-series">
              <div className="bx-series__head">
                <strong>{s.display}</strong>
                {s.unit && <span className="bx-unit">{s.unit}</span>}
                {s.delta !== null && s.delta !== undefined && (
                  // Arithmetic between two recorded measurements. Never a word like
                  // "worsening", which would be a judgement about the patient.
                  <span className="bx-delta">
                    {s.delta > 0 ? '+' : ''}
                    {s.delta} across {s.points.length} readings
                  </span>
                )}
              </div>
              <ol className="bx-points">
                {s.points.map((p, i) => (
                  <li key={i} data-flag={p.rangeFlag}>
                    <span className="bx-points__date">{p.observedOn}</span>
                    <span className="bx-points__value">
                      {p.value}
                      {p.unit ? ` ${p.unit}` : ''}
                    </span>
                    {p.rangeFlag !== 'unknown' && (
                      // `in_range` is a column value, not a word. Rendered raw it reached the
                      // screen as "IN_RANGE", which is our schema showing through.
                      <span className="bx-points__flag">{p.rangeFlag.replace(/_/g, ' ')}</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          ))}
          {observations.singles.map((s) => (
            <div key={s.analyteKey} className="bx-series bx-series--single">
              <div className="bx-series__head">
                <strong>{s.display}</strong>
                <span className="bx-points__value">
                  {s.points[0]?.value}
                  {s.points[0]?.unit ? ` ${s.points[0].unit}` : ''}
                </span>
              </div>
              {/* Why there is no chart, said out loud. A missing chart with no explanation
                  reads as a rendering failure. */}
              <p className="bx-note">{s.notChartableBecause}</p>
            </div>
          ))}
        </Section>

        {/* ── medication history ─────────────────────────────────── */}
        <Section
          title="Medication history"
          note={brief.medications.note}
          emptyReason={brief.medications.emptyReason}
          count={brief.medications.items.length}
        >
          <table className="bx-table">
            <thead>
              <tr>
                <th>Medicine</th>
                <th>Dose</th>
                <th>Frequency</th>
                <th>How we know</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {brief.medications.items.map((m, i) => (
                <tr key={i}>
                  <td>{m.name}</td>
                  <td>{m.dose ?? '—'}</td>
                  <td>{m.frequency ?? '—'}</td>
                  <td>
                    <span className="mk-badge" data-status={m.status}>
                      {m.status.replace(/_/g, ' ')}
                    </span>
                    <span className="bx-origin">{m.origin.replace(/-/g, ' ')}</span>
                  </td>
                  <td>{m.observedOn ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        {/* ── timeline ───────────────────────────────────────────── */}
        <Section
          title="Visit timeline"
          emptyReason={brief.timeline.emptyReason}
          count={brief.timeline.items.length}
        >
          <ol className="bx-timeline">
            {brief.timeline.items.map((t) => (
              <li key={t.encounterRef} data-current={t.isCurrent || undefined}>
                <span className="bx-timeline__date">{t.occurredOn}</span>
                <span className="bx-timeline__label">{t.headline ?? 'Intake'}</span>
                <span className="bx-timeline__by">{t.confirmedBy}</span>
              </li>
            ))}
          </ol>
        </Section>

        {/* ── similar encounters ─────────────────────────────────── */}
        <Section
          title="Similar earlier visits"
          note={brief.similarEncounters.note}
          emptyReason={brief.similarEncounters.emptyReason}
          count={brief.similarEncounters.items.length}
        >
          {brief.similarEncounters.items.map((s) => (
            <div key={s.encounterRef} className="bx-similar">
              <div className="bx-similar__head">
                <strong>{s.occurredOn}</strong>
                <span>{s.headline ?? 'Intake'}</span>
              </div>
              {/* Words, not a score. */}
              <p className="bx-note">{s.why}</p>
              <ul className="bx-shared">
                {s.sharedFeatures.map((f, i) => (
                  <li key={i}>{f.value}</li>
                ))}
              </ul>
            </div>
          ))}
        </Section>

        {/* ── contradictions ─────────────────────────────────────── */}
        <Section
          title="Contradictions"
          note={brief.contradictions.note}
          emptyReason={brief.contradictions.emptyReason}
          count={brief.contradictions.items.length}
        >
          {brief.contradictions.items.map((c) => (
            <div key={c.contradictionRef} className="bx-contradiction">
              <strong>{c.label}</strong>
              {/* BOTH sides, side by side. Neither is chosen. */}
              <div className="bx-contradiction__sides">
                <div>
                  <h4>One source says</h4>
                  <pre>{JSON.stringify(c.sideA, null, 1)}</pre>
                </div>
                <div>
                  <h4>The other says</h4>
                  <pre>{JSON.stringify(c.sideB, null, 1)}</pre>
                </div>
              </div>
            </div>
          ))}
        </Section>

        {/* ── unresolved ─────────────────────────────────────────── */}
        <Section
          title="Unresolved and changed"
          note={brief.unresolved.note}
          emptyReason={brief.unresolved.emptyReason}
        >
          {brief.unresolved.declinedOrUnknown.length > 0 && (
            <>
              <h3 className="bx-subhead">The patient chose not to say, or did not know</h3>
              <ul className="bx-plain">
                {brief.unresolved.declinedOrUnknown.map((d) => (
                  <li key={d.factRef}>
                    {d.path} <span className="mk-badge">{d.state}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {brief.unresolved.superseded.length > 0 && (
            <>
              <h3 className="bx-subhead">Answers the patient changed</h3>
              <ul className="bx-plain">
                {brief.unresolved.superseded.map((s) => (
                  <li key={s.factRef}>
                    {s.path}: was <s>{String(s.wasValue)}</s>
                  </li>
                ))}
              </ul>
            </>
          )}
          {brief.unresolved.invalidated.length > 0 && (
            <>
              <h3 className="bx-subhead">Ruled out as not applicable</h3>
              <ul className="bx-plain">
                {brief.unresolved.invalidated.map((s) => (
                  <li key={s.factRef}>
                    {s.path} — {s.reason}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>

        {/* ── completeness ───────────────────────────────────────── */}
        <Section title="Intake completeness" note={brief.completeness.note}>
          <div className="bx-completeness">
            {(
              [
                ['Collected', brief.completeness.collected, 'collected'],
                ['Declined', brief.completeness.declined, 'declined'],
                ['Not asked or unanswered', brief.completeness.missing, 'missing'],
              ] as const
            ).map(([label, items, kind]) => (
              <div key={kind} data-kind={kind}>
                <h3>
                  {label} <span className="bx-count">{items.length}</span>
                </h3>
                <ul className="bx-plain">
                  {items.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>

        {/* ── confirmation ───────────────────────────────────────── */}
        <Section title="Physician confirmation" note={brief.confirmation.note}>
          <p className="bx-confirm" data-confirmed={brief.confirmation.confirmed || undefined}>
            {brief.confirmation.confirmed ? (
              <>
                Confirmed by <strong>{brief.confirmation.confirmedBy}</strong>
                {brief.confirmation.confirmedAt
                  ? ` on ${brief.confirmation.confirmedAt.slice(0, 10)}`
                  : ''}
              </>
            ) : (
              'Not yet confirmed by a physician.'
            )}
          </p>
        </Section>

        <ExportButtons patientRef={patientRef} />

        <p className="bx-notice">{brief.notice}</p>
        <p className="bx-version">
          Report version {brief.reportVersion} · assembled from stored records, not generated
        </p>
      </div>

      <EvidencePanel
        patientRef={patientRef}
        encounterRef={encounterRef}
        factRef={openFact}
        onClose={() => setOpenFact(null)}
      />
    </div>
  );
}

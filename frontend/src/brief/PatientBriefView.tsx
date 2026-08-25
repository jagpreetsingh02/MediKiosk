/**
 * The same brief, for the person it is about.
 *
 * PATIENT CALM, not clinician density. `data-density="patient"` widens the shared scale — one
 * column, large type, generous spacing — because this is read standing up, possibly by someone
 * who has never used a kiosk, possibly by someone who cannot read quickly.
 *
 * GROUPED BY WHERE IT CAME FROM, not by clinical category. "What you told us" is a question a
 * patient can answer for themselves; "History of presenting illness" is not.
 *
 * ⛔ NOTHING HERE IS CLICKABLE INTO EVIDENCE, and that is deliberate rather than unfinished.
 * The provenance a patient needs is the group heading — these are your words, this came off
 * your paper — and a drawer full of ontology paths, tiers and confidence scores would be
 * showing them our bookkeeping rather than their record.
 *
 * The backend already strips every internal identifier (proved in
 * `tests/test_report_determinism.py` and again over the wire). This component adds nothing
 * back: it renders only `label` and `value`, both of which are plain language by construction.
 */
import { useEffect, useState } from 'react';
import { api, type PatientBrief } from '../shared/api';

interface Props {
  patientRef: string;
}

export function PatientBriefView({ patientRef }: Props): JSX.Element {
  const [brief, setBrief] = useState<PatientBrief | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .patientBrief(patientRef)
      .then((b) => live && setBrief(b))
      .catch(
        (e) =>
          live &&
          setError(
            e instanceof Error
              ? 'We could not open your record just now. Please ask a staff member for help.'
              : 'Something went wrong.',
          ),
      );
    return () => {
      live = false;
    };
  }, [patientRef]);

  if (error) return <p className="bx-empty bx-empty--error">{error}</p>;
  if (!brief) return <div className="bx-loading" aria-label="Loading your record" />;

  return (
    <div className="bx bx--patient" data-density="patient">
      <div className="bx-main">
        <header className="bx-header">
          <h1>Your visit</h1>
          {brief.forWhom && <p className="bx-header__sub">{brief.forWhom}</p>}
        </header>

        {brief.groups.map((group) => (
          <section key={group.title} className="bx-section" aria-label={group.title}>
            <header className="bx-section__head">
              <h2>{group.title}</h2>
            </header>

            {group.emptyReason ? (
              // Said in the patient's own terms by the backend, and rendered verbatim.
              <p className="bx-empty">{group.emptyReason}</p>
            ) : (
              <dl className="bx-patientlist">
                {group.items.map((item, i) => (
                  <div key={i} className="bx-patientlist__row">
                    <dt>{item.label}</dt>
                    <dd>{String(item.value ?? '')}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
        ))}

        <p className="bx-notice">{brief.notice}</p>
      </div>
    </div>
  );
}

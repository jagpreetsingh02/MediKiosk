/**
 * One drug, threaded across every visit, with how each mention is KNOWN.
 *
 * ROLE-NEUTRAL. This file lives in `record/` rather than in `physician/` or `patient/`
 * because both surfaces read the same medication thread, off the same route, and a component
 * owned by one role and borrowed by the other is how a control written for a clinician ends
 * up on a patient's screen. `audience` is the ONLY thing that varies, and it varies over
 * wording alone — never over which mentions are shown. See ADR-0016.
 *
 * The status vocabulary is the whole point of this panel. "documented" means a document says
 * so; "patient reports taking" means the patient said so today. Nothing in this system
 * concludes a medicine is still being taken because it was once prescribed, and this screen
 * is where that refusal becomes visible rather than merely correct — a physician reading
 * "Metformin 500 mg" with no provenance beside it would reasonably assume current use.
 */
import type { MedicationThread } from '../shared/api';

interface Props {
  medications: MedicationThread[];
  onOpenDocument: (documentRef: string) => void;
  /** Whose vocabulary the labels are written in. Never changes what is shown. */
  audience?: 'clinician' | 'patient';
}

const STATUS_LABEL: Record<string, string> = {
  documented: 'Documented',
  'patient-reported-current': 'Patient reports taking',
  historical: 'Historical',
  'stopped-reported': 'Patient reports stopped',
  uncertain: 'Uncertain',
};

/**
 * The same five states, said to the person they are about.
 *
 * "Patient reports taking" is a sentence written for somebody reading ABOUT a patient. Read
 * by the patient it is third-person about themselves, which is both odd and slightly
 * distancing. The MEANING is identical — nothing is softened, and "Uncertain" stays
 * uncertain, because a patient who does not know a line is unsure cannot correct it.
 */
const STATUS_LABEL_PATIENT: Record<string, string> = {
  documented: 'On a paper you gave us',
  'patient-reported-current': 'You said you take this',
  historical: 'From an earlier visit',
  'stopped-reported': 'You said you stopped this',
  uncertain: 'Not certain yet',
};

/**
 * `howWeKnow` in the patient's own voice.
 *
 * The server's `_how_we_know()` is a pure function of `status` — the same five keys, expanded
 * into a sentence — and three of its five phrasings are written ABOUT a patient rather than
 * TO one ("the patient said they take this"). This is that expansion in the second person,
 * keyed off the SAME field rather than parsed out of the server's wording, so the two cannot
 * disagree about what a status means and nothing is lost in the swap. Where the server's
 * sentence carries nuance the short status label does not — "recorded at a previous visit,
 * not mentioned since" — that nuance is kept.
 */
const HOW_WE_KNOW_PATIENT: Record<string, string> = {
  documented: 'read off a paper you gave us',
  'patient-reported-current': 'you told us you take this',
  historical: 'written down at an earlier visit, and not mentioned since',
  'stopped-reported': 'you told us you had stopped it',
  uncertain: 'we are not sure where this came from — the doctor will check',
};

export function MedicationHistory({
  medications,
  onOpenDocument,
  audience = 'clinician',
}: Props): JSX.Element {
  const patient = audience === 'patient';
  const statusLabel = patient ? STATUS_LABEL_PATIENT : STATUS_LABEL;

  if (!medications.length) {
    return (
      <div className="source-empty">
        {patient
          ? 'No medicines are recorded for you yet.'
          : 'No medicines recorded for this patient.'}
      </div>
    );
  }

  return (
    <div className="meds">
      {medications.map((thread) => (
        <section
          key={thread.normalized}
          className={`med-thread${thread.needsReconciliation ? ' needs-rec' : ''}`}
        >
          <header className="med-head">
            <h3>{thread.name}</h3>
            {thread.needsReconciliation && (
              // "Reconciliation" is a word for a medicines list, not for the person taking
              // the medicine. The finding is the same one either way — it is not hidden.
              <span className="med-warn">
                {patient ? 'The doctor will check this with you' : 'Needs reconciliation'}
              </span>
            )}
          </header>

          {thread.reason && <p className="med-reason">{thread.reason}</p>}

          <ol className="med-mentions">
            {thread.mentions.map((mention, index) => (
              <li key={`${thread.normalized}-${index}`}>
                <span className="med-when">
                  {mention.observedOn ?? mention.encounterOn ?? '—'}
                </span>
                <span className={`med-status s-${mention.status}`}>
                  {statusLabel[mention.status] ?? mention.status}
                </span>
                <span className="med-dose">
                  {[mention.dose, mention.frequency].filter(Boolean).join(' · ')}
                </span>
                <span className="med-know">
                  {patient
                    ? HOW_WE_KNOW_PATIENT[mention.status] ?? mention.howWeKnow
                    : mention.howWeKnow}
                </span>
                {mention.recordedAt && (
                  <span className="med-recorded">
                    {patient ? 'Added to your record ' : 'Added to record '}
                    {shortDate(mention.recordedAt)}
                  </span>
                )}
                {mention.documentRef && (
                  <button
                    type="button"
                    className="lt-source"
                    onClick={() => onOpenDocument(mention.documentRef as string)}
                  >
                    {patient ? 'Your paper' : 'Original'}
                  </button>
                )}
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

function shortDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

/**
 * One drug, threaded across every visit, with how each mention is KNOWN.
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
}

const STATUS_LABEL: Record<string, string> = {
  documented: 'Documented',
  'patient-reported-current': 'Patient reports taking',
  historical: 'Historical',
  'stopped-reported': 'Patient reports stopped',
  uncertain: 'Uncertain',
};

export function MedicationHistory({ medications, onOpenDocument }: Props): JSX.Element {
  if (!medications.length) {
    return <div className="source-empty">No medicines recorded for this patient.</div>;
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
            {thread.needsReconciliation && <span className="med-warn">Needs reconciliation</span>}
          </header>

          {thread.reason && <p className="med-reason">{thread.reason}</p>}

          <ol className="med-mentions">
            {thread.mentions.map((mention, index) => (
              <li key={`${thread.normalized}-${index}`}>
                <span className="med-when">
                  {mention.observedOn ?? mention.encounterOn ?? '—'}
                </span>
                <span className={`med-status s-${mention.status}`}>
                  {STATUS_LABEL[mention.status] ?? mention.status}
                </span>
                <span className="med-dose">
                  {[mention.dose, mention.frequency].filter(Boolean).join(' · ')}
                </span>
                <span className="med-know">{mention.howWeKnow}</span>
                {mention.documentRef && (
                  <button
                    type="button"
                    className="lt-source"
                    onClick={() => onOpenDocument(mention.documentRef as string)}
                  >
                    Original
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

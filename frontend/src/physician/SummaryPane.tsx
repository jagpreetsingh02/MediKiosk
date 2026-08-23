/**
 * The summary. Every fact line is a button, because every fact line is click-to-source.
 *
 * Lines are rendered in the order the backend produced them and nothing is re-sorted here:
 * a physician reading their fortieth history of the morning relies on the sections being in
 * the same place every time.
 */
import type { SummaryLine } from '../shared/api';

interface Props {
  lines: SummaryLine[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

const SECTION_TITLES: Record<string, string> = {
  patient: 'Patient',
  chief_complaint: 'Presenting complaint',
  hpi: 'History of presenting illness',
  red_flags: 'Escalation',
  past_medical: 'Past medical history',
  past_surgical: 'Past surgical history',
  drug_allergy: 'Medicines and allergies',
  documents: 'Prior records',
  family_history: 'Family history',
  personal_history: 'Personal history',
  review_of_systems: 'Review of systems',
  ayush: 'Ayurvedic assessment (patient-reported)',
  gaps: 'Not covered',
};

export function SummaryPane({ lines, selectedIndex, onSelect }: Props): JSX.Element {
  const grouped: { sectionId: string; entries: { line: SummaryLine; index: number }[] }[] = [];
  lines.forEach((line, index) => {
    const last = grouped[grouped.length - 1];
    if (last && last.sectionId === line.sectionId) last.entries.push({ line, index });
    else grouped.push({ sectionId: line.sectionId, entries: [{ line, index }] });
  });

  return (
    <div>
      {grouped.map((group) => (
        <section key={`${group.sectionId}-${group.entries[0].index}`} className="summary-section">
          <h2 className="summary-head">{SECTION_TITLES[group.sectionId] ?? group.sectionId}</h2>
          {group.entries.map(({ line, index }) => {
            const traceable = line.kind === 'fact' && line.sources.length > 0;
            const classes = [
              'summary-line',
              line.kind === 'structural' ? 'structural' : '',
              traceable ? 'traceable' : '',
              selectedIndex === index ? 'selected' : '',
              line.emphasis ?? '',
            ]
              .filter(Boolean)
              .join(' ');

            const tier = line.sources[0]?.tier;
            return (
              <button
                key={index}
                type="button"
                className={classes}
                onClick={() => onSelect(index)}
                disabled={line.kind === 'structural'}
                data-index={index}
              >
                {tier && <span className={`tier-dot tier-${tier}`} aria-hidden="true" />}
                {line.text}
              </button>
            );
          })}
        </section>
      ))}
    </div>
  );
}

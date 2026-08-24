/**
 * Progress, by section rather than by question count.
 *
 * "Question 7 of 28" is a promise this flow cannot keep: the interview branches, so the
 * denominator moves while the patient watches — and a number that goes *up* as you answer
 * reads as punishment. Sections do not move. The patient sees which part of the visit they
 * are in, which parts are done, and which are still ahead, and that is the honest shape of
 * an adaptive interview.
 *
 * The bar stays, because "roughly how much longer" is a real question and a filling bar
 * answers it without committing to an exact count. Its denominator is the questions this
 * patient will actually be asked, not the ontology's total — a branch that closed is not a
 * question they are behind on.
 *
 * The current section is marked on its own chip and nowhere else. Naming it again underneath
 * put the same words twice on a screen whose design rule is one thing at a time.
 */
import type { Progress, SectionProgress } from '../shared/api';

interface Props {
  progress: Progress;
  sections: SectionProgress[];
  currentSectionId: string | null;
}

export function ProgressRail({ progress, sections, currentSectionId }: Props): JSX.Element {
  return (
    <div className="progress-rail">
      <div
        className="progress-bar"
        role="progressbar"
        aria-valuenow={progress.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="How far through the questions you are"
      >
        <div className="progress-fill" style={{ width: `${progress.percent}%` }} />
      </div>
      <div className="progress-sections">
        {sections.map((section) => (
          <span
            key={section.sectionId}
            className={`progress-chip${section.complete ? ' complete' : ''}${
              section.sectionId === currentSectionId ? ' current' : ''
            }`}
          >
            <span aria-hidden="true" className="progress-mark">
              {section.complete ? '✓' : section.sectionId === currentSectionId ? '●' : ''}
            </span>
            {section.title}
          </span>
        ))}
      </div>
    </div>
  );
}

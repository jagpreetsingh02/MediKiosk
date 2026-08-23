/**
 * Progress.
 *
 * The denominator is the number of questions this patient will actually be asked, not the
 * ontology's total — a branch that closed is not a question they are behind on. Showing 30%
 * to someone who is nearly finished is how you get an abandoned session.
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
            {section.title} {section.answered}/{section.total}
          </span>
        ))}
      </div>
      <div className="progress-count">
        {progress.answered} of {progress.askable} questions answered
      </div>
    </div>
  );
}

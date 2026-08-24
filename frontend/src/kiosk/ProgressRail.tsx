/**
 * Progress, by section rather than by question count.
 *
 * "Question 7 of 28" is a promise this flow cannot keep: the interview branches, so the
 * denominator moves while the patient watches — and a number that goes *up* as you answer
 * reads as punishment. Sections do not move. The patient sees which part of the visit they
 * are in, which parts are done, and which are still ahead, and that is the honest shape of
 * an adaptive interview.
 *
 * It now lives in the header rather than pinned to the bottom of the page, which is why the
 * separate progress bar is gone: a filling bar and a row of section chips were answering the
 * same question twice, and the chips answer it better because they name the thing. The
 * numeric percentage survives for screen readers on the container, where it costs nothing.
 *
 * The active chip is marked by a travelling highlight (`layoutId`), so moving between
 * sections reads as one indicator sliding rather than two chips blinking.
 */
import { motion, useReducedMotion } from 'motion/react';
import type { Progress, SectionProgress } from '../shared/api';
import { springSoft } from '../design/motion';

interface Props {
  progress: Progress;
  sections: SectionProgress[];
  currentSectionId: string | null;
}

export function ProgressRail({ progress, sections, currentSectionId }: Props): JSX.Element {
  const prefersReduced = useReducedMotion() ?? false;

  return (
    <div
      className="kx-rail"
      role="progressbar"
      aria-valuenow={progress.percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="How far through the questions you are"
    >
      {sections.map((section) => {
        const active = section.sectionId === currentSectionId;
        const done = !active && section.answered > 0 && section.answered >= section.total;
        const state = active ? 'active' : done ? 'done' : 'ahead';
        return (
          <div key={section.sectionId} className="kx-rail__step" data-state={state}>
            {active && !prefersReduced && (
              <motion.span
                layoutId="kx-rail-active"
                className="kx-rail__halo"
                transition={springSoft}
                aria-hidden="true"
              />
            )}
            <span className="kx-rail__pip" aria-hidden="true" />
            {/* Only the current section is named. Eight labels in a header row
                overflowed and truncated mid-word, which told the patient less
                than a single clear "you are here" does. The rest keep their pips
                so the shape of the whole interview stays visible, and every
                title is still available to a screen reader. */}
            {active ? (
              <span className="kx-rail__text">{section.title}</span>
            ) : (
              <span className="mk-sr-only">{section.title}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

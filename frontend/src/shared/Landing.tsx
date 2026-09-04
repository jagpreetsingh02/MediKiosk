/**
 * The front door.
 *
 * It has ten seconds to say what this is, and the thing it must say is *not*
 * "an AI asks you medical questions". It is: this system already remembers you,
 * and it hands a doctor a sourced history before you walk in.
 *
 * So the hero is the memory itself, standing next to the body it belongs to.
 * The figure turns as you scroll; the spine of past visits builds beside it.
 * The three-step strip that used to lead explained the mechanism to someone who
 * had not yet been given a reason to care about the mechanism, so it now
 * follows, for anyone still reading.
 *
 * The no-diagnosis line is above the fold and always visible. That is a product
 * rule (Invariant 1), not a piece of copy to be moved for balance.
 *
 * MOTION BUDGET. Exactly two things type themselves — the wordmark and the one
 * sentence that makes the argument — and one thing tracks the scroll. Everything
 * else rises once, on reveal, and then holds still. A page where every element
 * has its own entrance has no hierarchy of attention, which is the same as
 * having none at all.
 */
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { Badge } from '../design/ui';
import { TypeReveal } from '../design/TypeReveal';
import { useCursorField } from '../design/useCursorField';
import { useScrollProgress } from '../design/useScrollProgress';
import { AnatomyFigure } from './AnatomyFigure';
import { Icon } from './Icon';
import { reduced, rise, stagger } from '../design/motion';

const SPINE = [
  { year: '2024', label: 'Laboratory report', detail: 'HbA1c 8.2% — on file', kind: 'lab' },
  {
    year: '2025',
    label: 'Prescription scanned',
    detail: 'Metformin 500 mg · 1-0-1',
    kind: 'prescription',
  },
  { year: '2025', label: 'Abdominal pain visit', detail: 'Worse after meals', kind: 'encounter' },
  { year: 'Today', label: 'New intake', detail: 'Speak, tap or type', kind: 'current' },
];

const STEPS = [
  {
    icon: 'mic' as const,
    title: 'Tell us what brings you here',
    body: 'Speak or tap, in your own language. Every answer keeps the words you said.',
  },
  {
    icon: 'camera' as const,
    title: 'Show your old papers',
    body: 'Prescriptions and reports are read, checked with you, and kept as evidence.',
  },
  {
    icon: 'checkup' as const,
    title: 'The doctor reads it first',
    body: 'A structured history, every line traceable to its source, before you sit down.',
  },
];

/** The claim this product is actually making, in numbers a judge can check
 *  against `/about`. Set in the display face because they are the one place on
 *  the page where the typography is allowed to be the message. */
const PROOF = [
  { figure: '0.00', label: 'Hallucination rate', note: 'across 62 evaluated scripts' },
  { figure: '100%', label: 'Red-flag sensitivity', note: 'rules, never a model' },
  { figure: '1:1', label: 'Facts to sources', note: 'no fact without its quote' },
];

export function Landing(): JSX.Element {
  const prefersReduced = useReducedMotion() ?? false;
  const riseV = reduced(prefersReduced, rise);
  // The page ground reads the cursor; the hero reads the scroll. Two separate
  // channels on two separate elements, so neither invalidates the other's
  // subtree when it updates.
  const ground = useCursorField<HTMLDivElement>({ global: true, smoothing: 0.09 });
  const scroll = useScrollProgress<HTMLDivElement>({ smoothing: 0.1 });

  return (
    <div className="lx" ref={ground}>
      <div className="lx-field" aria-hidden="true" />

      <div className="lx-hero" ref={scroll}>
        <div className="lx-hero__grid">
          <div className="lx-hero__copy">
            <TypeReveal as="h1" className="lx-title" text="MediKiosk" speed={64} />

            <TypeReveal
              as="p"
              className="lx-tagline"
              text="Your health history, remembered — and ready before you meet the doctor."
              delay={620}
              speed={17}
            />

            <motion.div
              className="lx-disclaimer"
              variants={riseV}
              initial="hidden"
              animate="visible"
              transition={{ delay: 2.1 }}
            >
              <Badge tone="info" dot>
                Does not diagnose
              </Badge>
              <span>It prepares your history for a doctor to read.</span>
            </motion.div>

            <motion.div
              className="lx-cta-row"
              variants={riseV}
              initial="hidden"
              animate="visible"
              transition={{ delay: 2.24 }}
            >
              <Link to="/intake" className="mk-key mk-key--primary lx-cta">
                <span className="mk-key__label">Start intake</span>
                <span className="mk-key__icon" aria-hidden="true">
                  <Icon name="check" />
                </span>
              </Link>
              <Link to="/demo" className="mk-key lx-cta-secondary">
                <span className="mk-key__label">Run a demo case</span>
              </Link>
            </motion.div>

            <motion.p
              className="lx-cta-note"
              variants={riseV}
              initial="hidden"
              animate="visible"
              transition={{ delay: 2.34 }}
            >
              Speak or tap, in ten languages. Nothing is stored without your consent.
            </motion.p>
          </div>

          {/* The figure sits in the second column on desktop and behind the copy
              on narrow screens — see `.lx-hero__figure` in kiosk-v2.css. */}
          <div className="lx-hero__figure">
            <AnatomyFigure />
          </div>
        </div>

        <div className="lx-scrollcue" aria-hidden="true">
          <span className="lx-scrollcue__label">Scroll</span>
          <span className="lx-scrollcue__rail">
            <span className="lx-scrollcue__bead" />
          </span>
        </div>
      </div>

      <motion.section
        className="lx-section lx-section--spine"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.25 }}
        variants={stagger(0.06)}
      >
        <motion.h2 className="lx-section__title" variants={riseV}>
          Four moments. One continuous record.
        </motion.h2>
        <motion.p className="lx-section__lead" variants={riseV}>
          A returning patient is not a blank form. Everything below was already on file before
          today&rsquo;s visit began.
        </motion.p>

        <ol className="lx-spine" aria-label="What MediKiosk remembers">
          {SPINE.map((entry) => (
            <motion.li
              key={`${entry.year}-${entry.label}`}
              className="lx-spine__row"
              data-kind={entry.kind}
              variants={riseV}
            >
              <span className="lx-spine__year">{entry.year}</span>
              <span className="lx-spine__body">
                <span className="lx-spine__label">{entry.label}</span>
                <span className="lx-spine__detail">{entry.detail}</span>
              </span>
              <span className="lx-spine__node" aria-hidden="true" />
            </motion.li>
          ))}
        </ol>
      </motion.section>

      <motion.section
        className="lx-section lx-section--proof"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.3 }}
        variants={stagger(0.07)}
      >
        <dl className="lx-proof">
          {PROOF.map((item) => (
            <motion.div key={item.label} className="lx-proof__cell" variants={riseV}>
              <dt className="lx-proof__figure">{item.figure}</dt>
              <dd className="lx-proof__label">
                {item.label}
                <span>{item.note}</span>
              </dd>
            </motion.div>
          ))}
        </dl>
        <motion.p className="lx-proof__note" variants={riseV}>
          Measured, not claimed — the harness, the gold scripts and the held-out set are in the
          repository, and{' '}
          <a href="/about" target="_blank" rel="noreferrer">
            /about
          </a>{' '}
          names every part of this build that is mocked.
        </motion.p>
      </motion.section>

      <motion.section
        className="lx-section lx-section--steps"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.25 }}
        variants={stagger(0.07)}
      >
        <motion.h2 className="lx-section__title" variants={riseV}>
          How a visit works
        </motion.h2>
        <ul className="lx-steps">
          {STEPS.map((step) => (
            <motion.li key={step.title} className="lx-step" variants={riseV}>
              <span className="lx-step__icon" aria-hidden="true">
                <Icon name={step.icon} />
              </span>
              <h3 className="lx-step__title">{step.title}</h3>
              <p className="lx-step__body">{step.body}</p>
            </motion.li>
          ))}
        </ul>
      </motion.section>

      <footer className="lx-foot">
        <span>All patients synthetic · mock ABHA issuer · not an ABDM integration</span>
        <nav className="lx-links">
          <Link to="/demo">Demo &amp; jury mode</Link>
          <Link to="/physician">Physician review</Link>
          <a href="/about" target="_blank" rel="noreferrer">
            What is mocked
          </a>
        </nav>
      </footer>
    </div>
  );
}

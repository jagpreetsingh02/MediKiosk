/**
 * The front door.
 *
 * It has ten seconds to say what this is, and the thing it must say is *not*
 * "an AI asks you medical questions". It is: this system already remembers you,
 * and it hands a doctor a sourced history before you walk in.
 *
 * So the hero is the memory itself. The three-step strip that used to sit here
 * explained the mechanism to someone who had not yet been given a reason to care
 * about the mechanism; the longitudinal spine does the arguing instead, and the
 * steps follow underneath for anyone still reading.
 *
 * The no-diagnosis line is above the fold and always visible. That is a product
 * rule (Invariant 1), not a piece of copy to be moved for balance.
 */
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { BrandMark } from '../design/KioskShell';
import { Badge } from '../design/ui';
import { Icon } from './Icon';
import { reduced, rise, stagger } from '../design/motion';

const SPINE = [
  { year: '2024', label: 'Laboratory report', detail: 'HbA1c on file', kind: 'lab' },
  { year: '2025', label: 'Prescription scanned', detail: 'Metformin 500 mg', kind: 'prescription' },
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

export function Landing(): JSX.Element {
  const prefersReduced = useReducedMotion() ?? false;
  const riseV = reduced(prefersReduced, rise);

  return (
    <div className="lx">
      <motion.div
        className="lx-inner"
        variants={stagger(0.07)}
        initial="hidden"
        animate="visible"
      >
        <motion.div className="lx-mark" variants={riseV}>
          <BrandMark size={54} />
        </motion.div>

        <motion.h1 className="lx-title" variants={riseV}>
          MediKiosk
        </motion.h1>

        <motion.p className="lx-tagline" variants={riseV}>
          Your health history, <em>remembered</em> — and ready before you meet the doctor.
        </motion.p>

        <motion.div className="lx-disclaimer" variants={riseV}>
          <Badge tone="info" dot>
            Does not diagnose
          </Badge>
          <span>It prepares your history for a doctor to read.</span>
        </motion.div>

        {/* The argument: one patient, four moments, one continuous record. */}
        <motion.ol className="lx-spine" variants={riseV} aria-label="What MediKiosk remembers">
          {SPINE.map((entry) => (
            <li key={`${entry.year}-${entry.label}`} className="lx-spine__row" data-kind={entry.kind}>
              <span className="lx-spine__year">{entry.year}</span>
              <span className="lx-spine__body">
                <span className="lx-spine__label">{entry.label}</span>
                <span className="lx-spine__detail">{entry.detail}</span>
              </span>
            </li>
          ))}
        </motion.ol>

        <motion.div variants={riseV} className="lx-cta-row">
          <Link to="/intake" className="mk-btn mk-btn--primary mk-btn--lg lx-cta">
            <span className="mk-btn__label">Start</span>
            <span className="mk-btn__icon" aria-hidden="true">
              <Icon name="check" />
            </span>
          </Link>
          <span className="lx-cta-note">Speak or tap, in your preferred language.</span>
        </motion.div>

        <motion.ul className="lx-steps" variants={riseV}>
          {STEPS.map((step, index) => (
            <li key={step.title} className="lx-step">
              <span className="lx-step__icon" aria-hidden="true">
                <Icon name={step.icon} />
              </span>
              <span className="lx-step__n">{index + 1}</span>
              <h2 className="lx-step__title">{step.title}</h2>
              <p className="lx-step__body">{step.body}</p>
            </li>
          ))}
        </motion.ul>

        <motion.nav className="lx-links" variants={riseV}>
          <Link to="/demo">Demo &amp; jury mode</Link>
          <span aria-hidden="true">·</span>
          <Link to="/physician">Physician review</Link>
          <span aria-hidden="true">·</span>
          <a href="/about" target="_blank" rel="noreferrer">
            What is mocked
          </a>
        </motion.nav>
      </motion.div>
    </div>
  );
}

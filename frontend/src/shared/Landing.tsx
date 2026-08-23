/**
 * The first thing anyone sees — patient or judge.
 *
 * One sentence of what this is, one obvious action, and the disclaimer that governs the whole
 * product. No "AI", no "FHIR", no "NLP": a patient does not need those words and a judge will
 * find them soon enough in the jury drawer.
 */
import { Link } from 'react-router-dom';
import { Icon } from './Icon';

const STEPS = [
  { icon: 'mic', title: 'Tell us what brings you here', body: 'Speak or tap, in your language.' },
  { icon: 'camera', title: 'Show your old papers', body: 'Prescriptions and reports, if you have them.' },
  { icon: 'checkup', title: 'The doctor gets it first', body: 'A structured history, ready before you walk in.' },
];

export function Landing(): JSX.Element {
  return (
    <div className="landing">
      <div className="landing-inner">
        <h1 className="landing-title">MediKiosk</h1>
        <p className="landing-tagline">Your health history, ready before you meet the doctor.</p>

        <div className="landing-steps">
          {STEPS.map((step, index) => (
            <div key={step.title} className="landing-step">
              <span className="landing-step-n">{index + 1}</span>
              <Icon name={step.icon} />
              <strong>{step.title}</strong>
              <span>{step.body}</span>
            </div>
          ))}
        </div>

        <Link to="/intake" className="landing-cta">
          Start
        </Link>

        <p className="landing-note">
          Speak or tap, in your preferred language.
          <br />
          <strong>This system does not diagnose.</strong> It prepares your history for a doctor
          to read.
        </p>

        <nav className="landing-links">
          <Link to="/demo">Demo &amp; jury mode</Link>
          <span aria-hidden="true">·</span>
          <Link to="/physician">Physician review</Link>
          <span aria-hidden="true">·</span>
          <a href="/about" target="_blank" rel="noreferrer">
            What is mocked
          </a>
        </nav>
      </div>
    </div>
  );
}

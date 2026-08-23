/**
 * Escalation, at the very top, impossible to scroll past.
 *
 * When nothing fired it says so explicitly rather than rendering nothing. A blank space where
 * a warning would be reads as "checked, all clear", and MediKiosk does not make that claim —
 * the rules are recall-biased detectors, not a clean bill of health (Invariant 3).
 */
import type { Escalation } from '../shared/api';

interface Props {
  escalation: Escalation;
  onSelectFlag: (factIds: string[]) => void;
}

export function RedFlagBanner({ escalation, onSelectFlag }: Props): JSX.Element {
  const { priority, flags } = escalation;

  if (!flags.length) {
    return (
      <div className="flag-banner routine">
        <div className="flag-title" style={{ color: 'var(--ink-3)' }}>
          No emergency rule fired
        </div>
        <div style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5 }}>
          22 deterministic rules were evaluated against the recorded history and none fired.
          This is <strong>not</strong> a statement that the patient is low priority.
        </div>
      </div>
    );
  }

  return (
    <div className={`flag-banner ${priority}`}>
      <div className="flag-title">
        {priority === 'immediate' ? 'Immediate — interrupt triage now' : 'Urgent — see within the hour'}
        {' · '}
        {flags.length} rule{flags.length === 1 ? '' : 's'} fired
      </div>
      {flags.map((flag) => (
        <button
          key={flag.ruleId}
          type="button"
          className="flag-row"
          style={{ border: 0, background: 'transparent', width: '100%', textAlign: 'left', cursor: 'pointer' }}
          onClick={() => onSelectFlag(flag.triggeringFactIds)}
          title="Show the answers that triggered this"
        >
          <span className="flag-id">{flag.ruleId}</span>
          <span>
            <span className="flag-label">{flag.label}</span>
            {' — '}
            <span className="flag-why">{flag.rationale}</span>
          </span>
        </button>
      ))}
    </div>
  );
}

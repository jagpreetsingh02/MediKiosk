/**
 * Severity, as faces.
 *
 * "Rate your pain zero to ten" is meaningless to someone who has never been asked it. The
 * faces are what the patient chooses; the number is what gets recorded, so the physician
 * still receives the 0–10 scale they expect.
 */
import type { Scale } from '../shared/api';
import { FaceIcon } from '../shared/Icon';

interface Props {
  scale: Scale;
  language: string;
  value: number | null;
  onSelect: (value: number) => void;
}

const STEPS = [0, 2, 4, 6, 8, 10];

export function FaceScale({ scale, language, value, onSelect }: Props): JSX.Element {
  const anchors = language === 'hi' && scale.anchors_hi.length ? scale.anchors_hi : scale.anchors_en;

  return (
    <div className="face-scale" role="radiogroup" aria-label="How bad is it?">
      {STEPS.map((step, index) => (
        <button
          key={step}
          type="button"
          className="face-option"
          aria-pressed={value === step}
          onClick={() => onSelect(step)}
        >
          <FaceIcon level={step} />
          <span>{anchors[index] ?? ''}</span>
          <span className="face-number">{step}</span>
        </button>
      ))}
    </div>
  );
}

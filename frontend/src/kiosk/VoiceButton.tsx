/**
 * The microphone.
 *
 * It never becomes the only way to answer, and it never disappears after a failure. When the
 * backend degrades a question to touch, the button stays visible but says so — the patient
 * can try speaking again on the next question, which is what `touchOnly` being per-question
 * means in practice.
 */
import { Icon } from '../shared/Icon';

interface Props {
  supported: boolean;
  listening: boolean;
  interim: string;
  disabled: boolean;
  label: string;
  onStart: () => void;
  onStop: () => void;
}

export function VoiceButton({
  supported,
  listening,
  interim,
  disabled,
  label,
  onStart,
  onStop,
}: Props): JSX.Element {
  if (!supported) {
    return (
      <div className="voice-row">
        <span className="voice-transcript">
          This device cannot listen. Please tap your answer above.
        </span>
      </div>
    );
  }

  return (
    <div className="voice-row">
      <button
        type="button"
        className={`voice-button${listening ? ' listening' : ''}${disabled ? ' unavailable' : ''}`}
        onClick={listening ? onStop : onStart}
        disabled={disabled}
        aria-pressed={listening}
      >
        <Icon name="mic" />
        {listening ? 'Listening… tap to stop' : label}
      </button>
      {interim && <span className="voice-transcript">“{interim}”</span>}
      {disabled && !interim && (
        <span className="voice-transcript">
          I did not catch the last answer — please tap it above. You can speak again on the
          next question.
        </span>
      )}
    </div>
  );
}

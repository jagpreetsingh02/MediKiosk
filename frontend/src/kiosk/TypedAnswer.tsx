/** Typing: the third modality, for a literate patient who prefers a keyboard to a microphone.
 *
 * Enter sends. There is no separate Continue step, because a second confirming tap after an
 * answer is already given teaches a patient that their first action did not register — which
 * is the opposite of what a kiosk should teach. Shift+Enter still makes a newline, for the
 * one free-text question where a patient may want two sentences.
 */
interface Props {
  value: string;
  placeholder: string;
  /** Disabled while the answer is in flight, so a double tap cannot record two facts. */
  busy?: boolean;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
}

export function TypedAnswer({ value, placeholder, busy, onChange, onSubmit }: Props): JSX.Element {
  function send(): void {
    const trimmed = value.trim();
    if (trimmed && !busy) onSubmit(trimmed);
  }

  return (
    <div className="typed-answer">
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            send();
          }
        }}
        placeholder={placeholder}
        aria-label="Type your answer"
      />
      <div className="typed-send-row">
        <span className="typed-hint">Press Enter to send</span>
        <button
          type="button"
          className="btn-primary btn-send"
          disabled={!value.trim() || busy}
          onClick={send}
        >
          {busy ? 'Saving…' : 'Send'}
        </button>
      </div>
    </div>
  );
}

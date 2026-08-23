/** Typing: the third modality, for a literate patient who prefers a keyboard to a microphone. */
interface Props {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}

export function TypedAnswer({ value, placeholder, onChange }: Props): JSX.Element {
  return (
    <div className="typed-answer">
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label="Type your answer"
      />
    </div>
  );
}

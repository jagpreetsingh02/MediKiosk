/**
 * The last screen the patient sees.
 *
 * It states plainly what happens next and what does NOT happen: nothing is sent anywhere
 * until the doctor has read and approved it. That is Invariant 4 written for a patient.
 */
import { useEffect } from 'react';
import { Icon } from '../shared/Icon';
import { useSpeech } from '../shared/useSpeech';

interface Props {
  language: string;
  answered: number;
  documents: number;
  onRestart: () => void;
}

const MESSAGE: Record<string, string> = {
  en: 'Thank you. Your answers are ready for the doctor. Please wait to be called.',
  hi: 'धन्यवाद। आपके जवाब डॉक्टर के लिए तैयार हैं। कृपया अपनी बारी का इंतज़ार कीजिए।',
};

export function DoneScreen({ language, answered, documents, onRestart }: Props): JSX.Element {
  const speech = useSpeech(language);

  useEffect(() => {
    void speech.speak(MESSAGE[language] ?? MESSAGE.en);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="kiosk-panel" style={{ textAlign: 'center' }}>
      <div style={{ color: 'var(--ok)', display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: 120, height: 120 }}>
          <Icon name="check" />
        </div>
      </div>
      <h1 className="kiosk-title" style={{ marginTop: 20 }}>
        {MESSAGE[language] ?? MESSAGE.en}
      </h1>
      <p className="kiosk-lead">
        You answered <strong>{answered}</strong> question{answered === 1 ? '' : 's'}
        {documents > 0 && <> and showed <strong>{documents}</strong> document{documents === 1 ? '' : 's'}</>}.
      </p>
      <div
        style={{
          background: 'var(--paper-2)',
          border: '3px solid var(--line)',
          borderRadius: 'var(--radius-lg)',
          padding: 24,
          fontSize: 21,
          lineHeight: 1.55,
          textAlign: 'left',
          color: 'var(--ink-2)',
        }}
      >
        <strong style={{ color: 'var(--ink)' }}>What happens now</strong>
        <ul style={{ margin: '12px 0 0', paddingLeft: 24 }}>
          <li>The doctor reads what you said, in your own words, before you go in.</li>
          <li>Nothing is saved to your health record until the doctor approves it.</li>
          <li>Everything on this machine is deleted when your visit ends.</li>
        </ul>
      </div>
      <div className="kiosk-actions" style={{ justifyContent: 'center' }}>
        <button type="button" className="btn-secondary" onClick={onRestart}>
          Start a new patient
        </button>
      </div>
    </div>
  );
}

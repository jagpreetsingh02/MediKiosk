/**
 * One question, all three ways to answer it, on one screen.
 *
 * The whole of Module A's patient-facing contract lives in this component: the prompt is
 * spoken aloud, the tap options are always visible, the microphone is offered alongside them
 * rather than instead of them, and a low-confidence transcript re-presents the question with
 * an explanation instead of recording a guess.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Question, VoiceOutcome } from '../shared/api';
import { Icon } from '../shared/Icon';
import { useSpeech } from '../shared/useSpeech';
import { FaceScale } from './FaceScale';
import { TapGrid } from './TapGrid';
import { TypedAnswer } from './TypedAnswer';
import { VoiceButton } from './VoiceButton';

interface Props {
  question: Question;
  voice: VoiceOutcome | null;
  busy: boolean;
  /** Whether the patient granted the `voice` consent scope. When they did not, the
   *  microphone is not offered at all — showing a button that 403s is worse than not
   *  showing it, and the patient explicitly said no. */
  voiceEnabled: boolean;
  onAnswer: (value: unknown) => void;
  onTyped: (value: string) => void;
  onSpoken: (transcript: string, confidence: number, bargeIn: boolean) => void;
  onSkip: () => void;
}

export function QuestionCard({
  question,
  voice,
  busy,
  voiceEnabled,
  onAnswer,
  onTyped,
  onSpoken,
  onSkip,
}: Props): JSX.Element {
  const [selected, setSelected] = useState<string[]>([]);
  const [typed, setTyped] = useState('');
  const speech = useSpeech(question.language);
  const spokenFor = useRef<string | null>(null);

  const multi = question.kind === 'multi_choice';
  const degraded = question.touchOnly || Boolean(voice?.degradedToTouch);

  // Speech SYNTHESIS is always allowed: reading a question aloud captures nothing, so it
  // needs no consent. Only recognition — the microphone — is gated.
  // Read the prompt aloud once per turn. Keyed on turnId, not questionId, so a re-presented
  // question is read again — the patient needs to hear it a second time, not be left in
  // silence wondering what happened.
  useEffect(() => {
    setSelected([]);
    setTyped('');
    if (spokenFor.current === question.turnId) return;
    spokenFor.current = question.turnId;
    const help = question.help ? ` ${question.help}` : '';
    void speech.speak(`${question.prompt}${help}`);
    return () => speech.cancelSpeech();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.turnId]);

  const listen = useCallback(() => {
    speech.cancelSpeech();
    speech.start(({ transcript, confidence, bargeIn }) => {
      onSpoken(transcript, confidence, bargeIn);
    });
  }, [speech, onSpoken]);

  function submitChoice(): void {
    if (question.kind === 'boolean') return;
    if (!selected.length) return;
    onAnswer(multi ? selected : selected[0]);
  }

  return (
    <>
      <div className="kiosk-section-label">
        {question.sectionTitle}
        {question.socrates && ` · ${question.socrates}`}
      </div>

      <h1 className="kiosk-prompt" lang={question.language}>
        {question.prompt}
      </h1>
      {question.help && <p className="kiosk-help">{question.help}</p>}

      {question.translationMissing && (
        <p className="kiosk-help" style={{ color: 'var(--warn)' }}>
          This question is not yet translated into your language and is shown in English.
        </p>
      )}

      <button type="button" className="audio-button" onClick={() => void speech.speak(question.prompt)}>
        <Icon name="speaker" />
        Say it again
      </button>

      {voice?.degradedToTouch && voice.prompt && (
        <div className="voice-degraded" role="status">
          <Icon name="mic" />
          <div>
            <strong>{voice.prompt}</strong>
            {voice.transcript.text && (
              <div style={{ fontSize: 19, marginTop: 8, color: 'var(--ink-2)' }}>
                I heard: “{voice.transcript.text}” — but only{' '}
                {Math.round(voice.transcript.confidence * 100)}% sure, and I will not guess.
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        {question.kind === 'boolean' ? (
          <div className="tap-grid">
            <button type="button" className="tap-option" disabled={busy} onClick={() => onAnswer(true)}>
              <Icon name="check" />
              <span>Yes</span>
            </button>
            <button type="button" className="tap-option" disabled={busy} onClick={() => onAnswer(false)}>
              <Icon name="cross" />
              <span>No</span>
            </button>
          </div>
        ) : question.kind === 'scale' && question.scale ? (
          <FaceScale
            scale={question.scale}
            language={question.language}
            value={selected.length ? Number(selected[0]) : null}
            onSelect={(value) => onAnswer(value)}
          />
        ) : question.options.length ? (
          <TapGrid options={question.options} selected={selected} multi={multi} onSelect={setSelected} />
        ) : (
          <TypedAnswer
            value={typed}
            placeholder="Type here, or use the microphone below"
            onChange={setTyped}
          />
        )}
      </div>

      {question.kind === 'open_text' && question.options.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <p className="kiosk-help" style={{ marginBottom: 12 }}>
            Or describe it in your own words:
          </p>
          <TypedAnswer value={typed} placeholder="Type here…" onChange={setTyped} />
        </div>
      )}

      {voiceEnabled && (
        <>
          <VoiceButton
            supported={speech.supported}
            listening={speech.listening}
            interim={speech.interim}
            disabled={busy || degraded}
            label="Speak my answer"
            onStart={listen}
            onStop={speech.stop}
          />
          {speech.error && (
            <div className="kiosk-error" style={{ marginTop: 12 }}>{speech.error}</div>
          )}
        </>
      )}

      <div className="kiosk-actions">
        {typed.trim() && (
          <button type="button" className="btn-primary" disabled={busy} onClick={() => onTyped(typed.trim())}>
            Send what I typed
          </button>
        )}
        {selected.length > 0 && question.kind !== 'boolean' && question.kind !== 'scale' && (
          <button type="button" className="btn-primary" disabled={busy} onClick={submitChoice}>
            {multi ? `Continue with ${selected.length} selected` : 'Continue'}
          </button>
        )}
        <button type="button" className="btn-quiet" disabled={busy} onClick={onSkip}>
          I would rather not answer
        </button>
      </div>
    </>
  );
}

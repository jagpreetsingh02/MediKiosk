/**
 * The kiosk flow: language → ABHA → consent → interview → documents → done.
 *
 * The component holds no clinical logic. Which question comes next is the backend's decision
 * (the deterministic state machine in Module A), and this file only renders what it is given
 * and posts back what the patient did. If the frontend ever starts deciding what to ask, the
 * invariant that the LLM cannot change question order has quietly become untrue, because the
 * UI would then be a second place where the interview is defined.
 */
import { useCallback, useEffect, useState } from 'react';
import { ApiError, api, setToken, type StepResponse, type VoiceOutcome } from '../shared/api';
import { AbhaLogin } from './AbhaLogin';
import { ConsentGate } from './ConsentGate';
import { DocumentUpload } from './DocumentUpload';
import { DoneScreen } from './DoneScreen';
import { ProgressRail } from './ProgressRail';
import { QuestionCard } from './QuestionCard';
import { LanguagePicker } from './LanguagePicker';

type Stage = 'language' | 'login' | 'consent' | 'interview' | 'documents' | 'done';

export function KioskApp(): JSX.Element {
  const [stage, setStage] = useState<Stage>('language');
  const [language, setLanguage] = useState('en');
  const [sessionRef, setSessionRef] = useState<string | null>(null);
  const [step, setStep] = useState<StepResponse | null>(null);
  const [voice, setVoice] = useState<VoiceOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answered, setAnswered] = useState(0);

  const apply = useCallback((response: StepResponse) => {
    setStep(response);
    setVoice(response.voice ?? null);
    if (response.complete) setStage('documents');
  }, []);

  const guard = useCallback(
    async (work: () => Promise<StepResponse>) => {
      setBusy(true);
      setError(null);
      try {
        apply(await work());
      } catch (exc) {
        setError(exc instanceof ApiError ? exc.message : 'Something went wrong. Please tell the staff.');
      } finally {
        setBusy(false);
      }
    },
    [apply],
  );

  useEffect(() => {
    if (stage !== 'interview' || !sessionRef || step) return;
    void guard(() => api.next(sessionRef));
  }, [stage, sessionRef, step, guard]);

  function restart(): void {
    setToken(null);
    setSessionRef(null);
    setStep(null);
    setVoice(null);
    setAnswered(0);
    setError(null);
    setStage('language');
  }

  const question = step?.question ?? null;

  return (
    <div className="kiosk">
      <div className="mock-banner">
        Demo identity — mock ABHA issuer, synthetic patients only. Not an ABDM integration.
      </div>

      <header className="kiosk-top">
        <span className="kiosk-brand">MediKiosk</span>
        <span className="kiosk-top-spacer" />
        {sessionRef && (
          <span style={{ fontSize: 15, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
            {sessionRef}
          </span>
        )}
        {stage !== 'language' && (
          <button type="button" className="btn-quiet" style={{ minHeight: 52, fontSize: 18 }} onClick={restart}>
            Start over
          </button>
        )}
      </header>

      <main className="kiosk-body">
        {error && <div className="kiosk-error">{error}</div>}

        {stage === 'language' && (
          <LanguagePicker
            onPick={(picked) => {
              setLanguage(picked);
              setStage('login');
            }}
          />
        )}

        {stage === 'login' && (
          <AbhaLogin onAuthenticated={() => setStage('consent')} onBack={() => setStage('language')} />
        )}

        {stage === 'consent' && (
          <ConsentGate
            language={language}
            onGranted={(ref) => {
              setSessionRef(ref);
              setStage('interview');
            }}
            onBack={() => setStage('login')}
          />
        )}

        {stage === 'interview' && question && sessionRef && (
          <QuestionCard
            question={question}
            voice={voice}
            busy={busy}
            onAnswer={(value) => {
              setAnswered((n) => n + 1);
              void guard(() => api.answer(sessionRef, question.turnId, question.questionId, value));
            }}
            onTyped={(value) => {
              setAnswered((n) => n + 1);
              void guard(() => api.answerTyped(sessionRef, question.turnId, question.questionId, value));
            }}
            onSpoken={(transcript, confidence, bargeIn) => {
              void guard(() =>
                api.answerVoice(
                  sessionRef,
                  question.turnId,
                  question.questionId,
                  transcript,
                  confidence,
                  bargeIn,
                ),
              );
            }}
            onSkip={() => void guard(() => api.skip(sessionRef, question.questionId))}
          />
        )}

        {stage === 'interview' && !question && !busy && (
          <div className="kiosk-panel">
            <p className="kiosk-lead">Loading your first question…</p>
          </div>
        )}

        {stage === 'documents' && sessionRef && (
          <DocumentUpload sessionRef={sessionRef} onDone={() => setStage('done')} />
        )}

        {stage === 'done' && (
          <DoneScreen
            language={language}
            answered={answered}
            documents={0}
            onRestart={restart}
          />
        )}
      </main>

      {stage === 'interview' && step && (
        <ProgressRail
          progress={step.progress}
          sections={step.sections}
          currentSectionId={question?.sectionId ?? null}
        />
      )}
    </div>
  );
}

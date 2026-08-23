/**
 * Granular, revocable, audio-explained consent. Nothing is captured until this passes.
 *
 * Two things this screen does that a checkbox does not:
 *  - it reads each scope aloud, and records whether the audio was actually played, so a
 *    consent taken in silence is visible later on the physician's screen;
 *  - every optional scope starts OFF. Pre-ticking an optional consent is how consent theatre
 *    works, and the patient must reach for each one deliberately.
 */
import { useEffect, useState } from 'react';
import { ApiError, api, type ConsentPresentation } from '../shared/api';
import { Icon } from '../shared/Icon';
import { useSpeech } from '../shared/useSpeech';

interface Props {
  language: string;
  onGranted: (sessionRef: string, ayushMode: boolean, grantedScopes: string[]) => void;
  onBack: () => void;
}

export function ConsentGate({ language, onGranted, onBack }: Props): JSX.Element {
  const [presentation, setPresentation] = useState<ConsentPresentation | null>(null);
  const [granted, setGranted] = useState<Set<string>>(new Set());
  const [audioPlayed, setAudioPlayed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const speech = useSpeech(language);

  useEffect(() => {
    api
      .consentPresentation(language)
      .then((body) => {
        setPresentation(body);
        // Required scopes start ON — the patient is here to be seen, and refusing the one
        // mandatory scope means ending the session, which the Cancel button already does.
        setGranted(new Set(body.scopes.filter((s) => s.required).map((s) => s.id)));
      })
      .catch((exc) => setError(exc instanceof ApiError ? exc.message : 'Could not load consent.'));
  }, [language]);

  async function readAll(): Promise<void> {
    if (!presentation) return;
    setAudioPlayed(true);
    await speech.speak(presentation.preamble);
    for (const scope of presentation.scopes) {
      await speech.speak(scope.audio);
    }
  }

  function toggle(id: string, required: boolean): void {
    if (required) return;
    setGranted((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function begin(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const session = await api.createSession(language, [...granted], audioPlayed);
      onGranted(session.sessionRef, session.ayushMode, [...granted]);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not start the session.');
    } finally {
      setBusy(false);
    }
  }

  if (!presentation) {
    return <div className="kiosk-panel"><p className="kiosk-lead">Loading…</p></div>;
  }

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">Before we begin</h1>
      <p className="kiosk-lead">{presentation.preamble}</p>

      <button type="button" className="audio-button" onClick={() => void readAll()}>
        <Icon name="speaker" />
        {speech.listening ? 'Reading…' : 'Read this to me'}
      </button>

      {error && <div className="kiosk-error" style={{ marginTop: 20 }}>{error}</div>}

      <div style={{ marginTop: 26 }}>
        {presentation.scopes.map((scope) => {
          const on = granted.has(scope.id);
          return (
            <div
              key={scope.id}
              className={`consent-scope${on ? ' granted' : ''}${scope.required ? ' required' : ''}`}
            >
              <button
                type="button"
                className={`consent-toggle${on ? ' on' : ''}`}
                aria-pressed={on}
                disabled={scope.required}
                onClick={() => toggle(scope.id, scope.required)}
              >
                {on ? 'Yes' : 'No'}
              </button>
              <div>
                <div className="consent-title">
                  {scope.title}
                  {scope.required && (
                    <span style={{ fontSize: 15, color: 'var(--accent)', marginLeft: 8 }}>
                      (needed to continue)
                    </span>
                  )}
                </div>
                <div className="consent-audio">{scope.audio}</div>
                <button
                  type="button"
                  className="audio-button"
                  onClick={() => { setAudioPlayed(true); void speech.speak(scope.audio); }}
                >
                  <Icon name="speaker" />
                  Read aloud
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="kiosk-actions">
        <button type="button" className="btn-primary" disabled={busy} onClick={() => void begin()}>
          I agree — start
        </button>
        <button type="button" className="btn-quiet" onClick={onBack}>
          Cancel
        </button>
      </div>
      <p style={{ fontSize: 17, color: 'var(--ink-3)', marginTop: 18, lineHeight: 1.5 }}>
        Policy version {presentation.policyVersion}. You can change your mind at any time, and
        anything already recorded under a permission you withdraw is deleted.
      </p>
    </div>
  );
}

/**
 * Granular, revocable, audio-explained consent. Nothing is captured until this passes.
 *
 * Two things this screen does that a checkbox does not:
 *  - it can read the whole page aloud, and records whether the audio was actually played, so
 *    a consent taken in silence is visible later on the physician's screen;
 *  - every optional scope starts OFF. Pre-ticking an optional consent is how consent theatre
 *    works, and the patient must reach for each one deliberately.
 *
 * WHY IT LOOKS DIFFERENT NOW. The first version gave each of the five scopes a full-width
 * card, a giant Yes/No button and its own Read aloud control. It was honest and it was
 * unusable: five Read aloud buttons is five decisions about which button to press before any
 * decision about consent, and a wall of equally-sized Yes/No cards hides the one thing that
 * actually matters — that exactly one permission is required and the other four are free
 * choices. The split into Required and Optional is not decoration; it is the information the
 * patient needs in order to consent to anything.
 *
 * Granularity is unchanged. Every scope is still separately refusable, still off by default,
 * still recorded individually. Only the presentation got smaller.
 */
import { useEffect, useState } from 'react';
import { ApiError, api, type ConsentPresentation } from '../shared/api';
import { Icon } from '../shared/Icon';
import { unlock } from '../shared/tts';
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
  const [expanded, setExpanded] = useState<string | null>(null);
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

  async function readPage(): Promise<void> {
    if (!presentation) return;
    unlock();
    setAudioPlayed(true);
    if (speech.speaking) {
      speech.cancelSpeech();
      return;
    }
    // One control reads the whole page, in order, exactly as a person would read it out.
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
    return (
      <div className="kiosk-panel">
        <p className="kiosk-lead">Loading…</p>
      </div>
    );
  }

  const required = presentation.scopes.filter((s) => s.required);
  const optional = presentation.scopes.filter((s) => !s.required);

  return (
    <div className="kiosk-panel">
      <div className="consent-head">
        <div>
          <h1 className="kiosk-title">Your permission</h1>
          <p className="consent-lead">
            Everything you tell me is deleted when your visit ends. Only the doctor sees it.
          </p>
        </div>
        {speech.canSpeak && (
          <button
            type="button"
            className={`audio-button${speech.speaking ? ' speaking' : ''}`}
            onClick={() => void readPage()}
          >
            <Icon name="speaker" />
            {speech.speaking ? 'Stop' : 'Hear this page'}
          </button>
        )}
      </div>

      {speech.speechNotice && (
        <p className="kiosk-help" style={{ color: 'var(--warn)' }}>
          {speech.speechNotice}
        </p>
      )}
      {error && (
        <div className="kiosk-error" style={{ marginTop: 16 }}>
          {error}
        </div>
      )}

      <div className="consent-group-label">Needed to continue</div>
      {required.map((scope) => (
        <div key={scope.id} className="consent-row required">
          <Icon name="check" />
          <div className="consent-row-body">
            <div className="consent-row-title">{scope.short ?? scope.title}</div>
            <div className="consent-row-detail">{scope.title}</div>
          </div>
        </div>
      ))}

      <div className="consent-group-label">Optional — your choice</div>
      {optional.map((scope) => {
        const on = granted.has(scope.id);
        const open = expanded === scope.id;
        return (
          <div key={scope.id} className={`consent-row${on ? ' granted' : ''}`}>
            <button
              type="button"
              role="switch"
              aria-checked={on}
              aria-label={scope.short ?? scope.title}
              className={`consent-switch${on ? ' on' : ''}`}
              onClick={() => toggle(scope.id, scope.required)}
            >
              <span className="consent-knob" />
            </button>
            <div className="consent-row-body">
              <div className="consent-row-title">{scope.short ?? scope.title}</div>
              {open && <div className="consent-row-detail">{scope.audio}</div>}
              <button
                type="button"
                className="consent-why"
                onClick={() => setExpanded(open ? null : scope.id)}
              >
                {open ? 'Hide' : 'What does this mean?'}
              </button>
            </div>
          </div>
        );
      })}

      <div className="kiosk-actions">
        <button type="button" className="btn-primary" disabled={busy} onClick={() => void begin()}>
          {busy ? 'Starting…' : 'Start intake'}
        </button>
        <button type="button" className="btn-quiet" onClick={onBack}>
          Cancel
        </button>
      </div>

      <p className="consent-footnote">
        You can change your mind at any time. Anything recorded under a permission you withdraw
        is deleted. Policy version {presentation.policyVersion}.
      </p>
    </div>
  );
}

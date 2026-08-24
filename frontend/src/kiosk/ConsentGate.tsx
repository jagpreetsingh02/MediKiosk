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
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { Button, Skeleton, Toggle } from '../design/ui';
import { expand, reduced, rise, stagger } from '../design/motion';

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
  const prefersReduced = useReducedMotion() ?? false;
  const riseV = reduced(prefersReduced, rise);
  const expandV = reduced(prefersReduced, expand);

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
      <div className="mk-stack" style={{ gap: 'var(--mk-space-5)' }} aria-busy="true">
        <span className="mk-sr-only" role="status">Loading your permissions</span>
        <Skeleton height={44} width="60%" radius="var(--mk-radius-md)" />
        <Skeleton height={92} radius="var(--mk-radius-lg)" />
        <Skeleton height={240} radius="var(--mk-radius-lg)" />
      </div>
    );
  }

  const required = presentation.scopes.filter((s) => s.required);
  const optional = presentation.scopes.filter((s) => !s.required);

  return (
    <motion.div variants={stagger(0.05)} initial="hidden" animate="visible">
      <motion.p className="kx-eyebrow" variants={riseV}>
        Before we begin
      </motion.p>
      <motion.h1 className="kx-title" variants={riseV}>
        Your permission
      </motion.h1>
      <motion.p className="kx-lead" variants={riseV}>
        Everything you tell us is deleted when your visit ends. Only the doctor sees it.
      </motion.p>

      {speech.canSpeak && (
        <motion.div variants={riseV} style={{ marginTop: 'var(--mk-space-5)' }}>
          <Button
            variant="secondary"
            icon={<Icon name="speaker" />}
            onClick={() => void readPage()}
            aria-live="polite"
          >
            {speech.speaking ? 'Stop reading' : 'Hear this page'}
          </Button>
        </motion.div>
      )}

      {speech.speechNotice && (
        <p className="kx-notice" role="status">
          {speech.speechNotice}
        </p>
      )}
      {error && <div className="kiosk-error" style={{ marginTop: 16 }}>{error}</div>}

      <motion.div variants={riseV} style={{ marginTop: 'var(--mk-space-8)' }}>
        <div className="kx-consent-group">
          <div className="kx-consent-group__head">
            <span>Needed to continue</span>
            <span>Always on</span>
          </div>
          {required.map((scope) => (
            <div key={scope.id} className="kx-consent-required">
              <span className="kx-consent-required__check" aria-hidden="true">
                <Icon name="check" />
              </span>
              <div>
                <div className="mk-toggle__title">{scope.short ?? scope.title}</div>
                <div className="mk-toggle__hint">{scope.title}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="kx-consent-group">
          <div className="kx-consent-group__head">
            <span>Optional — your choice</span>
            <span>{granted.size - required.length} on</span>
          </div>
          <div className="kx-consent-list">
            {optional.map((scope) => {
              const on = granted.has(scope.id);
              const open = expanded === scope.id;
              return (
                <div key={scope.id}>
                  <Toggle
                    checked={on}
                    onChange={() => toggle(scope.id, scope.required)}
                    title={scope.short ?? scope.title}
                    hint={scope.title}
                  />
                  <div className="kx-consent-why">
                    <button
                      type="button"
                      className="kx-linkish"
                      aria-expanded={open}
                      onClick={() => setExpanded(open ? null : scope.id)}
                    >
                      {open ? 'Hide' : 'What does this mean?'}
                    </button>
                    <AnimatePresence initial={false}>
                      {open && (
                        <motion.p
                          className="kx-consent-detail"
                          variants={expandV}
                          initial="hidden"
                          animate="visible"
                          exit="exit"
                        >
                          <span>{scope.audio}</span>
                        </motion.p>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </motion.div>

      <motion.div className="kx-actions" variants={riseV}>
        <Button size="lg" loading={busy} onClick={() => void begin()}>
          Start intake
        </Button>
        <Button variant="quiet" onClick={onBack}>
          Cancel
        </Button>
      </motion.div>

      <motion.p className="kx-footnote" variants={riseV}>
        You can change your mind at any time. Anything recorded under a permission you withdraw
        is deleted. Policy version {presentation.policyVersion}.
      </motion.p>
    </motion.div>
  );
}

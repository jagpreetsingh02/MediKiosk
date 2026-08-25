/**
 * "Waking the server" — the honest name for what a cold Render free-tier boot looks like.
 *
 * Without this, the very first request of a page load can sit for 30-60 seconds with nothing
 * on screen but whatever spinner that call already had — built assuming a warm server, so a
 * patient or judge watching it reads "broken," not "busy." This says the true thing instead.
 *
 * It only ever appears for the first request `shared/api.ts` makes (see `subscribeToWakeState`
 * there for why) and disappears the moment that request actually resolves — not on a guessed
 * timeout, so it never lingers past a wake that already finished or vanishes before a slow one
 * has.
 */
import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { subscribeToWakeState } from '../shared/api';
import { springSoft } from './motion';

export function WakeBanner(): JSX.Element | null {
  const [waking, setWaking] = useState(false);

  useEffect(() => subscribeToWakeState(setWaking), []);

  return (
    <AnimatePresence>
      {waking && (
        <motion.div
          className="mk-wakebanner"
          role="status"
          aria-live="polite"
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16, transition: { duration: 0.16 } }}
          transition={springSoft}
        >
          <span className="mk-wakebanner__spinner" aria-hidden="true" />
          <span>
            <strong>Waking the server…</strong> this can take up to a minute on first load.
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

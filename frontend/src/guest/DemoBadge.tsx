/**
 * The DEMO / SYNTHETIC DATA badge, and the Reset control beside it.
 *
 * MOUNTED ONCE ABOVE THE ROUTER, like `DatabaseBadge`, so every screen reachable in demo
 * mode carries it by construction. A per-screen badge is a badge that some screen forgets,
 * and the screen that forgets is the one where a judge photographs synthetic clinical data
 * with nothing on it saying so.
 *
 * It is deliberately styled like the mock-identity banner rather than like the product:
 * chrome that blends in is chrome nobody reads, and this has to survive being screenshotted
 * and shown to someone who was not in the room. Violet rather than rose or amber — the two
 * existing hazard bars are the local-database warning and the mock-ABHA notice, and a third
 * thing in the same colour as either would be read as the same thing.
 *
 * RESET IS HERE, not buried in a settings screen, because it is used between demo runs while
 * standing in front of people. It asks for confirmation once: a mis-click that wipes the
 * record mid-explanation is worse than one extra tap.
 */
import { useEffect, useState } from 'react';
import * as guest from './session';

export function DemoBadge(): JSX.Element | null {
  const [session, setSession] = useState(guest.current());
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => guest.subscribe(setSession), []);

  // Reserve layout space, exactly as the local-database badge does, so the bar never sits on
  // top of the nav on any screen.
  useEffect(() => {
    const root = document.documentElement;
    if (session) root.dataset.demoMode = 'true';
    else delete root.dataset.demoMode;
    return () => {
      delete root.dataset.demoMode;
    };
  }, [session]);

  if (!session) return null;

  async function doReset(): Promise<void> {
    setBusy(true);
    try {
      await guest.reset();
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mk-demobadge" role="note" data-testid="demo-badge">
      <span className="mk-demobadge__dot" aria-hidden="true" />
      <strong>Demo — synthetic data</strong>
      <span className="mk-demobadge__text">
        Nothing here is a real patient. This record is kept separate from clinical data.
      </span>

      {confirming ? (
        <span className="mk-demobadge__confirm">
          <span>Start the demo over?</span>
          <button type="button" className="mk-demobadge__btn" onClick={doReset} disabled={busy}>
            {busy ? 'Resetting…' : 'Yes, reset'}
          </button>
          <button
            type="button"
            className="mk-demobadge__btn mk-demobadge__btn--quiet"
            onClick={() => setConfirming(false)}
            disabled={busy}
          >
            Keep going
          </button>
        </span>
      ) : (
        <button
          type="button"
          className="mk-demobadge__btn"
          onClick={() => setConfirming(true)}
        >
          Reset demo
        </button>
      )}
    </div>
  );
}

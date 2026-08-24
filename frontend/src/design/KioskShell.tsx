/**
 * The kiosk frame: ambient ground, brand rail, section progress, content stage.
 *
 * Everything the patient sees sits inside this. It exists so no individual screen
 * has to think about the page furniture, and so the *stage* — the region that
 * swaps between screens — is a single element that `AnimatePresence` can animate
 * without the header and progress moving with it.
 *
 * The mock-identity banner stays. It is the one piece of chrome that is allowed
 * to be visually loud, because a synthetic-data disclaimer that a jury can miss
 * is a disclaimer that is not doing its job.
 */
import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { rise } from './motion';

interface Props {
  /** Section progress rail. Hidden before the interview begins. */
  progress?: ReactNode;
  /** Right-hand header slot — "Start over", the records chip, diagnostics. */
  actions?: ReactNode;
  /** Sub-brand line under the wordmark, e.g. the patient's name once known. */
  context?: ReactNode;
  children: ReactNode;
  /** Widen the stage for screens that hold a grid rather than a single question. */
  wide?: boolean;
  onPointerDownCapture?: () => void;
}

export function KioskShell({
  progress,
  actions,
  context,
  children,
  wide = false,
  onPointerDownCapture,
}: Props) {
  return (
    <div className="kx" onPointerDownCapture={onPointerDownCapture}>
      <div className="kx-disclaimer" role="note">
        <span className="kx-disclaimer__dot" aria-hidden="true" />
        Demo identity — mock ABHA issuer, synthetic patients only. Not an ABDM integration.
      </div>

      <header className="kx-header">
        <div className="kx-brand">
          <BrandMark />
          <div className="kx-brand__text">
            <span className="kx-brand__name">MediKiosk</span>
            {context && <span className="kx-brand__context">{context}</span>}
          </div>
        </div>
        {progress && <div className="kx-header__progress">{progress}</div>}
        {actions && <div className="kx-header__actions">{actions}</div>}
      </header>

      <main className={`kx-stage${wide ? ' kx-stage--wide' : ''}`}>{children}</main>
    </div>
  );
}

/**
 * The mark: a pulse line closing into a ring.
 *
 * Drawn rather than imported so it inherits `currentColor` and stays crisp at any
 * size. The reading is deliberate — a vital sign becoming a continuous record,
 * which is what longitudinal clinical memory is.
 */
export function BrandMark({ size = 34 }: { size?: number }) {
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
      className="kx-mark"
      variants={rise}
      initial="hidden"
      animate="visible"
    >
      <circle
        cx="20"
        cy="20"
        r="17"
        stroke="var(--mk-accent)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="88 20"
        transform="rotate(-90 20 20)"
      />
      <path
        d="M9 20.5h5.2l2.6-6.4 3.4 12 2.8-7.1 2 1.5H31"
        stroke="var(--mk-ink-strong)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </motion.svg>
  );
}

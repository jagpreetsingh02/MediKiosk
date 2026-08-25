/**
 * The nav, everywhere.
 *
 * This is the hero's navigation — mark on the left, a glass pill in the middle, a glass round
 * on the right — generalised so every screen after the hero wears the same header. That is
 * most of what stops a route change feeling like an application change: the thing at the top
 * of the window keeps its position, its material and its proportions from the landing page all
 * the way into the physician workspace.
 *
 * The middle slot is what varies, because "where am I" means different things per surface:
 *
 *   hero        three links, one active
 *   kiosk       the section progress rail — the patient's version of "where am I"
 *   clinical    the view switcher — the physician's version of the same question
 *
 * All three are the same pill in the same place. A patient never reads the word "progress" and
 * a physician never reads the word "step"; they both just see the middle of the bar telling
 * them where they are.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface Props {
  /** Sub-brand line under the wordmark — the patient's name, the signed-in clinician. */
  context?: ReactNode;
  /** The centre pill. Progress on the kiosk, view switching in the workspace. */
  center?: ReactNode;
  /** Right-hand slot — "Start over", diagnostics, the account round. */
  actions?: ReactNode;
  /** Compact bar for the dense surface. */
  dense?: boolean;
}

export function AppNav({ context, center, actions, dense = false }: Props) {
  return (
    <header className={`mk-nav${dense ? ' mk-nav--dense' : ''}`}>
      <Link to="/" className="mk-nav__brand" aria-label="MediKiosk home">
        <BrandMark size={dense ? 26 : 32} />
        <span className="mk-nav__brand-text">
          <span className="mk-nav__name">MediKiosk</span>
          {context && <span className="mk-nav__context">{context}</span>}
        </span>
      </Link>

      {center && <div className="mk-nav__center">{center}</div>}

      {actions && <div className="mk-nav__actions">{actions}</div>}
    </header>
  );
}

/**
 * The mark: a pulse line closing into a ring.
 *
 * Drawn rather than imported so it inherits `currentColor` and stays crisp at any size. The
 * reading is deliberate — a vital sign becoming a continuous record, which is what
 * longitudinal clinical memory is. On the glass ground it is monochrome like the hero's
 * logo, with the ring at reduced opacity so the line reads first.
 */
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
      className="mk-mark"
    >
      <circle
        cx="20"
        cy="20"
        r="17"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="88 20"
        transform="rotate(-90 20 20)"
      />
      <path
        d="M9 20.5h5.2l2.6-6.4 3.4 12 2.8-7.1 2 1.5H31"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * The front door — the hero from `ui/`, now the entry point of the product.
 *
 * The original in `ui/` is untouched and stays that way. This is that page, with its design,
 * its layout, its animations and its interaction behaviour carried over exactly: the same glass
 * nav pill, the same badge pill above the same 1.05-leading, -0.05em-tracked headline, the same
 * pill CTA, the same two-column stat foot, the same 300ms icon-swap hamburger and the same
 * 500ms mobile overlay. What changes is what it *says* and where its controls go — a landing
 * page for a wellness brand had to become the landing page for this one, and its button has to
 * open the intake rather than sit inert.
 *
 * Three things earned a deliberate substitution, each for a reason beyond taste:
 *
 *   The badge pill. It held four stock portraits and "our path to natural wellness". It now
 *   holds the sentence that is not allowed to move: MediKiosk does not diagnose. That line is a
 *   product rule, not copy — it must be above the fold on the first screen — and the badge is
 *   the element that sits above the fold on the first screen. Same pill, same faces, same type.
 *
 *   The faces. Four remote Pexels URLs became four drawn avatars at identical size, overlap and
 *   border. A kiosk is expected to run with no network, and four broken images in the first
 *   element a patient sees is not a first impression worth keeping.
 *
 *   The stats. Two invented wellness metrics became two true statements about this system.
 *
 * The background video is not here. It lives in `design/Ambient.tsx`, mounted once above the
 * router for the whole application — so the footage the patient sees behind this headline is
 * the same element, on the same frame, still playing, when they reach the consent screen.
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as guest from '../guest/session';

import { AVATARS } from './avatars';
import './hero.css';

const NAV_LINKS = [
  { name: 'Home', to: '/', active: true },
  { name: 'Physician review', to: '/physician', active: false },
  { name: 'Demo', to: '/demo', active: false },
];

export function Hero(): JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const [startingDemo, setStartingDemo] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function startDemo(): Promise<void> {
    setStartingDemo(true);
    setDemoError(null);
    try {
      await guest.start();
      // Straight into the intake, which is what "try it" means. The demo badge is mounted
      // above the router, so it is already on screen when the next surface paints.
      navigate('/intake');
    } catch {
      // Never a raw error on the front door. Building a guest record runs real OCR and real
      // ASR, so on a cold backend it genuinely can take a while or time out.
      setDemoError('The demo could not start just now. Please try again in a moment.');
      setStartingDemo(false);
    }
  }

  return (
    <div className="hx">
      <nav className="hx-nav">
        {/* The mark is MediKiosk's own — a pulse line closing into a ring — drawn at the
            original's dimensions and weight so the corner of the screen keeps its balance. */}
        <Link to="/" className="hx-brand" aria-label="MediKiosk home">
          <svg
            className="hx-brand__mark"
            viewBox="0 0 40 40"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
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
          <span className="hx-brand__name">MediKiosk</span>
        </Link>

        <div className="hx-links liquid-glass">
          {NAV_LINKS.map((link) => (
            <Link key={link.name} to={link.to} data-active={link.active || undefined}>
              {link.name}
            </Link>
          ))}
        </div>

        <div className="hx-nav__right">
          <Link to="/physician" className="hx-round liquid-glass" aria-label="Staff sign in">
            <UserIcon />
          </Link>
        </div>

        <div className="hx-burger-wrap">
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="hx-round hx-burger liquid-glass"
            aria-expanded={menuOpen}
            aria-label="Toggle navigation menu"
          >
            <span className="hx-burger__icons">
              <MenuIcon className="hx-burger__menu" />
              <CloseIcon className="hx-burger__close" />
            </span>
          </button>
        </div>
      </nav>

      <div className="hx-sheet" data-open={menuOpen}>
        <div className="hx-sheet__inner">
          {NAV_LINKS.map((link) => (
            <Link key={`m-${link.name}`} to={link.to} onClick={() => setMenuOpen(false)}>
              {link.name}
            </Link>
          ))}
          <div className="hx-sheet__account">
            <span className="hx-round liquid-glass">
              <UserIcon />
            </span>
            <span>Staff</span>
          </div>
        </div>
      </div>

      <main className="hx-main" data-dimmed={menuOpen}>
        <div className="hx-top">
          {/* Invariant 1, on the first screen, above the fold, in the first element. */}
          <div className="hx-badge liquid-glass">
            <span className="hx-badge__faces">
              {AVATARS.map((avatar) => (
                <Avatar key={avatar.id} {...avatar} />
              ))}
            </span>
            <span className="hx-badge__text">
              does not diagnose — it prepares your history
            </span>
          </div>

          {/* `lx-title` is kept on the heading. The browser suite identifies the landing
              screen by it, and a class name is not a design decision. */}
          <h1 className="hx-title lx-title">
            Your History,
            <br />
            <em>Remembered</em>
          </h1>

          <p className="hx-sub">Ready before you meet the doctor.</p>

          <Link to="/intake" className="hx-cta liquid-glass">
            Start
          </Link>
          <p className="hx-cta-note">Speak, tap or type — in your own language.</p>

          {/* No account, no personal details, no ABHA. Creates a synthetic record with a
              history already in it, so the brief has something to show immediately. */}
          <button
            type="button"
            className="hx-cta-secondary"
            onClick={startDemo}
            disabled={startingDemo}
          >
            {startingDemo ? 'Setting up the demo…' : 'Try demo'}
          </button>
          {demoError && <p className="hx-cta-note">{demoError}</p>}

          {/* The patient's own way back in, after a visit. Quiet: it is for returning
              patients, not the primary action on the front door. */}
          <p className="hx-cta-note">
            Been seen already?{' '}
            <Link to="/patient/me" className="hx-inline-link">
              See your records
            </Link>
          </p>
        </div>

        <div className="hx-stats">
          <div className="hx-stat">
            {/* The 1-3-5 triangular dot pattern, at the original's coordinates. */}
            <span className="hx-glyph" aria-hidden="true">
              <span style={{ top: '3px', left: '8.75px' }} />
              <span style={{ top: '9px', left: '4.75px' }} />
              <span style={{ top: '9px', left: '8.75px' }} />
              <span style={{ top: '9px', left: '12.75px' }} />
              <span style={{ top: '15px', left: '0.75px' }} />
              <span style={{ top: '15px', left: '4.75px' }} />
              <span style={{ top: '15px', left: '8.75px' }} />
              <span style={{ top: '15px', left: '12.75px' }} />
              <span style={{ top: '15px', left: '16.75px' }} />
            </span>
            <span className="hx-stat__value">10 Languages</span>
            <span className="hx-stat__label">Speak, tap or type</span>
          </div>

          <div className="hx-stat">
            {/* The 3×3 checkerboard, same cells lit as the original. */}
            <span className="hx-glyph hx-glyph--grid" aria-hidden="true">
              <span />
              <span data-off="true" />
              <span />
              <span data-off="true" />
              <span />
              <span data-off="true" />
              <span />
              <span data-off="true" />
              <span />
            </span>
            <span className="hx-stat__value">Every Line</span>
            <span className="hx-stat__label">Traceable to its source</span>
          </div>
        </div>
      </main>
    </div>
  );
}

/* The three icons the original takes from lucide-react, drawn inline at the same
   1.5 stroke weight. Inline rather than imported so the first screen has no
   dependency to resolve before it can paint. */

function UserIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="10" r="3" />
      <path d="M6.2 19.2a6.5 6.5 0 0 1 11.6 0" strokeLinecap="round" />
    </svg>
  );
}

function MenuIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

function Avatar({ from, to, glyph }: { id: string; from: string; to: string; glyph: string }): JSX.Element {
  return (
    <svg className="hx-badge__face" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id={`av-${glyph}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={from} />
          <stop offset="100%" stopColor={to} />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="16" fill={`url(#av-${glyph})`} />
      <circle cx="16" cy="13" r="4.6" fill="rgba(255,255,255,0.85)" />
      <path d="M6.5 30a9.8 9.8 0 0 1 19 0Z" fill="rgba(255,255,255,0.85)" />
    </svg>
  );
}

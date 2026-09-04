/**
 * The one piece of chrome that never unmounts.
 *
 * It is rendered *outside* `<Routes>` in `main.tsx`, which is the entire trick:
 * React keeps the same DOM node across every navigation, so the bar does not
 * re-mount, does not re-run its entrance, and does not flash. Navigating from
 * the landing page to the physician review moves the underline and nothing
 * else — which is what "one application rather than separate web pages"
 * actually means in implementation terms.
 *
 * WHY THE KIOSK IS EXCLUDED, AND WHY THAT IS NOT AN INCONSISTENCY.
 * `/intake` is a patient standing at a machine, mid-interview, holding their
 * own prescription. Two things follow. First, a global bar offering "Physician
 * review" puts a one-tap route into the clinical surface on a device a patient
 * is holding — ADR-0008 keeps those two surfaces apart for good reasons and a
 * nav link is not worth reopening them. Second, the kiosk already has a header
 * carrying its own progress rail and session actions, and stacking a second bar
 * above it costs 64px of a touch surface to say the word MediKiosk twice.
 *
 * So the kiosk keeps its own header — restyled to the identical glass, the
 * identical rule, the identical mark — and the continuity the brief asks for is
 * delivered by the design system rather than by a shared DOM node. Nothing
 * "visually resets": the bar a patient sees is the bar a judge just left.
 */
import { NavLink, useLocation } from 'react-router-dom';
import { BrandMark } from './KioskShell';

interface Entry {
  to: string;
  label: string;
}

const ENTRIES: Entry[] = [
  { to: '/', label: 'Overview' },
  { to: '/demo', label: 'Demo & jury' },
  { to: '/physician', label: 'Physician review' },
];

export function TopBar(): JSX.Element | null {
  const { pathname } = useLocation();

  // The kiosk owns its own chrome. See the note above.
  if (pathname.startsWith('/intake')) return null;

  return (
    <header className="mk-topbar" data-route={pathname}>
      <div className="mk-topbar__inner">
        <NavLink to="/" className="mk-topbar__brand" aria-label="MediKiosk — overview">
          <BrandMark size={28} />
          <span className="mk-topbar__word">MediKiosk</span>
        </NavLink>

        <nav className="mk-topbar__nav" aria-label="Primary">
          {ENTRIES.map((entry) => (
            <NavLink
              key={entry.to}
              to={entry.to}
              end={entry.to === '/'}
              className={({ isActive }) =>
                `mk-topbar__link${isActive ? ' is-active' : ''}`
              }
            >
              {entry.label}
              {/* The moving indicator is a child of the link rather than one
                  shared absolutely-positioned element: a shared element has to
                  measure the DOM on every route change and gets it wrong the
                  first time, before fonts have settled. */}
              <span className="mk-topbar__marker" aria-hidden="true" />
            </NavLink>
          ))}
        </nav>

        <div className="mk-topbar__end">
          <a
            className="mk-topbar__meta"
            href="/about"
            target="_blank"
            rel="noreferrer"
            title="Exactly which parts of this build are mocked"
          >
            What is mocked
          </a>
          <NavLink to="/intake" className="mk-topbar__cta">
            Start intake
          </NavLink>
        </div>
      </div>
    </header>
  );
}

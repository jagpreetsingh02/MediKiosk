/**
 * One product, four surfaces, one ground.
 *
 *   /          the hero — the front door, ported from `ui/`
 *   /intake    the kiosk (the patient's device)
 *   /physician the review workspace
 *   /demo      one-click synthetic cases for a jury
 *
 * They used to share the typed API client and nothing else, on the theory that a surface built
 * for a non-literate patient and one built for a time-pressed clinician want opposite things
 * from every component they might have in common. Half of that is still true and is why the
 * two surfaces run at different densities. The other half — that they should therefore *look*
 * unrelated — turned out to be wrong in practice: a patient who taps Start on the landing page
 * and lands somewhere that shares none of its colours, type or motion has, as far as they can
 * tell, been handed to a different piece of software mid-consultation. See ADR-0013.
 *
 * So everything below the router now sits on one ground and is built from one material.
 *
 * TWO THINGS ARE MOUNTED ABOVE `Routes`, AND BOTH HAVE TO BE:
 *
 *   `Ambient` — the background video. If each route rendered its own, every navigation would
 *   restart the footage from frame zero, and the ground would visibly cut. Mounted once, it
 *   simply never unmounts; it only changes depth. That single element is the strongest
 *   continuity cue in the product.
 *
 *   `ToastProvider` — already was, and stays: a toast raised by a commit must survive the
 *   navigation that follows it.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';

import { KioskApp } from './kiosk/KioskApp';
import { PhysicianApp } from './physician/PhysicianApp';
import { DemoLauncher } from './shared/DemoLauncher';
import { BriefRoute } from './brief/BriefRoute';
import { SignIn } from './account/SignIn';
import { PatientPortal } from './patient/PatientPortal';
import { Hero } from './hero/Hero';
import { ToastProvider } from './design/ui';
import { Ambient, type AmbientDepth } from './design/Ambient';
import { DatabaseBadge } from './design/DatabaseBadge';
import { WakeBanner } from './design/WakeBanner';
import { DemoBadge } from './guest/DemoBadge';
import { reduced, route as routeVariants } from './design/motion';

// Fonts are self-hosted through @fontsource, never linked from a CDN: the kiosk is expected to
// run with no network at all, and a webfont that silently fails to load takes the whole
// typographic hierarchy down with it. Inter is the hero's face and is now the product's only
// Latin face — the display/UI split it used to have is carried by weight and tracking instead,
// which is exactly how the hero does it.
import '@fontsource-variable/inter';
import '@fontsource/noto-sans-devanagari/400.css';
import '@fontsource/noto-sans-devanagari/600.css';
import '@fontsource/noto-sans-tamil/400.css';
import '@fontsource/noto-sans-tamil/600.css';

// Legacy surface styles FIRST, so the new system wins every collision. They are still loaded
// because screens land one at a time and the un-rebuilt ones still reference their classes;
// their variables are now aliases onto the shared tokens, so they follow the ground rather
// than fighting it.
import './styles/tokens.css';
import './styles/kiosk.css';
import './styles/physician.css';

// The design system. `theme` is FIRST and is the only file holding a raw colour value;
// `tokens` adds everything that is not a colour; `base` sets the document. Everything below
// reads from those three and defines no palette of its own — `make lint` fails the build if
// a literal appears outside `theme.css`.
import './design/theme.css';
import './design/tokens.css';
import './design/base.css';
import './design/ambient.css';
import './design/glass.css';
import './design/nav.css';
import './design/wakebanner.css';
import './brief/brief.css';
import './guest/demo.css';
import './account/account.css';
import './patient/patient.css';
import './design/primitives.css';
import './styles/kiosk-v2.css';
import './styles/physician-v2.css';

/**
 * How far into the product each route sits, which is how much the ground recedes behind it.
 * The hero gets the footage at full strength because it has almost nothing on top of it; the
 * workspace gets it at a fifth, because dense evidence has to win over atmosphere.
 */
const DEPTH: Record<string, AmbientDepth> = {
  '/': 'hero',
  '/intake': 'surface',
  '/demo': 'surface',
  '/physician': 'deep',
  '/brief': 'deep',
  '/sign-in': 'surface',
  '/patient': 'surface',
  '/patient/me': 'surface',
};

function Shell(): JSX.Element {
  const location = useLocation();
  const prefersReduced = useReducedMotion() ?? false;
  const variants = reduced(prefersReduced, routeVariants);
  const depth = DEPTH[location.pathname] ?? 'surface';

  return (
    <>
      <Ambient depth={depth} />

      {/* Renders nothing against Supabase. Mounted above `Routes` so there is no surface a
          local-database demo could be presented from without it. */}
      <DatabaseBadge />

      {/* Renders nothing once the first request has ever resolved. Mounted above `Routes` so
          a cold Render boot is visible no matter which screen the page happens to land on. */}
      <WakeBanner />

      {/* Renders nothing outside demo mode. Mounted above `Routes` for the same reason as
          the database badge: a per-screen badge is one some screen forgets, and that screen
          is where synthetic clinical data gets photographed with nothing saying so. */}
      <DemoBadge />

      {/* `mode="wait"` so the outgoing surface is gone before the incoming one commits.
          Overlapping them cross-fades two full screens through each other, which on a moving
          background reads as a glitch rather than a transition. */}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={location.pathname}
          className="mk-route"
          variants={variants}
          initial="hidden"
          animate="visible"
          exit="exit"
        >
          <Routes location={location}>
            <Route path="/" element={<Hero />} />
            <Route path="/intake" element={<KioskApp />} />
            <Route path="/physician" element={<PhysicianApp />} />
            <Route path="/demo" element={<DemoLauncher />} />
            {/* The Clinical Intelligence Brief. Same payload, two audiences — the
                `?patient` flag picks the grouping, not a different assembly. */}
            <Route path="/brief" element={<BriefRoute />} />
            {/* A stub, labelled as one on the screen itself. See account/SignIn.tsx. */}
            <Route path="/sign-in" element={<SignIn />} />
            {/* The patient reads their OWN record here, after a physician has confirmed it.
                Identity is the mock ABHA IdP, unchanged. */}
            <Route path="/patient/:patientRef" element={<PatientPortal />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </motion.div>
      </AnimatePresence>
    </>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);

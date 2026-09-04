/**
 * Four surfaces, one bundle, chosen by route.
 *
 *   /          landing — the argument, the figure, the disclaimer
 *   /intake    the kiosk (the patient's device)
 *   /physician the review screen
 *   /demo      one-click synthetic cases for a jury
 *
 * They share the typed API client, the Frostwork material system, and nothing
 * else — deliberately, because a surface built for a non-literate patient and
 * one built for a time-pressed clinician want opposite things from every
 * component they would otherwise have in common (ADR-0008).
 *
 * `<TopBar />` sits OUTSIDE `<Routes>`, and that placement is the whole reason
 * navigation feels continuous: React keeps the same DOM node across every route
 * change, so the bar never unmounts, never replays its entrance, and never
 * flashes. `<RouteStage>` inside it animates only the part that actually
 * changed. Moving the bar inside `<Routes>` would undo both.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { KioskApp } from './kiosk/KioskApp';
import { PhysicianApp } from './physician/PhysicianApp';
import { DemoLauncher } from './shared/DemoLauncher';
import { Landing } from './shared/Landing';
import { RouteStage } from './design/RouteStage';
import { TopBar } from './design/TopBar';
import { ToastProvider } from './design/ui';

// Fonts are self-hosted through @fontsource, never linked from a CDN: the kiosk
// is expected to run with no network at all, and a webfont that silently fails
// to load takes the whole typographic hierarchy down with it.
//
// Space Grotesk stands in for Neue Machina, which is licensed per-project and
// is not committed — see frontend/public/fonts/README.md. Helvetica is a system
// face on every platform this ships to and needs no import.
import '@fontsource-variable/space-grotesk';
import '@fontsource/noto-sans-devanagari/400.css';
import '@fontsource/noto-sans-devanagari/600.css';
import '@fontsource/noto-sans-tamil/400.css';
import '@fontsource/noto-sans-tamil/600.css';

// Legacy surface styles FIRST, so the new system wins every collision. They are
// still loaded because screens land one at a time and the un-rebuilt ones still
// reference their classes; the cleanup pass deletes them. Loading them last was a
// real bug — legacy `body` rules were overriding the ambient background, which is
// why the new surface rendered flat.
import './styles/tokens.css';
import './styles/kiosk.css';
import './styles/physician.css';

// The design system. `tokens` and `base` come first — everything below reads
// from them. `frostwork` carries the shared material (glass, keys, the bar, the
// figure) and sits between the primitives and the two surface sheets, so a
// surface can still override a shared default.
import './design/tokens.css';
import './design/base.css';
import './design/primitives.css';
import './design/frostwork.css';
import './styles/kiosk-v2.css';
import './styles/physician-v2.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ToastProvider>
        <TopBar />
        <RouteStage>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/intake" element={<KioskApp />} />
            <Route path="/physician" element={<PhysicianApp />} />
            <Route path="/demo" element={<DemoLauncher />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </RouteStage>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);

/**
 * Four surfaces, one bundle, chosen by route.
 *
 *   /          landing — one sentence, one action, the disclaimer
 *   /intake    the kiosk (the patient's device)
 *   /physician the review screen
 *   /demo      one-click synthetic cases for a jury
 *
 * They share the typed API client and nothing else — deliberately, because a surface built
 * for a non-literate patient and one built for a time-pressed clinician want opposite things
 * from every component they would otherwise have in common (ADR-0008).
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { KioskApp } from './kiosk/KioskApp';
import { PhysicianApp } from './physician/PhysicianApp';
import { DemoLauncher } from './shared/DemoLauncher';
import { Landing } from './shared/Landing';

import './styles/tokens.css';
import './styles/kiosk.css';
import './styles/physician.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/intake" element={<KioskApp />} />
        <Route path="/physician" element={<PhysicianApp />} />
        <Route path="/demo" element={<DemoLauncher />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);

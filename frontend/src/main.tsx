/**
 * Two surfaces, one bundle, chosen by route.
 *
 * `/` is the kiosk (the patient's device) and `/physician` is the review screen. They share
 * the API client and nothing else — deliberately, because sharing components between a
 * surface built for a non-literate patient and one built for a time-pressed clinician makes
 * both of them worse.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { KioskApp } from './kiosk/KioskApp';
import { PhysicianApp } from './physician/PhysicianApp';

import './styles/tokens.css';
import './styles/kiosk.css';
import './styles/physician.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<KioskApp />} />
        <Route path="/physician" element={<PhysicianApp />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);

/**
 * The brief's route. Picks the audience and makes sure there is a token to read with.
 *
 *   /brief?patient=pat_x            the physician's view
 *   /brief?patient=pat_x&as=patient the same payload, the patient's grouping
 *
 * `as=patient` changes WHICH ENDPOINT is called, not which component filters what. The
 * stripping happens on the server (`to_patient_view`), so a patient-facing screen cannot
 * accidentally render an internal identifier that was sitting in the payload all along.
 *
 * The sign-in here is the same mock staff token the physician workspace uses. It exists
 * because the brief routes are gated by `session.read` / `report.read_own`, and an
 * unauthenticated visit to this URL would otherwise show a bare 403 — accurate, and useless.
 */
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DoctorBrief } from './DoctorBrief';
import { PatientBriefView } from './PatientBriefView';
import { KioskShell } from '../design/KioskShell';
import { api, getToken, setToken } from '../shared/api';

export function BriefRoute(): JSX.Element {
  const [params] = useSearchParams();
  const patientRef = params.get('patient') ?? '';
  const asPatient = params.get('as') === 'patient';
  const [token, setLocalToken] = useState<string | null>(getToken());
  const [busy, setBusy] = useState(false);

  async function signIn(): Promise<void> {
    setBusy(true);
    try {
      const result = await api.staffToken('clinician', 'dr.mehta@aiia');
      setToken(result.access_token);
      setLocalToken(result.access_token);
    } finally {
      setBusy(false);
    }
  }

  if (!patientRef) {
    return (
      <KioskShell>
        <div className="bx">
          <div className="bx-main">
            <p className="bx-empty">
              No patient was named. Open this screen as{' '}
              <code>/brief?patient=&lt;patientRef&gt;</code>.
            </p>
          </div>
        </div>
      </KioskShell>
    );
  }

  if (!token) {
    return (
      <KioskShell>
        <div className="bx">
          <div className="bx-main">
            <section className="bx-section">
              <header className="bx-section__head">
                <h2>Sign in to read this record</h2>
              </header>
              <p className="bx-note">
                A mock staff identity, issued locally. Never presented as a real ABDM login.
              </p>
              <button type="button" className="btn-primary" onClick={signIn} disabled={busy}>
                {busy ? 'Signing in…' : 'Continue as clinician'}
              </button>
            </section>
          </div>
        </div>
      </KioskShell>
    );
  }

  return (
    <KioskShell>
      {asPatient ? (
        <PatientBriefView patientRef={patientRef} />
      ) : (
        <DoctorBrief patientRef={patientRef} />
      )}
    </KioskShell>
  );
}

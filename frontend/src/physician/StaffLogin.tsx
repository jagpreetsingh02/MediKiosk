/**
 * Staff sign-in against the mock issuer.
 *
 * The role matters and the screen says why: `clinician` can commit, `triage_nurse` can see
 * the queue and the flags but deliberately NOT the narrative. A triage desk needs to know
 * someone is urgent, not why — and the backend enforces that, so signing in as a nurse here
 * genuinely blocks the summary rather than just hiding a button.
 */
import { useState } from 'react';
import { ApiError, api, setToken } from '../shared/api';

const ROLES = [
  { id: 'clinician', label: 'Clinician', note: 'Reads the full history, edits, and commits.' },
  { id: 'triage_nurse', label: 'Triage nurse', note: 'Queue and escalations only — no narrative.' },
  { id: 'auditor', label: 'Auditor', note: 'Audit chain verification only.' },
];

interface Props {
  onSignedIn: (role: string, actor: string) => void;
}

export function StaffLogin({ onSignedIn }: Props): JSX.Element {
  const [actor, setActor] = useState('dr.mehta@aiia');
  const [role, setRole] = useState('clinician');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const result = await api.staffToken(role, actor);
      setToken(result.access_token);
      onSignedIn(role, actor);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Sign-in failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="phys-login">
      <div className="phys-login-card">
        <h1 style={{ fontSize: 22, margin: '0 0 6px' }}>MediKiosk — physician review</h1>
        <p style={{ fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.55, margin: '0 0 20px' }}>
          Mock issuer. Tokens are locally signed and labelled <code>mock: true</code>.
        </p>

        {error && <div className="phys-error">{error}</div>}

        <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-3)' }}>
          Who are you?
          <input
            className="btn"
            style={{ width: '100%', marginTop: 6, fontWeight: 400 }}
            value={actor}
            onChange={(event) => setActor(event.target.value)}
          />
        </label>

        <div style={{ marginTop: 16 }}>
          {ROLES.map((entry) => (
            <label
              key={entry.id}
              style={{
                display: 'flex',
                gap: 10,
                alignItems: 'flex-start',
                padding: '9px 11px',
                border: `1px solid ${role === entry.id ? 'var(--accent)' : 'var(--line)'}`,
                background: role === entry.id ? 'var(--accent-soft)' : 'var(--paper)',
                borderRadius: 'var(--radius)',
                marginBottom: 7,
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              <input
                type="radio"
                name="role"
                checked={role === entry.id}
                onChange={() => setRole(entry.id)}
                style={{ marginTop: 3 }}
              />
              <span>
                <strong>{entry.label}</strong>
                <span style={{ display: 'block', color: 'var(--ink-3)', fontSize: 12, marginTop: 2 }}>
                  {entry.note}
                </span>
              </span>
            </label>
          ))}
        </div>

        <button
          type="button"
          className="btn primary"
          style={{ width: '100%', marginTop: 14, height: 38 }}
          disabled={busy}
          onClick={() => void signIn()}
        >
          Sign in
        </button>
      </div>
    </div>
  );
}

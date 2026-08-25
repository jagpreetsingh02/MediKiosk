/**
 * Sign in / create account — A STUB, and it says so on the screen.
 *
 * The real identity path is the MOCK ABHA IdP, which is a documented project decision and is
 * deliberately NOT being replaced. This screen exists so the product does not have a visible
 * hole where judges expect a sign-in, and it is honest about being unfinished rather than
 * pretending to work and failing confusingly.
 *
 * SENTENCE CASE, ACTIVE VOICE. "Sign in", not "SIGN IN" or "Submit". The demo path is
 * labelled as demo, in the same words the rest of the product uses for it.
 *
 * The failure message comes from the SERVER and is deliberately identical for every cause —
 * the frontend must not helpfully add "that email isn't registered", which would undo the
 * non-enumeration property the endpoint is careful to have.
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { KioskShell } from '../design/KioskShell';
import { ApiError, api } from '../shared/api';
import * as guest from '../guest/session';

type Mode = 'sign-in' | 'register';

export function SignIn(): JSX.Element {
  const [mode, setMode] = useState<Mode>('sign-in');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      if (mode === 'register') {
        const result = await api.register(identifier, password);
        setMessage(result.message);
      } else {
        await api.signIn(identifier, password);
      }
    } catch (error) {
      // Verbatim from the server. Never elaborated on locally.
      setMessage(
        error instanceof ApiError
          ? error.message
          : 'Something went wrong. Please try again.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function tryDemo(): Promise<void> {
    setBusy(true);
    try {
      await guest.start();
      navigate('/intake');
    } catch {
      setMessage('The demo could not start just now. Please try again in a moment.');
      setBusy(false);
    }
  }

  return (
    <KioskShell>
      <div className="acct">
        <h1 className="kiosk-title">
          {mode === 'sign-in' ? 'Sign in' : 'Create an account'}
        </h1>

        {/* Said before the form, not after a failed attempt. */}
        <p className="acct-stub" role="note">
          Accounts are not available in this build. To see the product, use the demo — no
          account and no personal details are needed.
        </p>

        <form className="acct-form" onSubmit={submit}>
          <label className="acct-field">
            <span>Email or ABHA address</span>
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="username"
              required
            />
          </label>

          <label className="acct-field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
              required
            />
          </label>

          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'sign-in' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        {message && (
          <p className="acct-message" role="alert">
            {message}
          </p>
        )}

        <div className="acct-alt">
          <button
            type="button"
            className="btn-link"
            onClick={() => {
              setMode(mode === 'sign-in' ? 'register' : 'sign-in');
              setMessage(null);
            }}
          >
            {mode === 'sign-in' ? 'Create an account instead' : 'Sign in instead'}
          </button>
        </div>

        <hr className="acct-rule" />

        <div className="acct-demo">
          <h2>Try it without an account</h2>
          <button type="button" className="btn-secondary" onClick={tryDemo} disabled={busy}>
            Try demo
          </button>
          <p className="kx-footnote">
            Creates a synthetic record with a history already in it. Nothing in it is a real
            patient.
          </p>
          <p className="kx-footnote">
            Patients can also sign in with the <Link to="/intake">demo ABHA identity</Link> —
            a <strong>mock</strong> issuer, never a real ABDM integration.
          </p>
        </div>
      </div>
    </KioskShell>
  );
}

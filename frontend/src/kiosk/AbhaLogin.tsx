/**
 * ABHA login against the MOCK identity provider.
 *
 * The demo credentials are printed on the screen on purpose. A demo where the presenter has
 * to read an OTP out of a server log is a demo that goes wrong in front of judges, and a
 * mock issuer that hides its own mockness is worse than one that announces it.
 */
import { useState } from 'react';
import { ApiError, api, setToken } from '../shared/api';

const DEMO_ADDRESSES = [
  { address: 'kamala.devi@abdm', label: 'Kamala Devi · 64 · female · हिन्दी' },
  { address: 'ramesh.kumar@abdm', label: 'Ramesh Kumar · 47 · male · हिन्दी' },
  { address: 'anitha.r@abdm', label: 'Anitha R · 31 · female · தமிழ்' },
  { address: 'demo@abdm', label: 'Demo Patient · 52 · male · English' },
];

interface Props {
  onAuthenticated: (demographics: Record<string, unknown>) => void;
  onBack: () => void;
}

export function AbhaLogin({ onAuthenticated, onBack }: Props): JSX.Element {
  const [address, setAddress] = useState('');
  const [otp, setOtp] = useState('');
  const [stage, setStage] = useState<'address' | 'otp'>('address');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sendOtp(chosen: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await api.requestOtp(chosen);
      setAddress(chosen);
      setStage('otp');
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not reach the identity service.');
    } finally {
      setBusy(false);
    }
  }

  async function verify(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const result = await api.verifyOtp(address, otp);
      setToken(result.access_token);
      onAuthenticated(result.demographics ?? {});
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Verification failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="kiosk-panel">
      <h1 className="kiosk-title">Your ABHA number</h1>
      <p className="kiosk-lead">
        Touch your name below to sign in. In a real deployment you would scan your ABHA card
        or enter your ABHA address.
      </p>

      {error && <div className="kiosk-error">{error}</div>}

      {stage === 'address' ? (
        <>
          <div className="tap-grid">
            {DEMO_ADDRESSES.map((entry) => (
              <button
                key={entry.address}
                type="button"
                className="tap-option"
                disabled={busy}
                onClick={() => void sendOtp(entry.address)}
              >
                {entry.label}
              </button>
            ))}
          </div>
          <div className="kiosk-actions">
            <button type="button" className="btn-quiet" onClick={onBack}>
              Back
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="kiosk-lead">
            A one-time code was &ldquo;sent&rdquo; to <strong>{address}</strong>.
            <br />
            This mock issuer always accepts <strong>123456</strong>.
          </p>
          <div className="typed-answer">
            <textarea
              value={otp}
              onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456"
              inputMode="numeric"
              aria-label="One-time code"
              style={{ minHeight: 84, fontSize: 40, letterSpacing: '0.4em', textAlign: 'center' }}
            />
          </div>
          <div className="kiosk-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={busy || otp.length !== 6}
              onClick={() => void verify()}
            >
              Continue
            </button>
            <button type="button" className="btn-secondary" onClick={() => setOtp('123456')}>
              Fill demo code
            </button>
            <button type="button" className="btn-quiet" onClick={() => setStage('address')}>
              Back
            </button>
          </div>
        </>
      )}
    </div>
  );
}

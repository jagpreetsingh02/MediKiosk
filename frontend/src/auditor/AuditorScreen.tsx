/**
 * The auditor's screen. Read-only by construction: this file contains no form, no mutating
 * button, no call to any endpoint that is not a GET. There is nothing here to accidentally
 * wire up wrongly, because there is nothing that writes to wire up.
 *
 * `tests/test_auditor_role.py` proves the stronger claim server-side — that the `auditor`
 * role cannot reach ANY mutating route in the whole API, structurally, not just that this one
 * screen happens not to offer one.
 *
 * FOUR THINGS, for one encounter:
 *   the hash chain          recomputed and confirmed, over the WHOLE log (the chain is one
 *                            append-only sequence; it is not scoped per encounter)
 *   the audit trail          every event correlated to this encounter's capture session
 *   provenance completeness  does every durable fact have a source, or an explicit absence
 *   no assessment claim      the SAME scanner that gates every outbound response, run live
 *
 * Plus a tamper demonstration: corrupt one event in an IN-MEMORY COPY of the log and show
 * the chain catches it. The real table is never touched — see `app/audit/review.py`.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KioskShell } from '../design/KioskShell';
import { ApiError, api, getToken, setToken } from '../shared/api';
import { StateGlyph } from '../design/ui/StateGlyph';
import ConstellationField from '../components/ui/constellation-field';

type Review = Awaited<ReturnType<typeof api.auditReview>>;
type TamperResult = Awaited<ReturnType<typeof api.auditTamperDemo>>;

function roleOf(token: string | null): string | null {
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split('.')[1])).role ?? null;
  } catch {
    return null;
  }
}

function Row({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="ax-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function AuditorScreen(): JSX.Element {
  const navigate = useNavigate();
  const [token, setLocalToken] = useState<string | null>(getToken());
  const [busy, setBusy] = useState(false);
  const [encounterRef, setEncounterRef] = useState('');
  const [review, setReview] = useState<Review | null>(null);
  const [tamper, setTamper] = useState<TamperResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const signedInAsAuditor = roleOf(token) === 'auditor';

  async function signIn(): Promise<void> {
    setBusy(true);
    try {
      const result = await api.staffToken('auditor', 'auditor@aiia');
      setToken(result.access_token);
      setLocalToken(result.access_token);
    } finally {
      setBusy(false);
    }
  }

  async function open(): Promise<void> {
    if (!encounterRef.trim()) return;
    setBusy(true);
    setError(null);
    setReview(null);
    try {
      setReview(await api.auditReview(encounterRef.trim()));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not open that encounter.');
    } finally {
      setBusy(false);
    }
  }

  async function runTamperDemo(): Promise<void> {
    setBusy(true);
    try {
      setTamper(await api.auditTamperDemo());
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'The demonstration could not run.');
    } finally {
      setBusy(false);
    }
  }

  if (!signedInAsAuditor) {
    return (
      <KioskShell wide>
        <div className="ax ax--signin">
          <div className="ax-bg" aria-hidden="true">
            <ConstellationField mode="light" density={0.85} speed={0.6} opacity={0.9} />
          </div>
          {/* A solid card, for the same reason the clinician sign-in has one: this screen's
              type is light-on-dark, and the ground behind it is now a pale gradient. */}
          <div className="ax-signin-card">
            <h1 className="kiosk-title">Auditor</h1>
            <p className="kiosk-lead">
              A read-only verifier over the hash-chained audit log and the provenance already
              attached to every fact. It cannot create, edit or delete anything — see
              <code> tests/test_auditor_role.py</code> for the proof, not just this sentence.
            </p>
            <div className="kiosk-actions">
              <button type="button" className="btn-primary" onClick={signIn} disabled={busy}>
                {busy ? 'Signing in…' : 'Continue as auditor'}
              </button>
              <button type="button" className="btn-quiet" onClick={() => navigate('/')}>
                Back
              </button>
            </div>
          </div>
        </div>
      </KioskShell>
    );
  }

  return (
    <KioskShell wide>
      <div className="ax">
        <header className="ax-head">
          <h1 className="kiosk-title">Auditor</h1>
          <p className="kx-footnote">Signed in as auditor. Read-only — nothing here writes.</p>
        </header>

        <div className="ax-lookup">
          <input
            type="text"
            className="ax-input"
            placeholder="Encounter reference, e.g. enc_demo20260118v"
            value={encounterRef}
            onChange={(e) => setEncounterRef(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && open()}
          />
          <button type="button" className="btn-primary" onClick={open} disabled={busy}>
            {busy ? 'Opening…' : 'Open'}
          </button>
        </div>

        {error && <p className="kiosk-error">{error}</p>}

        {review && (
          <>
            <section className="ax-section">
              <h2>Encounter</h2>
              <dl className="ax-rows">
                <Row label="Reference" value={review.encounterRef} />
                <Row label="Occurred on" value={review.occurredOn} />
                <Row label="Confirmed by" value={review.confirmedBy} />
                <Row label="Consent reference" value={review.consentRef ?? '— none recorded'} />
              </dl>
            </section>

            <section className="ax-section" data-state={review.chain.intact ? 'ok' : 'broken'}>
              <h2>
                Hash chain{' '}
                <StateGlyph
                  state={review.chain.intact ? 'ok' : 'critical'}
                  title={review.chain.intact ? 'Intact' : 'Broken'}
                />
              </h2>
              <p className="ax-verdict">
                {review.chain.intact
                  ? `Intact — ${review.chain.eventsChecked} of ${review.chain.totalEvents} events recomputed and confirmed.`
                  : `BROKEN at event #${review.chain.firstBrokenEventId} (index ${review.chain.firstBrokenIndex}). ${review.chain.detail}`}
              </p>
            </section>

            <section
              className="ax-section"
              data-state={review.provenance.complete ? 'ok' : 'broken'}
            >
              <h2>
                Provenance completeness{' '}
                <StateGlyph
                  state={review.provenance.complete ? 'ok' : 'critical'}
                  title={review.provenance.complete ? 'Complete' : 'Incomplete'}
                />
              </h2>
              <p className="ax-verdict">
                {review.provenance.totalFacts} durable fact(s):{' '}
                {review.provenance.withEvidence} carry a recorded source,{' '}
                {review.provenance.withExplicitAbsence} are an explicit absence
                (declined / not asked).
                {review.provenance.offenders.length > 0 && (
                  <strong> {review.provenance.offenders.length} have neither.</strong>
                )}
              </p>
              {review.provenance.offenders.length > 0 && (
                <ul className="ax-offenders">
                  {review.provenance.offenders.map((o) => (
                    <li key={o.factRef}>
                      {o.path} — state: {o.state}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section
              className="ax-section"
              data-state={review.noAssessmentClaim.clean ? 'ok' : 'broken'}
            >
              <h2>
                No diagnosis or treatment claim{' '}
                <StateGlyph
                  state={review.noAssessmentClaim.clean ? 'ok' : 'critical'}
                  title={review.noAssessmentClaim.clean ? 'Clean' : 'Violation found'}
                />
              </h2>
              <p className="ax-verdict">
                {review.noAssessmentClaim.clean
                  ? 'Clean — the same scanner that gates every outbound response found no assessment-shaped field in this report.'
                  : `Found ${review.noAssessmentClaim.offenders.length} assessment-shaped field(s).`}
              </p>
            </section>

            <section className="ax-section">
              <h2>Audit trail ({review.trail.length})</h2>
              {review.trail.length === 0 ? (
                <p className="bx-empty">
                  No audit events are correlated to this encounter — it has no recorded
                  consent reference to join on.
                </p>
              ) : (
                <table className="ax-table">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Actor</th>
                      <th>Role</th>
                      <th>Action</th>
                      <th>Purpose</th>
                      <th>Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {review.trail.map((e) => (
                      <tr key={e.id}>
                        <td>{e.ts.slice(0, 19).replace('T', ' ')}</td>
                        <td>{e.actor}</td>
                        <td>{e.actorRole}</td>
                        <td>{e.action}</td>
                        <td>{e.purposeOfUse}</td>
                        <td>{e.outcome}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}

        <section className="ax-section ax-section--tamper">
          <h2>Tamper demonstration</h2>
          <p className="kx-footnote">
            Corrupts one event in an in-memory COPY of the log and re-verifies it. The real
            audit_event table is only read — this cannot corrupt anything.
          </p>
          <button type="button" className="btn-secondary" onClick={runTamperDemo} disabled={busy}>
            {busy ? 'Running…' : 'Run tamper demonstration'}
          </button>

          {tamper && !tamper.available && <p className="bx-empty">{tamper.note}</p>}
          {tamper && tamper.available && (
            <div className="ax-tamper-result" data-state={tamper.detected ? 'ok' : 'broken'}>
              <p>
                Changed event <strong>#{tamper.tamperedEventId}</strong>&rsquo;s{' '}
                <code>{tamper.tamperedField}</code> from{' '}
                <code>{tamper.originalValue}</code> to <code>{tamper.corruptedValue}</code>.
              </p>
              <p className="ax-verdict">
                <StateGlyph
                  state={tamper.detected ? 'ok' : 'critical'}
                  title={tamper.detected ? 'Detected' : 'Not detected'}
                />{' '}
                {tamper.detected
                  ? `Detected at index ${tamper.firstBrokenIndex} — the recomputed hash no longer matches the stored one.`
                  : 'NOT DETECTED — this would mean the chain is not doing its job.'}
              </p>
              <p className="kx-footnote">{tamper.note}</p>
            </div>
          )}
        </section>
      </div>
    </KioskShell>
  );
}

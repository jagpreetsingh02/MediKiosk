/**
 * Demo mode — one click, one complete synthetic session.
 *
 * A judge has ninety seconds. This creates a session, grants every consent, plays a scripted
 * synthetic patient through the *real* state machine, extractor, OCR pipeline and rule engine,
 * and hands back the session id so they can open it on the physician screen.
 *
 * Nothing here is pre-recorded. The numbers that come back — facts recorded, rules fired,
 * contradictions found — are computed live from the same code the product runs.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppNav } from '../design/AppNav';
import { ApiError, api, setToken, type DemoCase, type DemoLoadResult } from './api';

const ALL_SCOPES = ['history', 'voice', 'documents', 'abdm_share', 'ayush'];

export function DemoLauncher(): JSX.Element {
  const [cases, setCases] = useState<DemoCase[]>([]);
  const [notice, setNotice] = useState('');
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, DemoLoadResult>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .demoCases()
      .then(body => {
        setCases(body.cases);
        setNotice(body.notice);
      })
      .catch(exc => setError(exc instanceof ApiError ? exc.message : 'Could not load demo cases.'));
  }, []);

  async function run(demo: DemoCase): Promise<void> {
    setRunning(demo.id);
    setError(null);
    try {
      // A demo does not bypass the consent gate — it grants consent the way a patient would.
      const auth = await api.verifyOtp('demo@abdm', '123456');
      setToken(auth.access_token);
      const session = await api.createSession(demo.language, ALL_SCOPES, true);
      const result = await api.loadDemoCase(demo.id, session.sessionRef);
      setResults(current => ({ ...current, [demo.id]: result }));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : 'Could not run this case.');
    } finally {
      setRunning(null);
    }
  }

  return (
    <>
      {/* The same bar as the hero and the workspace. A judge moving between the
          three is never handed to a different application. */}
      <AppNav
        context="Demo & jury mode"
        actions={
          <>
            <Link to="/physician" className="mk-btn mk-btn--quiet mk-btn--sm">
              Physician review
            </Link>
            <a href="/about" target="_blank" rel="noreferrer" className="mk-btn mk-btn--ghost mk-btn--sm">
              What is mocked
            </a>
          </>
        }
      />
      <div className="demo">
      <header className="demo-head">
        <div>
          <h1>Demo &amp; jury mode</h1>
          <p>{notice || 'Loading…'}</p>
        </div>
      </header>

      {error && <div className="phys-error">{error}</div>}

      <div className="demo-grid">
        {cases.map(demo => {
          const result = results[demo.id];
          return (
            <article key={demo.id} className="demo-card">
              <h2>{demo.title}</h2>
              <p className="demo-shows">{demo.shows}</p>

              <ul className="demo-watch">
                {demo.watchFor.map(item => (
                  <li key={item}>{item}</li>
                ))}
              </ul>

              <div className="demo-tags">
                <span className="badge">{demo.language}</span>
                {demo.ayush && <span className="badge">AYUSH</span>}
                {demo.document && <span className="badge">{demo.document}</span>}
              </div>

              {result ? (
                <div className="demo-result">
                  <dl>
                    <div>
                      <dt>answered</dt>
                      <dd>{result.answered}</dd>
                    </div>
                    <div>
                      <dt>spoken turns</dt>
                      <dd>{result.spokenTurns}</dd>
                    </div>
                    <div>
                      <dt>facts</dt>
                      <dd>{result.factsRecorded}</dd>
                    </div>
                    <div>
                      <dt>priority</dt>
                      <dd>
                        <span className={`badge ${result.priority}`}>{result.priority}</span>
                      </dd>
                    </div>
                    <div>
                      <dt>rules fired</dt>
                      <dd>{result.redFlags.length ? result.redFlags.join(', ') : 'none'}</dd>
                    </div>
                    <div>
                      <dt>contradictions</dt>
                      <dd>{result.contradictions}</dd>
                    </div>
                    {result.document && (
                      <div>
                        <dt>from document</dt>
                        <dd>{result.document.factsRecorded} facts</dd>
                      </div>
                    )}
                  </dl>
                  <Link className="btn primary" to={`/physician?session=${result.sessionRef}`}>
                    Open on the physician screen →
                  </Link>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn primary"
                  disabled={running !== null}
                  onClick={() => void run(demo)}
                >
                  {running === demo.id ? 'Running the real pipeline…' : 'Run this case'}
                </button>
              )}
            </article>
          );
        })}
      </div>
      </div>
    </>
  );
}

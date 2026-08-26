/**
 * The patient's own record — sign in, see your confirmed visits, download your report.
 *
 * WHY THIS SCREEN EXISTS SEPARATELY FROM THE KIOSK. The kiosk is the thing you use once, in a
 * corridor, before a consultation. This is the thing you open afterwards, at home, possibly
 * weeks later, to answer "what did the doctor write down?". Same record, different moment,
 * and the second one has been missing: everything the system produced was readable by a
 * clinician and by nobody else.
 *
 * ⛔ ONLY WHAT A PHYSICIAN CONFIRMED APPEARS HERE. That is not a filter this component
 * applies — an `Encounter` row is created solely by `promote()`, which is reachable only from
 * the commit route. A visit still being written up does not exist as an encounter yet, so
 * there is nothing here to hide. The screen says so in words, because "you have one visit"
 * and "you have one visit and another we are not showing you" look identical otherwise.
 *
 * IDENTITY IS THE MOCK ABHA IdP, UNCHANGED. Not Supabase Auth, not a new user table — a
 * second patient identity is what the brief explicitly refuses. The login is labelled a mock
 * on screen, in the token, and in `/about`.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { KioskShell } from '../design/KioskShell';
import { AbhaLogin } from '../kiosk/AbhaLogin';
import { PatientBriefView } from '../brief/PatientBriefView';
import { ApiError, api, getToken, setToken } from '../shared/api';
import { Icon } from '../shared/Icon';

interface Visit {
  encounterRef: string;
  occurredOn: string;
  headline: string | null;
  confirmedBy: string;
  confirmedAt: string | null;
}

/** The role on the stored token. Read locally for routing only; never trusted for access. */
function roleOf(token: string | null): string | null {
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split('.')[1])).role ?? null;
  } catch {
    return null;
  }
}

export function PatientPortal(): JSX.Element {
  const params = useParams<{ patientRef: string }>();
  const navigate = useNavigate();
  const [resolvedRef, setResolvedRef] = useState<string | null>(
    params.patientRef && params.patientRef !== 'me' ? params.patientRef : null,
  );
  const patientRef = resolvedRef;

  const [token, setLocalToken] = useState<string | null>(getToken());
  const [visits, setVisits] = useState<Visit[] | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const signedInAsPatient = roleOf(token) === 'patient';

  const load = useCallback(async () => {
    if (!patientRef) return;
    setError(null);
    try {
      const result = await api.myEncounters(patientRef);
      setVisits(result.encounters);
      setName(result.displayName);
      setNote(result.note);
    } catch (exc) {
      // The refusal is the server's own wording. A patient reaching somebody else's record
      // must not be told anything about whether that record exists.
      setError(
        exc instanceof ApiError
          ? exc.message
          : 'We could not open your record just now. Please try again.',
      );
      setVisits([]);
    }
  }, [patientRef]);

  // `/patient/me` is the link a returning patient follows; the reference comes from the
  // TOKEN rather than the URL, so nobody has to know or type their own patient id — and a
  // guessable id in a link is not a way into somebody else's record.
  useEffect(() => {
    if (!signedInAsPatient || resolvedRef) return;
    let live = true;
    api
      .myRecord()
      .then((r) => {
        const ref = (r as { patientRef?: string }).patientRef ?? null;
        if (live) {
          if (ref) setResolvedRef(ref);
          else setError('No record is linked to this sign-in yet.');
        }
      })
      .catch(() => live && setError('We could not open your record just now.'));
    return () => {
      live = false;
    };
  }, [signedInAsPatient, resolvedRef]);

  useEffect(() => {
    if (signedInAsPatient && patientRef) void load();
  }, [signedInAsPatient, patientRef, load]);

  async function download(encounterRef: string): Promise<void> {
    if (!patientRef) return;
    setDownloading(encounterRef);
    try {
      // The SAME deterministic generator the clinician report uses, in its patient variant.
      const { url, filename } = await api.briefPdf(patientRef, 'patient', encounterRef);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch {
      setError('That report could not be prepared. Please try again.');
    } finally {
      setDownloading(null);
    }
  }

  // ── not signed in ────────────────────────────────────────────────────────
  if (!signedInAsPatient) {
    return (
      <KioskShell>
        <div className="pp">
          <h1 className="kiosk-title">See your own records</h1>
          <p className="kiosk-lead">
            Sign in with your ABHA address to read what the doctor wrote down, and to download
            a copy for yourself.
          </p>
          <AbhaLogin
            onAuthenticated={() => {
              setLocalToken(getToken());
            }}
            onBack={() => navigate('/')}
          />
        </div>
      </KioskShell>
    );
  }

  // ── the record ───────────────────────────────────────────────────────────
  return (
    <KioskShell>
      <div className="pp">
        <header className="pp-head">
          <div>
            <h1 className="kiosk-title">Your visits</h1>
            {name && <p className="kiosk-lead">{name}</p>}
          </div>
          <button
            type="button"
            className="btn-link"
            onClick={() => {
              setToken(null);
              setLocalToken(null);
              setVisits(null);
            }}
          >
            Sign out
          </button>
        </header>

        {error && <p className="kiosk-error">{error}</p>}

        {visits === null && <div className="bx-loading" aria-label="Loading your visits" />}

        {visits !== null && visits.length === 0 && !error && (
          <p className="bx-empty">
            You have no confirmed visits yet. A visit appears here once a doctor has finished
            reviewing it.
          </p>
        )}

        {visits !== null && visits.length > 0 && (
          <>
            {/* Said out loud. "One visit" and "one visit plus one we are hiding" look the
                same, and the patient is the person entitled to know which it is. */}
            {note && <p className="kx-footnote">{note}</p>}

            <ol className="pp-visits">
              {visits.map((v) => (
                <li key={v.encounterRef} className="pp-visit">
                  <div className="pp-visit__when">
                    <strong>{v.occurredOn}</strong>
                    <span className="kx-footnote">Confirmed by {v.confirmedBy}</span>
                  </div>
                  <div className="pp-visit__what">{v.headline ?? 'Clinical history'}</div>
                  <div className="pp-visit__actions">
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setOpen(open === v.encounterRef ? null : v.encounterRef)}
                      aria-expanded={open === v.encounterRef}
                    >
                      {open === v.encounterRef ? 'Hide my report' : 'View my report'}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => download(v.encounterRef)}
                      disabled={downloading !== null}
                    >
                      <Icon name="image" />
                      {downloading === v.encounterRef ? 'Preparing…' : 'Download PDF'}
                    </button>
                  </div>

                  {open === v.encounterRef && (
                    <div className="pp-visit__report">
                      {/* The same patient view the kiosk shows, for THIS visit. */}
                      <PatientBriefView patientRef={patientRef!} encounterRef={v.encounterRef} />
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </KioskShell>
  );
}

/**
 * The patient's workspace — everything the person the record is about can do with it.
 *
 * WHY THIS EXISTS SEPARATELY FROM THE KIOSK. The kiosk is the thing you use once, in a
 * corridor, before a consultation: it asks questions and it ends. This is the thing you open
 * afterwards, at home, possibly weeks later, and it never ends. Same record, different
 * moment. Both are the patient's, and both sit behind the Patient door on the front screen.
 *
 * FIVE VIEWS, ONE RECORD:
 *
 *   Visits      the confirmed visits, each with its report and a PDF     PatientVisits
 *   Timeline    the whole record on one axis, filterable                 record/LongitudinalTimeline
 *   Medicines   one thread per drug, with how each mention is known      record/MedicationHistory
 *   Papers      what has been read off their documents, and adding more  PatientRecords
 *   Changes     what each confirmed visit added, and who signed it off   PatientChanges
 *
 * ⛔ NOTHING FROM THE DOCTOR'S WORKSPACE APPEARS HERE. Not the queue, not the verification
 * lane, not the commit bar, not another patient's anything — and structurally, not by
 * omission: this folder imports from `patient/`, `kiosk/`, `brief/`, `record/` and `design/`,
 * and never from `physician/`. `tests/test_role_separation.py` fails the build if that
 * changes. The three views both roles genuinely need live in `record/`, owned by neither, and
 * the one place their vocabulary differs is passed as `audience` rather than forked. ADR-0016.
 *
 * ⛔ ONLY WHAT A PHYSICIAN CONFIRMED IS ON THIS SCREEN, which is a property of the schema
 * rather than a filter applied here — see `PatientVisits` and `PatientChanges`.
 *
 * IDENTITY IS THE MOCK ABHA IdP, UNCHANGED. Not Supabase Auth, not a new user table — a
 * second patient identity is what the brief explicitly refuses. The login is labelled a mock
 * on screen, in the token, and in `/about`.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { KioskShell } from '../design/KioskShell';
import { AbhaLogin } from '../kiosk/AbhaLogin';
import { LongitudinalTimeline } from '../record/LongitudinalTimeline';
import { MedicationHistory } from '../record/MedicationHistory';
import { EvidenceDrawer } from '../record/EvidenceDrawer';
import { PatientChanges, type ConfirmedVisit } from './PatientChanges';
import { PatientRecords } from './PatientRecords';
import { PatientVisits } from './PatientVisits';
import { ApiError, api, getToken, setToken, type MedicationThread, type TimelineRow } from '../shared/api';

type Panel = 'visits' | 'timeline' | 'medicines' | 'papers' | 'changes';

const PANELS: { id: Panel; label: string }[] = [
  { id: 'visits', label: 'Visits' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'medicines', label: 'Medicines' },
  { id: 'papers', label: 'My papers' },
  { id: 'changes', label: 'What changed' },
];

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
  const [visits, setVisits] = useState<ConfirmedVisit[] | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  /** The language of the most recent visit, so an upload session is not silently English. */
  const [language, setLanguage] = useState('en');
  const [error, setError] = useState<string | null>(null);

  const [panel, setPanel] = useState<Panel>('visits');
  const [timeline, setTimeline] = useState<TimelineRow[] | null>(null);
  const [medications, setMedications] = useState<MedicationThread[] | null>(null);
  const [evidence, setEvidence] = useState<{ documentId: string; label: string } | null>(null);

  const signedInAsPatient = roleOf(token) === 'patient';

  /** Which panels read the whole-record timeline. Three of the five do. */
  const needsTimeline = panel === 'timeline' || panel === 'papers' || panel === 'changes';

  const load = useCallback(async () => {
    if (!patientRef) return;
    setError(null);
    try {
      const result = await api.myEncounters(patientRef);
      setVisits(result.encounters);
      setName(result.displayName);
      setNote(result.note);
      if (result.encounters[0]?.language) setLanguage(result.encounters[0].language);
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

  // `/patient` and `/patient/me` are the links a returning patient follows; the reference
  // comes from the TOKEN rather than the URL, so nobody has to know or type their own patient
  // id — and a guessable id in a link is not a way into somebody else's record.
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

  // Loaded once per panel, on first visit to it — not eagerly on sign-in, since most patients
  // opening this screen just want their visits and never touch the other tabs.
  useEffect(() => {
    if (!signedInAsPatient || !patientRef) return;
    let live = true;
    if (needsTimeline && timeline === null) {
      api
        .patientTimeline(patientRef)
        .then((r) => live && setTimeline(r.events))
        .catch(() => live && setTimeline([]));
    }
    if (panel === 'medicines' && medications === null) {
      api
        .patientMedications(patientRef)
        .then((r) => live && setMedications(r.medications))
        .catch(() => live && setMedications([]));
    }
    return () => {
      live = false;
    };
  }, [signedInAsPatient, patientRef, panel, needsTimeline, timeline, medications]);

  // ── not signed in ────────────────────────────────────────────────────────
  //
  // NOT A SIGN-IN WALL. The Patient door has to answer for both patients behind it — the one
  // standing at a kiosk in a corridor who wants to start a visit, and the one at home who
  // wants to read what the doctor wrote — and only the second of those needs to sign in
  // first. Putting the visit behind a sign-in would have made the front door's primary path
  // longer than it was before the split, which is the opposite of the point.
  if (!signedInAsPatient) {
    return (
      <KioskShell>
        <div className="pp">
          <h1 className="kiosk-title">Your records</h1>
          <p className="kiosk-lead">
            Sign in with your ABHA address to read what the doctor wrote down, add a paper, and
            download a copy for yourself.
          </p>

          <p className="pp-or">
            Here for an appointment?{' '}
            <Link to="/intake" className="pp-start">
              Start a visit
            </Link>
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
            <h1 className="kiosk-title">Your record</h1>
            {name && <p className="kiosk-lead">{name}</p>}
          </div>
          <div className="pp-head__actions">
            {/* Today's visit is a patient action and belongs on the patient's own screen —
                it is the one thing here that writes rather than reads. */}
            <Link to="/intake" className="pp-start">
              Start a visit
            </Link>
            <Link to="/" className="btn-link">
              ← Home
            </Link>
            <button
              type="button"
              className="btn-link"
              onClick={() => {
                setToken(null);
                setLocalToken(null);
                setVisits(null);
                setTimeline(null);
                setMedications(null);
              }}
            >
              Sign out
            </button>
          </div>
        </header>

        <nav className="pp-tabs" aria-label="Your record views">
          {PANELS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={`pp-tab${panel === entry.id ? ' active' : ''}`}
              aria-selected={panel === entry.id}
              onClick={() => setPanel(entry.id)}
            >
              {entry.label}
            </button>
          ))}
        </nav>

        {error && <p className="kiosk-error">{error}</p>}

        {panel === 'visits' && !error && (
          <PatientVisits
            patientRef={patientRef!}
            visits={visits}
            note={note}
            onError={setError}
          />
        )}

        {panel === 'timeline' && (
          <div data-density="patient">
            {timeline === null && <div className="bx-loading" aria-label="Loading your timeline" />}
            {timeline !== null && (
              <LongitudinalTimeline
                events={timeline}
                onOpenDocument={(documentRef) =>
                  setEvidence({ documentId: documentRef, label: 'Your document' })
                }
              />
            )}
          </div>
        )}

        {panel === 'medicines' && (
          <div data-density="patient">
            {medications === null && (
              <div className="bx-loading" aria-label="Loading your medicines" />
            )}
            {medications !== null && (
              <MedicationHistory
                medications={medications}
                audience="patient"
                onOpenDocument={(documentRef) =>
                  setEvidence({ documentId: documentRef, label: 'Your document' })
                }
              />
            )}
          </div>
        )}

        {panel === 'papers' && (
          <div data-density="patient">
            <PatientRecords
              events={timeline}
              language={language}
              onOpenDocument={(documentRef, label) =>
                setEvidence({ documentId: documentRef, label })
              }
              // A confirmed visit may have landed while this tab was open. Drop the cache
              // rather than merging: the server's ordering is the one that is correct.
              onUploaded={() => {
                setTimeline(null);
                void load();
              }}
            />
          </div>
        )}

        {panel === 'changes' && (
          <div data-density="patient">
            <PatientChanges visits={visits} events={timeline} />
          </div>
        )}
      </div>

      {evidence && patientRef && (
        <EvidenceDrawer
          fileUrl={api.documentFileUrl(patientRef, evidence.documentId)}
          item={null}
          documentLabel={evidence.label}
          onClose={() => setEvidence(null)}
        />
      )}
    </KioskShell>
  );
}

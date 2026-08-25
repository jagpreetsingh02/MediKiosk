/**
 * Demo-mode state, owned in one place.
 *
 * WHY A MODULE AND NOT A PROP. The DEMO badge has to appear on EVERY screen in this mode —
 * kiosk, physician, brief, patient view, and every PDF page. Threading a `isDemo` prop
 * through five route trees means five chances to forget one, and the screen that forgets it
 * is the screen where a judge sees synthetic clinical data with nothing saying so.
 *
 * So the flag lives in sessionStorage, and `<DemoBadge>` mounts once above the router. Any
 * screen reachable in demo mode is badged by construction rather than by remembering.
 *
 * sessionStorage rather than localStorage: a demo should end when the tab does. Nobody
 * should open the site a week later and still be in it without having asked.
 */
import { api } from '../shared/api';

const KEY = 'medikiosk.guest';

export interface GuestSession {
  patientRef: string;
  displayName: string;
  startedAt: string;
}

type Listener = (session: GuestSession | null) => void;
const listeners = new Set<Listener>();

function read(): GuestSession | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as GuestSession) : null;
  } catch {
    // A private window, or storage the browser refuses. Not being in demo mode is the
    // correct answer to "I cannot tell" — the alternative would badge a real session.
    return null;
  }
}

function write(session: GuestSession | null): void {
  try {
    if (session) sessionStorage.setItem(KEY, JSON.stringify(session));
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable; the in-memory listeners still fire for this page view */
  }
  listeners.forEach((fn) => fn(session));
}

export function current(): GuestSession | null {
  return read();
}

export function isDemo(): boolean {
  return read() !== null;
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Start a demo. Creates the synthetic record server-side and remembers it. */
export async function start(): Promise<GuestSession> {
  const result = await api.startGuest();
  const session: GuestSession = {
    patientRef: result.patientRef,
    displayName: result.displayName,
    startedAt: new Date().toISOString(),
  };
  write(session);
  return session;
}

/**
 * Restore the demo to its starting state.
 *
 * The server returns a NEW patientRef — it deletes and rebuilds rather than mutating, so the
 * old ref no longer exists. Writing the new one back is not bookkeeping; without it every
 * screen would keep asking for a record that has been deleted.
 */
export async function reset(): Promise<GuestSession | null> {
  const existing = read();
  if (!existing) return null;
  const result = await api.resetGuest(existing.patientRef);
  const session: GuestSession = {
    patientRef: result.patientRef,
    displayName: result.displayName,
    startedAt: new Date().toISOString(),
  };
  write(session);
  return session;
}

/** Leave demo mode. Does not delete the server record — a judge may still be reading it. */
export function end(): void {
  write(null);
}

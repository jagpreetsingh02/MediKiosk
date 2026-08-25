/**
 * A badge that appears ONLY when the process is running on the local demo database.
 *
 * WHY THIS EXISTS. `DEMO_LOCAL_DB=true` swaps Supabase for a local Postgres so a demo can
 * survive a venue that blocks outbound 5432. That is a real mitigation and it introduces a
 * real hazard: someone presenting from local data, believing — and telling a room — that they
 * are showing the hosted project. Nothing on screen would contradict them.
 *
 * So the flag is announced in three places that are hard to miss and hard to remove by
 * accident: a warning in the startup log, a field in `/about`, and this. It renders nothing
 * at all against Supabase, so it costs the real demo nothing.
 *
 * It is deliberately styled like the mock-identity disclaimer rather than like the product:
 * chrome that blends in is chrome that gets ignored, and this one has to survive being
 * photographed.
 */
import { useEffect, useState } from 'react';
import { api } from '../shared/api';

interface DatabaseInfo {
  backend?: string;
  host?: string;
  isLocalDemo?: boolean;
  isSupabase?: boolean;
}

export function DatabaseBadge(): JSX.Element | null {
  const [info, setInfo] = useState<DatabaseInfo | null>(null);

  useEffect(() => {
    // A failure here must never take a screen down — the badge is a safety net, and a safety
    // net that can crash the page is worse than no badge. Silence is correct: if /about
    // cannot be reached the surrounding UI already has bigger problems to report.
    api
      .about()
      .then((body) => setInfo((body as { database?: DatabaseInfo }).database ?? null))
      .catch(() => setInfo(null));
  }, []);

  // Flag it on the root element so the layout can make room. Doing this in CSS rather than
  // by wrapping the app keeps the badge out of every surface's layout logic: `.phys` in
  // particular is a viewport-height grid, and a sibling above it would push it off-screen.
  useEffect(() => {
    const root = document.documentElement;
    if (info?.isLocalDemo) root.dataset.localDb = 'true';
    else delete root.dataset.localDb;
    return () => {
      delete root.dataset.localDb;
    };
  }, [info?.isLocalDemo]);

  if (!info?.isLocalDemo) return null;

  return (
    <div className="mk-dbbadge" role="note">
      <span className="mk-dbbadge__dot" aria-hidden="true" />
      <strong>LOCAL DEMO DATABASE</strong>
      <span>
        Running on a local Postgres ({info.host ?? 'localhost'}), not Supabase. Nothing here
        reaches the hosted project.
      </span>
    </div>
  );
}

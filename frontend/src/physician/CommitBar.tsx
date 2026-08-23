/**
 * ⛔ Invariant 4 lives here on the frontend: the physician is the committer.
 *
 * The button is disabled until the summary has actually been read — not as friction theatre,
 * but because "confirm" on an unread draft is exactly the failure this invariant exists to
 * prevent. The backend refuses an unconfirmed commit independently, so this is the second of
 * two gates, not the only one.
 */
interface Props {
  status: string;
  traceable: boolean;
  completeness: number;
  reviewed: boolean;
  busy: boolean;
  committed: { bundleId: string; entries: number; hisStatus: string } | null;
  onCommit: () => void;
}

export function CommitBar({
  status,
  traceable,
  completeness,
  reviewed,
  busy,
  committed,
  onCommit,
}: Props): JSX.Element {
  if (committed) {
    return (
      <>
        <span className="badge ok">committed</span>
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          Bundle <code style={{ fontFamily: 'var(--mono)' }}>{committed.bundleId}</code> ·{' '}
          {committed.entries} FHIR resources · HIS: {committed.hisStatus}
        </span>
        <span className="phys-top-spacer" style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
          Session data purged. The committed bundle survives.
        </span>
      </>
    );
  }

  return (
    <>
      <span className={`badge ${status === 'draft' ? 'draft' : 'ok'}`}>{status}</span>
      <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
        {(completeness * 100).toFixed(0)}% of the applicable history captured ·{' '}
        {traceable ? (
          <span style={{ color: 'var(--ok)' }}>every claim traced to a source</span>
        ) : (
          <span style={{ color: 'var(--danger)' }}>traceability check failed</span>
        )}
      </span>
      <span style={{ flex: 1 }} />
      {!reviewed && (
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
          Scroll through the summary to enable commit
        </span>
      )}
      <button
        type="button"
        className="btn primary"
        disabled={busy || !reviewed || !traceable}
        onClick={onCommit}
        title={
          reviewed
            ? 'Confirm this history and push it to the HIS'
            : 'Read the summary before confirming'
        }
      >
        Confirm and commit <kbd style={{ marginLeft: 6 }}>⌘↵</kbd>
      </button>
    </>
  );
}

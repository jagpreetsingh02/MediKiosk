/**
 * ⛔ Invariant 4 lives here on the frontend: the physician is the committer.
 *
 * THE ARMING CONDITION IS AN ATTESTATION, NOT A SCROLL POSITION.
 *
 * This bar used to enable itself when the summary column had been scrolled to the bottom.
 * That was wrong twice over. Mechanically it broke on short summaries, zoom, short viewports
 * and keyboard-only navigation (see `useSummaryReviewed.ts` for each case) — a physician who
 * had genuinely read everything could be permanently unable to commit.
 *
 * More importantly it was wrong in kind. Scrolling is a proxy for reading, and a proxy is not
 * an attestation. What Invariant 4 actually requires is a named clinician taking
 * responsibility for a durable clinical record: the backend demands `confirmed: true` from a
 * `clinician` role, and this control is the human act that claim refers to. A scrollbar
 * reaching the bottom cannot be that act — a stray trackpad gesture produces it.
 *
 * So there are now two conditions, and they do different jobs:
 *
 *   reachedEnd   the end of the summary has actually been on screen. Measured with an
 *                IntersectionObserver, so it is true whether the physician scrolled, zoomed
 *                out, resized, or the summary simply fit. It gates the CHECKBOX, not the
 *                button — it is a precondition for the attestation being meaningful, not the
 *                attestation itself.
 *
 *   attested     the physician ticked "I have reviewed this summary". This is the arming
 *                condition for the commit button, and it is deliberately an affirmative,
 *                revocable act with a name on it.
 *
 * `traceable` remains an independent hard block: an untraceable summary cannot be committed
 * no matter who attests to it, because Invariant 2 is not a matter of clinical judgement.
 */
interface Props {
  status: string;
  traceable: boolean;
  completeness: number;
  /** The end of the summary has been on screen. Gates the checkbox. */
  reachedEnd: boolean;
  /** The physician ticked the attestation. Gates the button. */
  attested: boolean;
  onAttest: (value: boolean) => void;
  busy: boolean;
  committed: { bundleId: string; entries: number; hisStatus: string } | null;
  onCommit: () => void;
}

export function CommitBar({
  status,
  traceable,
  completeness,
  reachedEnd,
  attested,
  onAttest,
  busy,
  committed,
  onCommit,
}: Props): JSX.Element {
  if (committed) {
    return (
      <>
        <span className="badge ok">committed</span>
        <span className="phys-commit__detail">
          Bundle <code>{committed.bundleId}</code> · {committed.entries} FHIR resources · HIS:{' '}
          {committed.hisStatus}
        </span>
        <span style={{ flex: 1 }} />
        <span className="phys-commit__note">
          Session data purged. The committed bundle survives.
        </span>
      </>
    );
  }

  const blocked = busy || !attested || !traceable;

  return (
    <>
      <span className={`badge ${status === 'draft' ? 'draft' : 'ok'}`}>{status}</span>
      <span className="phys-commit__detail">
        {(completeness * 100).toFixed(0)}% of the applicable history captured ·{' '}
        {traceable ? (
          <span className="phys-commit__ok">every claim traced to a source</span>
        ) : (
          <span className="phys-commit__bad">traceability check failed</span>
        )}
      </span>

      <span style={{ flex: 1 }} />

      {/* A real checkbox, not a styled div: it must be reachable by Tab, togglable by Space,
          and announced as a checkbox by a screen reader. A physician driving this screen
          from the keyboard is the normal case, not an accessibility afterthought. */}
      <label className="phys-attest" data-ready={reachedEnd || undefined}>
        <input
          type="checkbox"
          checked={attested}
          disabled={!reachedEnd}
          onChange={(event) => onAttest(event.target.checked)}
        />
        <span>I have reviewed this summary</span>
      </label>

      {!reachedEnd && (
        <span className="phys-commit__note" role="status">
          Read to the end of the summary to confirm
        </span>
      )}

      <button
        type="button"
        className="btn primary"
        disabled={blocked}
        onClick={onCommit}
        title={
          !traceable
            ? 'This summary has an untraceable claim and cannot be committed'
            : attested
              ? 'Confirm this history and push it to the HIS'
              : 'Tick "I have reviewed this summary" to confirm'
        }
      >
        Confirm and commit <kbd style={{ marginLeft: 6 }}>⌘↵</kbd>
      </button>
    </>
  );
}

/**
 * The kiosk frame: the shared nav, section progress, content stage.
 *
 * Everything the patient sees sits inside this. It exists so no individual screen has to think
 * about the page furniture, and so the *stage* — the region that swaps between screens — is a
 * single element that `AnimatePresence` can animate without the header and progress moving
 * with it.
 *
 * The header is no longer the kiosk's own. It is `AppNav`, the same bar the hero wears and the
 * same bar the physician workspace wears, with the progress rail dropped into its centre slot.
 * The patient who tapped Start on the landing page sees the mark stay exactly where it was,
 * the same size, in the same material — the page under it changed and the frame did not. That
 * is the whole reason this component was rewritten rather than re-coloured.
 *
 * The mock-identity banner stays, and stays visually loud. It is the one piece of chrome
 * allowed to break the glass language, because a synthetic-data disclaimer that blends in is a
 * disclaimer that is not doing its job.
 */
import type { ReactNode } from 'react';
import { AppNav } from './AppNav';

export { BrandMark } from './AppNav';

interface Props {
  /** Section progress rail. Hidden before the interview begins. */
  progress?: ReactNode;
  /** Right-hand header slot — "Start over", the records chip, diagnostics. */
  actions?: ReactNode;
  /** Sub-brand line under the wordmark, e.g. the patient's name once known. */
  context?: ReactNode;
  children: ReactNode;
  /** Widen the stage for screens that hold a grid rather than a single question. */
  wide?: boolean;
  onPointerDownCapture?: () => void;
}

export function KioskShell({
  progress,
  actions,
  context,
  children,
  wide = false,
  onPointerDownCapture,
}: Props) {
  return (
    <div className="kx" data-surface="kiosk" onPointerDownCapture={onPointerDownCapture}>
      <div className="kx-disclaimer" role="note">
        <span className="kx-disclaimer__dot" aria-hidden="true" />
        Demo identity — mock ABHA issuer, synthetic patients only. Not an ABDM integration.
      </div>

      <AppNav context={context} center={progress} actions={actions} />

      <main className={`kx-stage${wide ? ' kx-stage--wide' : ''}`}>{children}</main>
    </div>
  );
}

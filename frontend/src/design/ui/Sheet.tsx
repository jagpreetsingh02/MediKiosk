/**
 * A centred modal sheet. Same focus contract as Drawer.
 */
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { fade, sheet } from '../motion';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** When false, clicking the backdrop does not dismiss — for destructive confirms. */
  dismissible?: boolean;
}

export function Sheet({ open, onClose, title, children, dismissible = true }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement | null;
    const timer = window.setTimeout(() => panel.current?.focus(), 40);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && dismissible) onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('keydown', onKey);
      restoreTo.current?.focus?.();
    };
  }, [open, onClose, dismissible]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="mk-overlay"
          style={{ display: 'grid', placeItems: 'center', padding: 'var(--mk-space-6)' }}
          variants={fade}
          initial="hidden"
          animate="visible"
          exit="exit"
          onClick={dismissible ? onClose : undefined}
        >
          <motion.div
            ref={panel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="mk-sheet"
            variants={sheet}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={(event) => event.stopPropagation()}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

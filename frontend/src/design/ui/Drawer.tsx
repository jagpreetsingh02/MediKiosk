/**
 * A right-hand drawer for evidence and detail panels.
 *
 * Focus is trapped while open and returned to the opener on close, and Escape
 * closes. That is the whole reason this is a component rather than a styled div:
 * a drawer that strands keyboard focus behind an overlay is unusable, and it is
 * the single most commonly skipped part of building one.
 */
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { drawer, fade } from '../motion';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Width override for wide evidence panels. */
  width?: number;
}

export function Drawer({ open, onClose, title, children, width }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement | null;
    // Move focus into the panel so the next Tab lands inside it, not behind it.
    const timer = window.setTimeout(() => panel.current?.focus(), 40);

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !panel.current) return;
      const focusable = panel.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKey, true);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('keydown', onKey, true);
      restoreTo.current?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="mk-overlay"
            variants={fade}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={onClose}
          />
          <motion.div
            ref={panel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="mk-drawer"
            style={width ? { width: `min(${width}px, 100vw)` } : undefined}
            variants={drawer}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

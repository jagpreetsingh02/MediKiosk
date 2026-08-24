/**
 * Transient messages, announced to screen readers.
 *
 * The region is `aria-live="polite"` and `role="status"` so a toast is spoken
 * without stealing focus — important on the kiosk, where a toast fires while the
 * patient is mid-answer and must not interrupt them.
 */
import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { springSoft } from '../motion';

export type ToastTone = 'neutral' | 'ok' | 'alert';

interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastApi {
  show: (message: string, tone?: ToastTone) => void;
}

const Ctx = createContext<ToastApi>({ show: () => {} });

export function useToast(): ToastApi {
  return useContext(Ctx);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, tone: ToastTone = 'neutral') => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const api = useMemo(() => ({ show }), [show]);

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="mk-toast-region" role="status" aria-live="polite">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              layout
              className={`mk-toast${toast.tone !== 'neutral' ? ` mk-toast--${toast.tone}` : ''}`}
              initial={{ opacity: 0, y: 20, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.16 } }}
              transition={springSoft}
            >
              {toast.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}

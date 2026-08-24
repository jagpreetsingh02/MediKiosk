/**
 * A status token. `tone` is semantic, never decorative — `alert` means a red
 * flag or a contradiction, and nothing else is allowed to borrow it.
 */
import type { ReactNode } from 'react';

export type BadgeTone = 'neutral' | 'ok' | 'warn' | 'alert' | 'info';

interface Props {
  tone?: BadgeTone;
  /** Show a leading dot. Useful when the badge sits in a dense row of text. */
  dot?: boolean;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = 'neutral', dot = false, children, className = '' }: Props) {
  return (
    <span className={`mk-badge mk-badge--${tone} ${className}`.trim()}>
      {dot && <span className="mk-badge__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

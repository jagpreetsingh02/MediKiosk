/**
 * An empty state that says what would fill it and how.
 *
 * "No documents" alone is a dead end; "No records yet — add a prescription and
 * it appears here" is an instruction. Every empty state in the product takes
 * the second form.
 */
import type { ReactNode } from 'react';

interface Props {
  glyph?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}

export function EmptyState({ glyph, title, body, action }: Props) {
  return (
    <div className="mk-empty">
      {glyph && <div className="mk-empty__glyph">{glyph}</div>}
      <div className="mk-empty__title">{title}</div>
      {body && <p className="mk-empty__body">{body}</p>}
      {action}
    </div>
  );
}

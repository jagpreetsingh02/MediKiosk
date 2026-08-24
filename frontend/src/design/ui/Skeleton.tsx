/**
 * A loading placeholder shaped like the thing it is standing in for.
 *
 * Deliberately not a spinner: a spinner says "wait", a skeleton says "here is
 * what is coming", and the second is what keeps a slow screen from feeling
 * broken. Marked `aria-hidden` — the live region announces loading instead.
 */
interface Props {
  width?: string | number;
  height?: string | number;
  radius?: string;
  className?: string;
}

export function Skeleton({ width = '100%', height = 16, radius, className = '' }: Props) {
  return (
    <div
      className={`mk-skeleton ${className}`.trim()}
      aria-hidden="true"
      style={{ width, height, borderRadius: radius }}
    />
  );
}

/** Several lines of fake text, the last one short like a real paragraph. */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="mk-stack" style={{ gap: 'var(--mk-space-2)' }}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} height={14} width={i === lines - 1 ? '60%' : '100%'} />
      ))}
    </div>
  );
}

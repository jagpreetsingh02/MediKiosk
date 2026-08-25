/**
 * Clinical state, carried by SHAPE first and colour second.
 *
 * THE PROBLEM THIS SOLVES. Caution is amber (hue ~40°) and critical is rose (hue ~350°).
 * Those are 50° apart and unmistakable to normal trichromatic vision — but red–green colour
 * deficiency affects roughly 1 in 12 men, and under deuteranopia the long-wavelength end of
 * the spectrum compresses, pulling both toward a duller yellow-brown.
 *
 * MEASURED, not assumed (`tests/test_colour_vision_deficiency.py` prints these):
 *
 *     normal vision    ΔE 63.8
 *     protanopia       ΔE 67.4
 *     deuteranopia     ΔE 21.9   <- a 66% loss of separation
 *
 * 21.9 is still above the ~10 at which two samples read as the same colour, so the pair does
 * NOT actually become indistinguishable — the honest finding is that it survives, with two
 * thirds of its margin gone. That is a thin thing to rest an escalation on, and hue was the
 * only signal carrying it.
 *
 * So hue is now the third of three channels rather than the only one:
 *
 *   SHAPE   A triangle for caution, an octagon for critical. Chosen because they are the two
 *           most over-learned warning silhouettes in the world — road signage uses exactly
 *           this pairing — and because they remain distinguishable at 12px, in monochrome,
 *           and to someone who cannot separate the hues at all. Shape survives every kind of
 *           colour vision, and it survives a black-and-white printout of the summary.
 *   TEXT    An explicit word. Never an icon alone.
 *   COLOUR  Reinforces the other two. It no longer carries the meaning by itself.
 *
 * The glyphs are drawn rather than imported so they inherit `currentColor`, stay crisp at any
 * size, and add no dependency to a screen a clinician is waiting on.
 */
import type { ReactNode } from 'react';

export type ClinicalState = 'critical' | 'caution' | 'ok' | 'info' | 'neutral';

/** The word shown alongside the glyph. Never rendered as an icon on its own. */
export const STATE_LABEL: Record<ClinicalState, string> = {
  critical: 'Critical',
  caution: 'Caution',
  ok: 'Clear',
  info: 'Source',
  neutral: 'Note',
};

/** Maps the API's priority vocabulary onto the visual states. */
export function stateForPriority(priority: string): ClinicalState {
  if (priority === 'immediate') return 'critical';
  if (priority === 'urgent') return 'caution';
  return 'ok';
}

interface Props {
  state: ClinicalState;
  size?: number;
  /** Decorative when a text label sits beside it; labelled when it stands alone. */
  title?: string;
}

export function StateGlyph({ state, size = 16, title }: Props): JSX.Element {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className: `mk-state-glyph mk-state-glyph--${state}`,
    role: title ? ('img' as const) : undefined,
    'aria-hidden': title ? undefined : true,
  };

  return (
    <svg {...common}>
      {title && <title>{title}</title>}
      {shape(state)}
    </svg>
  );
}

function shape(state: ClinicalState): ReactNode {
  switch (state) {
    // OCTAGON — the stop sign. Reserved for `immediate`, and used nowhere else in the
    // product, so the silhouette itself is unambiguous.
    case 'critical':
      return (
        <>
          <path d="M8.4 2.6h7.2L21.4 8.4v7.2l-5.8 5.8H8.4L2.6 15.6V8.4z" />
          <path d="M12 7.5v5.5" />
          <path d="M12 16.4h.01" />
        </>
      );
    // TRIANGLE — the warning sign. Distinct from the octagon in outline at any size.
    case 'caution':
      return (
        <>
          <path d="M12 3.2 22 20H2z" />
          <path d="M12 9.5v4.5" />
          <path d="M12 17h.01" />
        </>
      );
    // CIRCLE + tick. Rounded, so it never reads as a warning shape at a glance.
    case 'ok':
      return (
        <>
          <circle cx="12" cy="12" r="9.2" />
          <path d="M7.8 12.3 10.7 15.2 16.3 9.4" />
        </>
      );
    // SQUARE — provenance. A document is a rectangle; the shape says "this came from a page".
    case 'info':
      return (
        <>
          <rect x="3.4" y="3.4" width="17.2" height="17.2" rx="3" />
          <path d="M8 9h8M8 13h8M8 17h5" />
        </>
      );
    default:
      return <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />;
  }
}

/**
 * Glyph + word together. This is the component feature code should reach for — it makes the
 * "never an icon alone" rule the default rather than a convention people remember.
 */
export function StateTag({
  state,
  children,
  size = 14,
}: {
  state: ClinicalState;
  children?: ReactNode;
  size?: number;
}): JSX.Element {
  return (
    <span className={`mk-state-tag mk-state-tag--${state}`}>
      <StateGlyph state={state} size={size} />
      <span>{children ?? STATE_LABEL[state]}</span>
    </span>
  );
}

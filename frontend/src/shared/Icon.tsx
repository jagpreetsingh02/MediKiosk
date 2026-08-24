/**
 * Inline SVG icons for the kiosk's tap options.
 *
 * These carry real weight: a patient who cannot read the label answers by recognising the
 * picture, so each one has to be identifiable at a glance without its caption. Line art at a
 * consistent 2.2px stroke, drawn to read at 54px, no colour dependency.
 */

interface Props {
  name: string;
  className?: string;
}

const paths: Record<string, JSX.Element> = {
  pain: (
    <>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.9 2.9M15.5 15.5l2.9 2.9M18.4 5.6l-2.9 2.9M8.5 15.5l-2.9 2.9" />
      <circle cx="12" cy="12" r="3.2" />
    </>
  ),
  fever: (
    <>
      <path d="M10 13.5V5a2 2 0 1 1 4 0v8.5" />
      <circle cx="12" cy="17" r="3.4" />
      <path d="M16.5 7h3M16.5 10h2" />
    </>
  ),
  cough: (
    <>
      <path d="M4 15a4.5 4.5 0 0 1 4.5-4.5h1A3.5 3.5 0 0 0 13 7V5" />
      <path d="M8.5 19.5c-2 0-3.5-1.4-3.5-3.2" />
      <path d="M15 9.5l2.5-1.5M16 13h3M15.5 16.5l2.5 1.5" />
    </>
  ),
  stomach: (
    <>
      <path d="M8 4v5.5a5 5 0 0 0 5 5h.5a3.5 3.5 0 0 1 0 7H11" />
      <path d="M8 4h4" />
    </>
  ),
  weakness: (
    <>
      <circle cx="12" cy="5.5" r="2.5" />
      <path d="M12 8v6M12 14l-3 6M12 14l3 6M7.5 11l4.5 1 4.5-1" />
    </>
  ),
  injury: (
    <>
      <path d="M4 12h4l2-4 3 8 2-4h5" />
      <path d="M3 5h18v14H3z" opacity="0.25" />
    </>
  ),
  skin: (
    <>
      <path d="M4 6h16v12H4z" />
      <circle cx="8.5" cy="10" r="1.1" />
      <circle cx="13" cy="13.5" r="1.1" />
      <circle cx="16" cy="8.8" r="1.1" />
      <circle cx="10" cy="15" r="1.1" />
    </>
  ),
  checkup: (
    <>
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M15 3v4h4" />
      <path d="M9.5 13.5h5M12 11v5" />
    </>
  ),
  other: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M9.5 9.5a2.6 2.6 0 1 1 3.2 2.5v1.6" />
      <circle cx="12.2" cy="16.6" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  head: (
    <>
      <path d="M15.5 20v-2.6c0-1 .5-1.6 1.2-2.3A6.8 6.8 0 1 0 8 17v3" />
      <path d="M13 10.5a1.6 1.6 0 1 0-2.4-1.4" />
    </>
  ),
  chest: (
    <>
      <path d="M12 20s-6-3.8-6-8.4A3.6 3.6 0 0 1 12 9a3.6 3.6 0 0 1 6 2.6C18 16.2 12 20 12 20z" />
      <path d="M4 6l3 1M20 6l-3 1" />
    </>
  ),
  abdomen: (
    <>
      <ellipse cx="12" cy="13" rx="6.5" ry="7" />
      <path d="M12 10.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />
    </>
  ),
  back: (
    <>
      <path d="M12 3v18" />
      <path d="M9 5h6M9 8.5h6M9 12h6M9 15.5h6M9 19h6" />
    </>
  ),
  limbs: (
    <>
      <circle cx="12" cy="4.5" r="2" />
      <path d="M12 6.5v6M12 12.5l-3.5 7M12 12.5l3.5 7M6.5 9l5.5 1.5L17.5 9" />
    </>
  ),
  joints: (
    <>
      <path d="M6 5v5a3 3 0 0 0 3 3" />
      <path d="M18 19v-5a3 3 0 0 0-3-3" />
      <circle cx="12" cy="13" r="2.6" />
    </>
  ),
  throat: (
    <>
      <path d="M9 3v4.5a3 3 0 0 0 6 0V3" />
      <path d="M7.5 12h9M8.5 16h7M9.5 20h5" />
    </>
  ),
  whole_body: (
    <>
      <circle cx="12" cy="4.5" r="2.2" />
      <path d="M12 7v7M12 14l-3 6M12 14l3 6M7 10h10" />
      <circle cx="12" cy="12" r="10" opacity="0.22" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="2.5" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
    </>
  ),
  speaker: (
    <>
      <path d="M4 9.5h3.5L12 5.5v13L7.5 14.5H4z" />
      <path d="M15.5 9.5a4 4 0 0 1 0 5M18 7a7.5 7.5 0 0 1 0 10" />
    </>
  ),
  camera: (
    <>
      <path d="M3 7.5h4l1.5-2h7L17 7.5h4v11H3z" />
      <circle cx="12" cy="13" r="3.6" />
    </>
  ),
  check: <path d="M4.5 12.5l5 5 10-11" />,
  cross: <path d="M6 6l12 12M18 6L6 18" />,
  // Navigation, distinct from the `back` body-part glyph. A ✕ on the Back control
  // read as "close the interview", which is not what it does.
  arrowLeft: <path d="M19 12H5M11 6l-6 6 6 6" />,
  arrowRight: <path d="M5 12h14M13 6l6 6-6 6" />,
};

const FACES: Record<number, JSX.Element> = {
  0: <><circle cx="12" cy="12" r="9" /><circle cx="9" cy="10" r="0.9" fill="currentColor" stroke="none" /><circle cx="15" cy="10" r="0.9" fill="currentColor" stroke="none" /><path d="M8 14.5c1.2 1.4 2.5 2 4 2s2.8-.6 4-2" /></>,
  2: <><circle cx="12" cy="12" r="9" /><circle cx="9" cy="10" r="0.9" fill="currentColor" stroke="none" /><circle cx="15" cy="10" r="0.9" fill="currentColor" stroke="none" /><path d="M8.5 14.8c1 .9 2.1 1.3 3.5 1.3s2.5-.4 3.5-1.3" /></>,
  4: <><circle cx="12" cy="12" r="9" /><circle cx="9" cy="10" r="0.9" fill="currentColor" stroke="none" /><circle cx="15" cy="10" r="0.9" fill="currentColor" stroke="none" /><path d="M8.5 15h7" /></>,
  6: <><circle cx="12" cy="12" r="9" /><circle cx="9" cy="10" r="0.9" fill="currentColor" stroke="none" /><circle cx="15" cy="10" r="0.9" fill="currentColor" stroke="none" /><path d="M8.5 16c1-.9 2.1-1.3 3.5-1.3s2.5.4 3.5 1.3" /><path d="M7 8l2.5 1M17 8l-2.5 1" /></>,
  8: <><circle cx="12" cy="12" r="9" /><path d="M7.6 9.4l2.6 1.4M16.4 9.4l-2.6 1.4" /><path d="M8 16.5c1.2-1.4 2.5-2 4-2s2.8.6 4 2" /></>,
  10: <><circle cx="12" cy="12" r="9" /><path d="M7.6 9l2.8 1.8M16.4 9l-2.8 1.8" /><ellipse cx="12" cy="16" rx="3.2" ry="2.4" /><path d="M4.5 6.5l1.8 1.4M19.5 6.5l-1.8 1.4" /></>,
};

export function Icon({ name, className }: Props): JSX.Element | null {
  const shape = paths[name];
  if (!shape) return null;
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {shape}
    </svg>
  );
}

export function FaceIcon({ level }: { level: number }): JSX.Element {
  const nearest = [0, 2, 4, 6, 8, 10].reduce((best, candidate) =>
    Math.abs(candidate - level) < Math.abs(best - level) ? candidate : best,
  );
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {FACES[nearest]}
    </svg>
  );
}

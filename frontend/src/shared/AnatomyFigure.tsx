/**
 * The hero figure: an anatomical plate that turns as the page scrolls.
 *
 * WHY THIS IS SVG AND NOT WEBGL. A kiosk is a low-powered machine in a hospital
 * corridor and this is the first thing it paints. Three hundred kilobytes of
 * WebGL runtime plus a model download, to render a shape that is fundamentally
 * line art, is a cost the surface cannot justify — and a canvas cannot inherit
 * `currentColor`, scale to any viewport without resampling, or be read by a
 * screen reader. What actually sells rotation is *parallax between depths*, and
 * CSS `preserve-3d` gives that for free.
 *
 * So the figure is five flat plates standing at different `translateZ`. Turning
 * the group slides them across each other at different rates, which is exactly
 * the cue the eye reads as solidity. The plates are:
 *
 *      -90px  the orbit ring and measurement grid — the instrument it stands in
 *      -34px  the body silhouette, soft and unlit
 *        0px  the skeleton: bones, joints, the load-bearing drawing
 *      +38px  the vital nodes and the pulse trace
 *      +74px  a specular sheen that tracks the cursor
 *
 * THE ROTATION IS BOUNDED, AND THAT IS THE DESIGN. It runs from −16° to +30°
 * across the whole page and never approaches edge-on, where stacked plates
 * degenerate into lines and the illusion collapses. The brief asks for movement
 * that feels "physically connected to scroll position" rather than spinning:
 * bounded travel is what makes it read as a figure turning to face you rather
 * than as an object on a turntable.
 *
 * The angle reads `--mk-scroll-eased` — the damped channel from
 * `useScrollProgress` — so the body carries momentum and settles, while
 * anything positional on the page reads the raw channel and stays glued to the
 * scrollbar. That split is the whole reason the hook publishes two numbers.
 */
import { useCursorField } from '../design/useCursorField';

/**
 * Half a body, mirrored. Drawn from the crown down the outside of the arm, back
 * up the inside, out over the hip, down the outside of the leg, and home along
 * the inside — so one path plus one mirrored `<use>` closes into a whole
 * silhouette that is symmetrical to the pixel. Hand-balancing two halves would
 * never be, and the brief asks for symmetry.
 */
const SILHOUETTE_HALF = `
  M200 24
  C224 24 242 44 242 74
  C242 98 232 116 217 126
  L217 148
  C252 156 280 170 291 193
  C302 217 308 256 306 296
  C305 327 300 357 295 385
  C293 399 296 411 302 421
  C307 429 304 437 296 436
  C289 435 284 429 281 419
  C275 399 270 372 267 345
  C264 369 260 392 256 410
  C263 446 266 479 262 513
  C258 550 252 585 248 620
  C245 649 243 678 242 702
  C242 719 246 731 253 739
  C258 745 254 752 246 752
  C237 752 231 745 229 735
  C224 707 221 663 217 620
  C213 578 208 541 203 513
  L200 513
`;

/** The load-bearing drawing. Everything here is a real landmark, positioned to
 *  the silhouette above — a skeleton that does not fit its body reads as a
 *  mistake even to someone who could not name the bone. */
const JOINTS: [number, number, number][] = [
  // shoulders, elbows, wrists
  [151, 201, 5.5],
  [249, 201, 5.5],
  [131, 300, 4.5],
  [269, 300, 4.5],
  [120, 396, 4],
  [280, 396, 4],
  // hips, knees, ankles
  [177, 419, 5],
  [223, 419, 5],
  [173, 560, 4.5],
  [227, 560, 4.5],
  [171, 706, 4],
  [229, 706, 4],
];

interface Props {
  /** 0–1. How far the figure has turned. Supplied through CSS by the hero's
   *  scroll channel; the prop exists so the component can be placed and posed
   *  in isolation without a scroll container. */
  className?: string;
}

export function AnatomyFigure({ className = '' }: Props): JSX.Element {
  // Its own cursor field, tracked globally: the sheen should follow the pointer
  // anywhere in the hero, not only across the 400px the figure occupies.
  const field = useCursorField<HTMLDivElement>({ global: true, smoothing: 0.08 });

  return (
    <div
      ref={field}
      className={`anat ${className}`.trim()}
      // Decorative. Everything it depicts is stated in the prose beside it, and
      // a screen reader announcing "diagram of a human body" adds nothing a
      // patient or a judge can act on.
      aria-hidden="true"
    >
      <div className="anat__space">
        {/* ---- plate 1: the instrument the figure stands in ---- */}
        <svg className="anat__plate anat__plate--grid" viewBox="0 0 400 800" fill="none">
          <circle className="anat__ring" cx="200" cy="400" r="272" />
          <circle className="anat__ring anat__ring--inner" cx="200" cy="400" r="196" />
          {/* Measurement ticks around the ring: the figure is being observed,
              which is the difference between a mascot and a clinical plate. */}
          {Array.from({ length: 48 }, (_, index) => {
            const angle = (index / 48) * Math.PI * 2;
            const major = index % 4 === 0;
            const r1 = major ? 254 : 264;
            return (
              <line
                key={index}
                className={major ? 'anat__tick anat__tick--major' : 'anat__tick'}
                x1={200 + Math.cos(angle) * r1}
                y1={400 + Math.sin(angle) * r1}
                x2={200 + Math.cos(angle) * 272}
                y2={400 + Math.sin(angle) * 272}
              />
            );
          })}
          {[168, 400, 632].map((y) => (
            <line key={y} className="anat__rule" x1="8" y1={y} x2="392" y2={y} />
          ))}
        </svg>

        {/* ---- plate 2: the body ---- */}
        <svg className="anat__plate anat__plate--body" viewBox="0 0 400 800" fill="none">
          <defs>
            <linearGradient id="anatBody" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.96" />
              <stop offset="46%" stopColor="#eceef1" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#cfd4dc" stopOpacity="0.82" />
            </linearGradient>
          </defs>
          <g className="anat__body">
            <path d={SILHOUETTE_HALF} />
            <path d={SILHOUETTE_HALF} transform="scale(-1 1) translate(-400 0)" />
          </g>
        </svg>

        {/* ---- plate 3: the skeleton ---- */}
        <svg className="anat__plate anat__plate--bone" viewBox="0 0 400 800" fill="none">
          <g className="anat__bone">
            {/* spine — the one curve in the drawing, because a straight spine
                is the tell that nobody looked at a real one */}
            <path d="M200 150 C206 210 194 268 200 330 C205 380 197 400 200 419" />
            <path d="M151 201 L249 201" />
            <path d="M177 419 L223 419" />
            {/* ribs */}
            {[[228, 22], [258, 30], [288, 34], [316, 31]].map(([y, spread]) => (
              <g key={y}>
                <path d={`M198 ${y - 8} C${198 - spread} ${y - 6} ${186 - spread} ${y + 10} ${196} ${y + 20}`} />
                <path d={`M202 ${y - 8} C${202 + spread} ${y - 6} ${214 + spread} ${y + 10} ${204} ${y + 20}`} />
              </g>
            ))}
            {/* limbs */}
            <path d="M151 201 L131 300 L120 396" />
            <path d="M249 201 L269 300 L280 396" />
            <path d="M177 419 L173 560 L171 706" />
            <path d="M223 419 L227 560 L229 706" />
            {/* skull */}
            <ellipse cx="200" cy="82" rx="33" ry="42" />
            <path d="M181 108 L219 108" />
          </g>
          <g className="anat__joint">
            {JOINTS.map(([cx, cy, r]) => (
              <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} />
            ))}
          </g>
        </svg>

        {/* ---- plate 4: what the record actually holds ---- */}
        <svg className="anat__plate anat__plate--vitals" viewBox="0 0 400 800" fill="none">
          {/* The same pulse-into-a-line reading as the wordmark: a vital sign
              becoming a continuous record. Drawn across the chest because that
              is where it is measured. */}
          <path
            className="anat__pulse"
            d="M96 252 H150 l14 -26 18 52 15 -34 11 8 H304"
          />
          <g className="anat__node">
            <circle cx="186" cy="252" r="7" />
            <circle cx="200" cy="342" r="5.5" />
            <circle cx="164" cy="236" r="4.5" />
            <circle cx="222" cy="236" r="4.5" />
          </g>
        </svg>

        {/* ---- plate 5: the light on the glass ---- */}
        <div className="anat__sheen" />
      </div>
    </div>
  );
}

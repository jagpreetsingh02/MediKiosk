/**
 * The motion vocabulary. One place, so nothing improvises its own timing.
 *
 * Three rules this file exists to enforce:
 *
 *  1. DURATION FOLLOWS DISTANCE. A chip that tints on tap gets `fast`; a whole
 *     screen that replaces another gets `slow`. Using one duration everywhere is
 *     what makes an interface feel either sluggish or twitchy depending on which
 *     number was picked.
 *
 *  2. ENTRANCES EASE OUT, EXITS EASE IN. Something arriving should decelerate
 *     into place; something leaving should accelerate away. Reversing this is the
 *     single most common reason motion feels "off" without anyone being able to
 *     say why.
 *
 *  3. NOTHING LOOPS WITHOUT A REASON. The only continuous animation in the
 *     product is the microphone listening ring and the OCR progress rail, both of
 *     which represent a process that is genuinely still running. Decorative loops
 *     are banned — on a kiosk they read as "the screen is broken".
 *
 * Reduced motion is handled in two places and both are needed: `base.css`
 * collapses CSS durations, and `useReducedMotion()` from Motion is respected by
 * the variants below via `reduced()`.
 */
import type { Transition, Variants } from 'motion/react';

/** Perceptual durations in seconds, mirroring `--mk-dur-*` in tokens.css. */
export const duration = {
  instant: 0.09,
  fast: 0.16,
  normal: 0.24,
  slow: 0.38,
  slower: 0.56,
} as const;

/** Cubic-bezier control points. Typed as fixed-length tuples because that is what
 *  Motion's `Easing` union accepts — a bare `number[]` is rejected. */
type Bezier = [number, number, number, number];

export const ease: Record<'out' | 'inOut' | 'in', Bezier> = {
  out: [0.22, 1, 0.36, 1],
  inOut: [0.65, 0, 0.35, 1],
  in: [0.7, 0, 0.84, 0],
};

/** A spring that settles without a visible wobble. For anything a finger moves. */
export const springSoft: Transition = {
  type: 'spring',
  stiffness: 420,
  damping: 38,
  mass: 1,
};

/** A touch more overshoot, for things that should feel like they landed. */
export const springPop: Transition = {
  type: 'spring',
  stiffness: 520,
  damping: 30,
  mass: 0.9,
};

export const tween = (d: number = duration.normal): Transition => ({
  duration: d,
  ease: ease.out,
});

// ------------------------------------------------------------------ variants

/**
 * The standard screen transition for the kiosk.
 *
 * `custom` carries the direction: +1 moving forward through the interview, -1
 * moving back. Back navigation animating backwards is not a flourish — it is the
 * only cue that distinguishes "you have returned to an earlier question" from
 * "a new question arrived", and the intake flow depends on that being obvious.
 */
export const screen: Variants = {
  enter: (dir: number = 1) => ({
    opacity: 0,
    x: dir * 26,
    filter: 'blur(5px)',
  }),
  center: {
    opacity: 1,
    x: 0,
    filter: 'blur(0px)',
    transition: { duration: duration.slow, ease: ease.out },
  },
  exit: (dir: number = 1) => ({
    opacity: 0,
    x: dir * -22,
    filter: 'blur(5px)',
    transition: { duration: duration.fast, ease: ease.in },
  }),
};

/** Cards, panels and list rows arriving. Pair with `stagger`. */
export const rise: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: duration.slow, ease: ease.out },
  },
  exit: {
    opacity: 0,
    y: -8,
    transition: { duration: duration.fast, ease: ease.in },
  },
};

/** A container that deals its children in. Keep `staggerChildren` small — a long
 *  cascade looks impressive once and wastes the patient's time every time after. */
export const stagger = (step: number = 0.045, delay: number = 0): Variants => ({
  hidden: {},
  visible: {
    transition: { staggerChildren: step, delayChildren: delay },
  },
});

/** Drawers and evidence panels sliding in from the right. */
export const drawer: Variants = {
  hidden: { x: '100%', opacity: 0.4 },
  visible: { x: 0, opacity: 1, transition: springSoft },
  exit: {
    x: '100%',
    opacity: 0.4,
    transition: { duration: duration.normal, ease: ease.in },
  },
};

/** Modals and sheets. */
export const sheet: Variants = {
  hidden: { opacity: 0, y: 28, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1, transition: springSoft },
  exit: {
    opacity: 0,
    y: 16,
    scale: 0.98,
    transition: { duration: duration.fast, ease: ease.in },
  },
};

export const fade: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: tween(duration.normal) },
  exit: { opacity: 0, transition: tween(duration.fast) },
};

/** Accordions and timeline events expanding. Height animation is deliberate here:
 *  it is the one case where the layout genuinely has to move and a cross-fade
 *  would leave the surrounding content jumping. */
export const expand: Variants = {
  hidden: { height: 0, opacity: 0 },
  visible: {
    height: 'auto',
    opacity: 1,
    transition: {
      height: { duration: duration.normal, ease: ease.out },
      opacity: { duration: duration.fast, delay: 0.06 },
    },
  },
  exit: {
    height: 0,
    opacity: 0,
    transition: {
      height: { duration: duration.fast, ease: ease.in },
      opacity: { duration: duration.instant },
    },
  },
};

/** Press feedback. Applied via `whileTap` so it works for touch and mouse alike. */
export const press = { scale: 0.975 } as const;
export const liftHover = { y: -2 } as const;

/**
 * Strip travel out of a variant set when the user asked for reduced motion.
 *
 * Opacity is kept: a fade is not vestibular motion, and removing every cue makes
 * state changes genuinely harder to follow rather than kinder.
 */
export function reduced(on: boolean, variants: Variants): Variants {
  if (!on) return variants;
  return {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { duration: 0.01 } },
    enter: { opacity: 0 },
    center: { opacity: 1, transition: { duration: 0.01 } },
    exit: { opacity: 0, transition: { duration: 0.01 } },
  };
}

/**
 * The stage every route is played on, and the crossfade between them.
 *
 * One transition, used everywhere, so navigating never feels like a different
 * kind of event depending on where you clicked: the outgoing view falls back a
 * few pixels and blurs as it goes, the incoming view arrives from slightly in
 * front and sharpens. Combined it reads as depth rather than as a fade — the
 * old page recedes, the new one steps forward.
 *
 * `mode="popLayout"` rather than the default `"sync"`: with sync, both routes
 * occupy the flow at once and the page height jumps to the taller of the two
 * mid-transition, which on the physician screen means the whole review lurches.
 * popLayout takes the exiting view out of flow so the incoming one lays out
 * alone.
 *
 * The blur is the reason this needs `filter` and not just transform+opacity.
 * It is a compositor-friendly property here because the element is already
 * promoted for the transform, and it is what turns a crossfade into something
 * that reads as optical rather than as a dissolve. It is also strictly bounded:
 * 6px for 320ms, which no one reading the screen ever has to wait through.
 */
import type { ReactNode } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useLocation } from 'react-router-dom';
import { ease } from './motion';

export function RouteStage({ children }: { children: ReactNode }): JSX.Element {
  const { pathname } = useLocation();
  const prefersReduced = useReducedMotion() ?? false;

  if (prefersReduced) {
    // Not a shorter animation — none. A route change under reduced motion
    // should be a cut, which is also what makes it instant.
    return <div className="mk-stage">{children}</div>;
  }

  return (
    <AnimatePresence mode="popLayout" initial={false}>
      <motion.div
        key={pathname}
        className="mk-stage"
        initial={{ opacity: 0, y: 10, filter: 'blur(6px)' }}
        animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
        // The exit runs faster than the entrance, and carries its own
        // transition rather than a shared one. Equal timings make the gap
        // between two pages feel like a stall; clearing the old view early is
        // what makes the new one feel like it was already there.
        exit={{
          opacity: 0,
          y: -6,
          filter: 'blur(6px)',
          transition: { duration: 0.2, ease: ease.in },
        }}
        transition={{ duration: 0.32, ease: ease.out }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

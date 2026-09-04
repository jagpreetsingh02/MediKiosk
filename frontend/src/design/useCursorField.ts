/**
 * Pointer position as CSS custom properties, so the styling stays in CSS.
 *
 * The hook writes `--mk-mx`, `--mk-my` (0–1 within the element) and `--mk-mdist`
 * (0 at the centre, 1 at the far corner) onto a ref, and CSS does everything
 * else. That division matters: the alternative is re-rendering React on every
 * mousemove to pass a number into a style prop, which is a render storm on a
 * surface that is also running an interview state machine.
 *
 * Three things this must never do, and the whole file is shaped by them:
 *
 *  1. **Never run on touch.** A finger has no hover, so a tilt driven by
 *     pointer position either does nothing or fires once on tap and sticks.
 *     Gated on a real `(hover: hover) and (pointer: fine)` query, not on width.
 *  2. **Never run under reduced motion.** Cursor parallax is vestibular motion
 *     the user did not ask for.
 *  3. **Never write more than once a frame.** `pointermove` fires faster than
 *     the compositor can use, and writing a custom property invalidates style
 *     for the subtree each time.
 *
 * Values are also written as *smoothed* targets: raw pointer coordinates make
 * glass reflections snap, which reads as a bug rather than as a material.
 */
import { useEffect, useRef, type RefObject } from 'react';

interface Options {
  /** Track over the whole window rather than the element's own box. Used for
   *  the page ground, which reacts to the cursor wherever it is. */
  global?: boolean;
  /** 0–1. Lower is heavier. The default reads as glass rather than as a laser
   *  pointer; raise it for small controls where lag feels unresponsive. */
  smoothing?: number;
}

export function useCursorField<T extends HTMLElement>(
  options: Options = {},
): RefObject<T> {
  const { global = false, smoothing = 0.12 } = options;
  const ref = useRef<T>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    // Both gates, and both are necessary: a laptop with a touchscreen reports
    // coarse *and* fine pointers, and a user on that machine using the
    // trackpad should still get the effect.
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)');
    const still = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!fine.matches || still.matches) return;

    let targetX = 0.5;
    let targetY = 0.5;
    let currentX = 0.5;
    let currentY = 0.5;
    let frame = 0;
    let settled = false;

    const onMove = (event: PointerEvent): void => {
      const box = global
        ? { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight }
        : node.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) return;
      targetX = clamp((event.clientX - box.left) / box.width);
      targetY = clamp((event.clientY - box.top) / box.height);
      settled = false;
      if (!frame) frame = requestAnimationFrame(tick);
    };

    const tick = (): void => {
      currentX += (targetX - currentX) * smoothing;
      currentY += (targetY - currentY) * smoothing;

      const dx = (currentX - 0.5) * 2;
      const dy = (currentY - 0.5) * 2;
      // Normalised so the far corner is 1 rather than √2, which keeps every
      // consumer's arithmetic in 0–1 without each one dividing by root two.
      const distance = Math.min(Math.hypot(dx, dy) / Math.SQRT2, 1);

      node.style.setProperty('--mk-mx', currentX.toFixed(4));
      node.style.setProperty('--mk-my', currentY.toFixed(4));
      node.style.setProperty('--mk-mdist', distance.toFixed(4));

      // Stop the loop once the eased value has effectively arrived. Without
      // this the rAF runs forever behind a stationary cursor, which on a kiosk
      // is a permanent battery and thermal cost for nothing on screen.
      const arrived =
        Math.abs(targetX - currentX) < 0.0005 && Math.abs(targetY - currentY) < 0.0005;
      if (arrived) {
        if (settled) {
          frame = 0;
          return;
        }
        settled = true;
      }
      frame = requestAnimationFrame(tick);
    };

    const onLeave = (): void => {
      // Return to centre rather than freezing where the cursor left. A panel
      // stuck at a tilt after the pointer has gone reads as a rendering bug.
      targetX = 0.5;
      targetY = 0.5;
      settled = false;
      if (!frame) frame = requestAnimationFrame(tick);
    };

    const target: HTMLElement | Window = global ? window : node;
    target.addEventListener('pointermove', onMove as EventListener, { passive: true });
    target.addEventListener('pointerleave', onLeave as EventListener, { passive: true });

    return () => {
      target.removeEventListener('pointermove', onMove as EventListener);
      target.removeEventListener('pointerleave', onLeave as EventListener);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [global, smoothing]);

  return ref;
}

function clamp(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

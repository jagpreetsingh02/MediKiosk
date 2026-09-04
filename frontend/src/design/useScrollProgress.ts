/**
 * Scroll position as a smoothed 0–1 channel, published as a CSS custom property.
 *
 * The brief asks for two things that pull against each other: scrolling should
 * feel *highly responsive* — a small wheel movement must produce visible
 * feedback — while nothing on screen may jitter. Those are reconciled by
 * separating the two numbers this hook exposes:
 *
 *   `--mk-scroll`    the raw progress, snapped to the scroll position exactly.
 *                    Anything positional reads this: reveal thresholds, depth,
 *                    parallax offsets. It cannot lag, because a parallax layer
 *                    that trails the scroll by 100ms is the classic
 *                    "scrolljacked" feeling.
 *
 *   `--mk-scroll-eased`  the same value run through a critically-damped lerp.
 *                    Anything *rotational or inertial* reads this — the hero
 *                    figure above all — because a body that changes direction
 *                    the instant the wheel does has no mass, and mass is the
 *                    whole point of tying it to scroll.
 *
 * Writing custom properties on one element rather than setting React state is
 * deliberate for the same reason as `useCursorField`: scroll fires far faster
 * than React should re-render, and this surface is also running an interview.
 *
 * Under `prefers-reduced-motion` the eased channel is pinned to the raw one and
 * the loop never starts — the page still reveals, it simply does not glide.
 */
import { useEffect, useRef, type RefObject } from 'react';

interface Options {
  /** Measure this element's travel through the viewport instead of the page.
   *  0 when its top hits the bottom of the viewport, 1 when its bottom leaves
   *  the top — the standard "cover" range. */
  element?: boolean;
  /** 0–1. Lower is heavier. 0.1 gives a figure that feels like it weighs
   *  something without ever visibly lagging the page. */
  smoothing?: number;
}

export function useScrollProgress<T extends HTMLElement>(
  options: Options = {},
): RefObject<T> {
  const { element = false, smoothing = 0.1 } = options;
  const ref = useRef<T>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const still = window.matchMedia('(prefers-reduced-motion: reduce)');
    let target = 0;
    let eased = 0;
    let frame = 0;
    let settled = false;

    const measure = (): number => {
      if (element) {
        const box = node.getBoundingClientRect();
        const span = window.innerHeight + box.height;
        if (span <= 0) return 0;
        return clamp((window.innerHeight - box.top) / span);
      }
      const travel = document.documentElement.scrollHeight - window.innerHeight;
      return travel <= 0 ? 0 : clamp(window.scrollY / travel);
    };

    const publish = (): void => {
      node.style.setProperty('--mk-scroll', target.toFixed(4));
      node.style.setProperty('--mk-scroll-eased', eased.toFixed(4));
    };

    const tick = (): void => {
      eased += (target - eased) * smoothing;
      publish();
      if (Math.abs(target - eased) < 0.0002) {
        if (settled) {
          eased = target;
          publish();
          frame = 0;
          return;
        }
        settled = true;
      }
      frame = requestAnimationFrame(tick);
    };

    const onScroll = (): void => {
      target = measure();
      if (still.matches) {
        // No inertia to run: the raw value is the eased value, written once.
        eased = target;
        publish();
        return;
      }
      settled = false;
      if (!frame) frame = requestAnimationFrame(tick);
    };

    // Publish once before any scroll so a page loaded part-way down (a
    // refresh, a back-navigation, an anchor) renders in the right state
    // instead of animating in from zero.
    target = measure();
    eased = target;
    publish();

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [element, smoothing]);

  return ref;
}

function clamp(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

/**
 * Has the physician actually reached the end of the summary?
 *
 * ⛔ This is one half of Invariant 4's frontend gate. The other half — the attestation
 * checkbox — is in `CommitBar`. Read both together.
 *
 * WHY THE OLD MECHANISM WAS WRONG. It was a `scroll` handler on the summary column:
 *
 *     if (el.scrollTop + el.clientHeight >= el.scrollHeight - 96) setReviewed(true);
 *
 * A scroll event only fires if there is something to scroll. That single fact breaks it in
 * four separate ways, and every one of them ends with a physician who has genuinely read the
 * whole summary being told they have not, with no way to proceed:
 *
 *   1. SHORT SUMMARIES. A brief encounter — three complaints, no documents — fits the
 *      viewport. Nothing scrolls, no event fires, commit stays disabled forever. The shorter
 *      the consultation, the more completely the product breaks.
 *   2. ZOOM. At 200% the layout reflows; at 50% on a large display the summary fits. Both
 *      change whether a scrollbar exists at all.
 *   3. KEYBOARD-ONLY. `j`/`k` move the selection with `scrollIntoView({block:'nearest'})`,
 *      which does not scroll when the target is already visible. A physician can traverse
 *      every line to the last one without ever generating a qualifying scroll event.
 *   4. SHORT VIEWPORTS. A laptop in a side-by-side window, a rotated tablet.
 *
 * WHAT REPLACES IT. Two mechanisms, because "the end is visible" and "there is no end to
 * scroll to" are genuinely different questions:
 *
 *   * An IntersectionObserver on a sentinel element rendered after the last summary line.
 *     It fires when the end of the content is actually on screen, regardless of how it got
 *     there — scrolling, zooming, resizing, keyboard traversal, or a window that was always
 *     big enough. It is the direct measurement of the thing we care about.
 *
 *   * An explicit short-content branch. When the content fits its container there is no
 *     scrolling to observe and the sentinel is already visible, so this arms immediately.
 *     It is checked on mount and re-checked with a ResizeObserver, so a zoom change or a
 *     window resize re-evaluates rather than latching the wrong answer at mount.
 *
 * Both are one-way: once the end has been seen, it stays seen. Re-scrolling upward does not
 * un-review a summary the physician has already read to the bottom.
 *
 * IMPORTANT: reaching the end is NOT consent. It is a precondition for the attestation
 * checkbox to be meaningful — scroll position is a proxy for reading, and a proxy is not an
 * attestation. The physician ticks the box; that is the act this invariant is actually about.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface Result {
  /** Attach to the scrolling container (the summary column). */
  containerRef: (node: HTMLElement | null) => void;
  /** Render as the last child of the scrolled content, after the final summary line. */
  sentinelRef: (node: HTMLElement | null) => void;
  /** True once the end of the summary has been on screen, by any route. */
  reachedEnd: boolean;
  /** Reset when a different patient is opened. */
  reset: () => void;
}

export function useSummaryReviewed(): Result {
  const [reachedEnd, setReachedEnd] = useState(false);
  const container = useRef<HTMLElement | null>(null);
  const sentinel = useRef<HTMLElement | null>(null);
  const observer = useRef<IntersectionObserver | null>(null);
  const resize = useRef<ResizeObserver | null>(null);

  /** The short-content case: nothing to scroll, so the end is already in view.
   *  A one-pixel tolerance absorbs sub-pixel layout rounding, which at fractional zoom
   *  levels is routinely enough to make a non-scrolling element report a scrollHeight one
   *  pixel larger than its clientHeight. */
  const armIfNothingToScroll = useCallback(() => {
    const el = container.current;
    if (el && el.scrollHeight <= el.clientHeight + 1) setReachedEnd(true);
  }, []);

  const attachObservers = useCallback(() => {
    observer.current?.disconnect();
    resize.current?.disconnect();

    const root = container.current;
    const mark = sentinel.current;
    if (!root || !mark) return;

    // `root: null` would observe against the viewport, which is wrong here: the summary
    // scrolls inside its own column, so the column is the root.
    observer.current = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setReachedEnd(true);
      },
      { root, threshold: 0.01 },
    );
    observer.current.observe(mark);

    // Zoom, window resize and late-arriving content all change whether the column
    // scrolls at all. Re-evaluating on resize is what stops the short-content branch
    // latching a stale answer from mount.
    resize.current = new ResizeObserver(armIfNothingToScroll);
    resize.current.observe(root);
    armIfNothingToScroll();
  }, [armIfNothingToScroll]);

  const containerRef = useCallback(
    (node: HTMLElement | null) => {
      container.current = node;
      attachObservers();
    },
    [attachObservers],
  );

  const sentinelRef = useCallback(
    (node: HTMLElement | null) => {
      sentinel.current = node;
      attachObservers();
    },
    [attachObservers],
  );

  useEffect(() => {
    return () => {
      observer.current?.disconnect();
      resize.current?.disconnect();
    };
  }, []);

  const reset = useCallback(() => {
    setReachedEnd(false);
    // A new patient's summary replaces the old one; re-measure rather than waiting for a
    // scroll that may never come if the new summary is shorter than the viewport.
    requestAnimationFrame(armIfNothingToScroll);
  }, [armIfNothingToScroll]);

  return { containerRef, sentinelRef, reachedEnd, reset };
}

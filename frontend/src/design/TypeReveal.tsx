/**
 * Text that types itself in, flares once as it lands, and then holds still.
 *
 * Reserved for the four or five statements on the site that are worth waiting
 * for — the hero line, a section title, the sentence that says what MediKiosk
 * refuses to do. Applying it to body copy would be a category error: typing is
 * a *delay* dressed as an effect, and delaying a paragraph someone is trying to
 * read is hostile.
 *
 * Three details do most of the work:
 *
 *  1. **The layout never shifts.** The full string is rendered underneath at
 *     zero opacity and the typed copy is absolutely positioned over it, so the
 *     element occupies its final box from the first frame. A typing effect that
 *     grows its own container reflows everything below it, line by line, for
 *     the whole duration.
 *  2. **Screen readers get the finished sentence, once.** The visible characters
 *     are `aria-hidden`; the real text sits in the reserving copy. A live region
 *     announcing one character at a time is unusable.
 *  3. **The glow is on the ink, not behind it.** A `text-shadow` bloom that
 *     fades over ~700ms, rather than a background flash — so contrast against
 *     the frost ground never drops while it plays.
 *
 * Under `prefers-reduced-motion` the text is simply there, at full opacity,
 * with no typing and no flare.
 */
import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'motion/react';

interface Props {
  text: string;
  /** Element to render. A heading must stay a heading. */
  as?: 'h1' | 'h2' | 'h3' | 'p' | 'span' | 'div';
  className?: string;
  /** ms before the first character. Stagger a stack of these by hand rather
   *  than nesting them in a variant tree — the timing is the composition. */
  delay?: number;
  /** ms per character. ~26 reads as brisk and deliberate; below ~15 it stops
   *  reading as typing and starts reading as a flicker. */
  speed?: number;
  /** Fires once the flare has faded, so a caller can chain the next line. */
  onSettled?: () => void;
}

type Phase = 'waiting' | 'typing' | 'flaring' | 'settled';

export function TypeReveal({
  text,
  as: Tag = 'span',
  className = '',
  delay = 0,
  speed = 26,
  onSettled,
}: Props): JSX.Element {
  const prefersReduced = useReducedMotion() ?? false;
  const [count, setCount] = useState(prefersReduced ? text.length : 0);
  const [phase, setPhase] = useState<Phase>(prefersReduced ? 'settled' : 'waiting');
  // Held in a ref so a caller passing an inline arrow does not restart the
  // animation on every parent render.
  const settledRef = useRef(onSettled);
  settledRef.current = onSettled;

  useEffect(() => {
    if (prefersReduced) {
      setCount(text.length);
      setPhase('settled');
      settledRef.current?.();
      return;
    }

    setCount(0);
    setPhase('waiting');
    const timers: number[] = [];

    timers.push(
      window.setTimeout(() => {
        setPhase('typing');
        let index = 0;
        const step = window.setInterval(() => {
          index += 1;
          setCount(index);
          if (index >= text.length) {
            window.clearInterval(step);
            // The flare fires the instant the last character lands, which is
            // what makes it read as the sentence *completing* rather than as a
            // separate decorative pulse some time afterwards.
            setPhase('flaring');
            timers.push(
              window.setTimeout(() => {
                setPhase('settled');
                settledRef.current?.();
              }, 720),
            );
          }
        }, speed);
        timers.push(step);
      }, delay),
    );

    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [text, delay, speed, prefersReduced]);

  return (
    <Tag className={`mk-type mk-type--${phase} ${className}`.trim()} data-phase={phase}>
      {/* Reserves the final box. Present for assistive tech and for copy-paste;
          invisible, but never `visibility: hidden`, which would take it out of
          the accessibility tree along with the layout. */}
      <span className="mk-type__reserve">{text}</span>
      <span className="mk-type__ink" aria-hidden="true">
        {text.slice(0, count)}
        {phase === 'typing' && <span className="mk-type__caret" />}
      </span>
    </Tag>
  );
}

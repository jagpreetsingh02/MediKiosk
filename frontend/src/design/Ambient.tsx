/**
 * The ground. One video element, mounted once, for the entire application.
 *
 * This is the piece that does the most work toward "you never left the product". The hero's
 * background is a looping video; if each route rendered its own copy, every navigation would
 * restart the footage from frame zero and the ground would visibly jump — the exact seam this
 * whole exercise exists to remove. So it is mounted *above* the router, outside `Routes`,
 * and it simply never unmounts. Walking from the hero into consent into the physician
 * workspace, the footage keeps playing on the same frame it was already on.
 *
 * What does change is its *depth*. The hero shows it at full strength because there is almost
 * nothing on top of it. A screen carrying a clinical brief cannot: text over moving footage is
 * unreadable, and motion behind a form is a distraction a patient does not need. So the ground
 * recedes as you go deeper — dimmer, blurred, slightly scaled — over 700ms, which is slow
 * enough to read as the same room rather than a different one.
 *
 *   hero      full strength, sharp, unblurred
 *   surface   dimmed and blurred — patient screens, still spacious
 *   deep      dimmed further — the physician workspace, where density wins
 *
 * The video is remote (CloudFront). The kiosk is expected to run with no network at all, so
 * everything below it is designed to work without it: the black ground and the ambient
 * gradient pools are CSS, they paint first, and if the video never arrives the product simply
 * has a still background. Nothing is laid out relative to the footage.
 */
import { useEffect, useRef } from 'react';

/** The hero's own background footage, byte-identical URL. */
const AMBIENT_SRC =
  'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260715_082433_69699cf8-444b-4484-93cc-053e57896dfd.mp4';

export type AmbientDepth = 'hero' | 'surface' | 'deep';

interface Props {
  depth: AmbientDepth;
}

export function Ambient({ depth }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);

  // Autoplay, exactly as the hero primes it: muted first, then play, and a failure is a
  // console note rather than an error — a blocked autoplay leaves the gradient ground, which
  // is a perfectly good screen.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = true;
    video.play().catch(() => {
      /* autoplay blocked, or no network — the CSS ground stands in */
    });
  }, []);

  // Decoding video costs power for a background nobody is looking at. When the tab is hidden
  // the footage pauses and resumes on return; it is the same frame either way because the
  // element is never torn down.
  useEffect(() => {
    function onVisibility() {
      const video = videoRef.current;
      if (!video) return;
      if (document.hidden) video.pause();
      else void video.play().catch(() => {});
    }
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  return (
    <div className="mk-ambient" data-depth={depth} aria-hidden="true">
      <video
        ref={videoRef}
        className="mk-ambient__video"
        autoPlay
        loop
        muted
        playsInline
        preload="auto"
        src={AMBIENT_SRC}
      />
      <div className="mk-ambient__veil" />
    </div>
  );
}

/**
 * The four faces in the hero's badge pill.
 *
 * The original loads four Pexels photographs over the network. This kiosk is expected to run
 * with no network at all, and four broken images in the very first element a patient sees is
 * not a first impression worth keeping — so they are drawn instead, at the same 20/24px size,
 * the same -0.5rem overlap and the same 2px white/18 border. Four distinct gradients so the
 * strip still reads as four people rather than one repeated shape.
 */
export interface HeroAvatar {
  id: string;
  from: string;
  to: string;
  glyph: string;
}

export const AVATARS: HeroAvatar[] = [
  { id: 'a', from: '#8f9bbd', to: '#4a5789', glyph: 'a' },
  { id: 'b', from: '#7fbfa8', to: '#3d6d5c', glyph: 'b' },
  { id: 'c', from: '#a9a2c4', to: '#5b5480', glyph: 'c' },
  { id: 'd', from: '#b0a898', to: '#6b6357', glyph: 'd' },
];

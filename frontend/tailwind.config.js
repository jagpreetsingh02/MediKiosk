/**
 * Scoped, on purpose. The rest of this app is a hand-built `--mk-*` token system
 * (see src/design/theme.css) — this config exists ONLY to support shadcn-style
 * components vendored into src/components/ui/, not to Tailwind-ify the product.
 *
 * `content` is narrowed to that one folder (plus its own demo files) so the JIT
 * compiler never has a reason to scan the other ~90 existing components — nothing
 * added here can generate a utility class that collides with anything they use.
 *
 * `corePlugins.preflight: false` is not optional: Tailwind's base layer resets
 * global element selectors (button, ul, h1, ...), and this app already has 84
 * existing buttons and a full CSS reset of its own (src/design/base.css). Leaving
 * preflight on would silently reskin every one of them the moment this file is
 * imported.
 */
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./src/components/ui/**/*.{ts,tsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
      },
    },
  },
  plugins: [],
};

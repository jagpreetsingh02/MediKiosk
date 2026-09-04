# Neue Machina goes here

The display face for MediKiosk — headings, the wordmark, numerals and technical labels — is
**Neue Machina** by Pangram Pangram. It is a commercial font and its files are deliberately
**not committed to this repository**.

Drop these three files into this directory and every heading in the product picks them up
with no code change:

```
NeueMachina-Regular.woff2
NeueMachina-Medium.woff2
NeueMachina-Ultrabold.woff2
```

The `@font-face` blocks are already written, at the foot of `src/design/tokens.css`.

**Until then the product uses Space Grotesk**, bundled through `@fontsource-variable` and
therefore self-hosted and available with no network — which matters, because a kiosk is
expected to run without one. Space Grotesk is the closest free face in character: geometric,
squared terminals, a mechanical single-storey `a`. Nothing looks broken while it is standing
in, and nothing needs changing when it stops.

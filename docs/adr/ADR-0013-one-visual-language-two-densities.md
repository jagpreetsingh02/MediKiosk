# ADR-0013 — One visual language, two densities (supersedes the visual half of ADR-0008)

**Context.** ADR-0008 decided that the kiosk and the physician screen share no components, on
the grounds that they solve opposite problems. That reasoning was sound and most of it still
holds. But it was implemented as two *design languages* — a light, porcelain patient surface
and a dark, instrument-grade clinical one — and a separate landing page in a third style. Once
a hero page in `ui/` became the product's front door, the cost of that decision became
concrete and easy to state:

A patient taps **Start** on a black, glass, video-backed landing page and arrives at a white
form. A physician opens a link from that same page and arrives at a dark workspace built from
different type at different weights with different controls. Nothing carries across the
boundary: not the ground, not the typeface, not the button, not the hover. As far as anyone
using it can tell, they have been handed to a different piece of software mid-consultation —
three times, on the happy path.

That is not a theme preference. It is the product failing to read as one product at exactly
the moments it is asking someone to trust it with a medical history.

**Decision.** The hero in `ui/` is the visual specification for the whole application. Its
material — a near-transparent fill, a 4px backdrop blur, an inset white lip highlight, and a
1.4px gradient border drawn with the `mask-composite: exclude` trick so it brightens at the
top and bottom edge and vanishes through the middle — is lifted verbatim into
`design/glass.css` and is what every button, card, chip, field, sheet, drawer and panel in the
product is now made of. Inter at 400/300 with tight tracking is the only Latin face. The
hero's two durations, 300ms and 500ms, are the entire motion vocabulary. Its single hover
behaviour — the glass brightens to white/10, nothing lifts or scales — is the hover behaviour
everywhere.

**The surfaces no longer differ in theme. They differ in density.** `data-surface="kiosk"` and
`data-surface="clinical"` now change only sizes and spacing: 60/76px targets against 38/44px,
reading sizes one step apart, gutters one step apart. Not one colour differs between them.

Two structural pieces carry the continuity that tokens cannot:

- **`design/Ambient.tsx`** — the hero's background video, mounted *once*, above the router,
  for the life of the application. It never unmounts; it only changes depth (`hero` /
  `surface` / `deep`) over 700ms. A per-route copy would restart the footage from frame zero
  on every navigation, and the ground would visibly cut — the exact seam this ADR exists to
  close. It is the single strongest continuity cue in the product.
- **`design/AppNav.tsx`** — the hero's navigation bar, generalised. Its centre slot holds the
  hero's links, the kiosk's progress rail, or the physician's view switcher. All three are the
  same pill in the same place, so "where am I" is answered by the same object on every screen.

**What ADR-0008 keeps.** Its actual subject — that the two surfaces do not share *components* —
still stands, and is why `KioskApp` and `PhysicianApp` remain separate trees with separate
stylesheets and one component per file. What is superseded is the inference that different
problems require different *looks*. A shared design system with size variants was rejected
there as producing `<Button size="huge">` that is neither properly huge nor properly compact.
That risk is real and the answer to it is the density split above: the variants change
geometry only, so neither surface has to compromise on target size or information density to
share a material with the other.

**The accessibility trade, stated plainly.** ADR-0008's light kiosk had a genuine clinical
argument behind it: contrast sensitivity falls with age, a kiosk stands under hospital
fluorescents, and a dark UI in a bright room is the worst combination for an elderly patient.
Unifying on the hero's dark ground gives that up, and it is the one real cost of this
decision. It is mitigated, not eliminated: patient-side body text sits at 17px minimum against
white-on-black at ≥0.9 opacity, targets stay at 60px and above, the ambient video is veiled
most heavily exactly where the content column sits, and the veil plus the panes' own blur keep
text contrast well clear of AA. If a real kiosk in a real corridor shows this to be
insufficient, the fix is a light density variant of the *same* material — the token layer is
built so that is a change in one block — and not a return to two products.

**Alternatives.**

- *Keep the hero as a separate landing page and leave the app alone.* This is the status quo
  ante and it is what produced the problem.
- *Restyle the hero to match the app.* Explicitly ruled out: the hero's design is the
  requirement, not a candidate.
- *Adopt Tailwind so the hero's markup could be pasted in unchanged.* Rejected — it would drop
  a preflight reset on top of ~13k lines of existing stylesheet and break more than it saved.
  Each hero utility is instead written out at its exact computed value in `hero/hero.css`, with
  the source values recorded in that file's header comment.

**Consequences.**

- The token layer (`design/tokens.css`) is now the leverage point for the entire product: the
  `-v2` stylesheets and the primitives already read only from it, so re-theming happens in one
  block rather than forty files.
- The legacy variables in `styles/tokens.css` are now pure aliases onto the semantic layer.
  Screens still written against `--paper` and `--ink` follow the shared ground automatically,
  which is what lets `kiosk.css` and `physician.css` be deleted screen by screen with no visual
  step at any point.
- `.evi-frame` is the one deliberately opaque white surface left. It holds a scanned
  prescription, and a page photographed on paper is white. Evidence is displayed, never styled.
- The browser suites no longer wait on `networkidle`. The ambient video is a permanently open
  connection, so the network is never idle; every navigation waits on the DOM and then on an
  explicit selector, which was always the stronger assertion.
- One class of bug is now easy to reintroduce and worth naming: the glass recipe carries
  `overflow: hidden`, and copying it wholesale onto a layout container clips that container's
  controls out of the hit area. The gradient edge does not need clipping — it is an `inset: 0`
  masked pseudo-element and cannot paint outside its own box. Only `.mk-card--flush` keeps it.

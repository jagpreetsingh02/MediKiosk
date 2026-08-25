# ADR-0008 — The kiosk and the physician screen share no components

> **Partly superseded by [ADR-0013](ADR-0013-one-visual-language-two-densities.md).** The
> decision below — that the two surfaces share no *components* — still stands. The inference
> that they should therefore look unrelated does not: they now share one visual language and
> differ only in density. Read this together with ADR-0013.

**Context.** Both surfaces are React, in one bundle, hitting one API. The instinct is a shared
component library.

**Decision.** They share the typed API client and nothing else. Separate stylesheets, separate
components, separate design languages.

The two are solving opposite problems. The kiosk serves a first-time, possibly non-literate,
elderly patient standing at a machine: 96px minimum targets, 22px minimum body text, one
decision on screen at a time, everything readable at arm's length in a bright corridor. The
physician screen serves someone reading their fortieth history of the morning in ninety
seconds: dense, keyboard-driven, tabular numbers, three panels at once.

**Alternatives.** A shared design system with size variants — which is how you end up with a
`<Button size="huge">` that is neither properly huge nor properly compact, and a set of tokens
that no longer means anything on either surface.

**Consequences.** Some duplication, deliberately. When a shared abstraction is genuinely
needed it will be obvious, and it will be extracted then rather than predicted now. The brief
also asks for one component per file so pieces can be customised independently; a shared
library works against that.

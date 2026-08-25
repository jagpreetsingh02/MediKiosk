"""The print variant of the design system.

THE SCREEN THEME CANNOT BE PRINTED. It is white text on near-black glass, with blur, gradient
and a video behind it. On paper that is either a solid black page or, once a printer drops
the background, white text on white. Neither is a document.

So this is a genuine translation rather than a filter: the SAME hues, re-derived for ink on
white. The periwinkle accent stays periwinkle and the violet evidence colour stays violet —
someone holding the printout and looking at the screen should see the same product — but
every value is darkened until it is legible as ink, and every surface becomes white or a very
pale tint with a SOLID border where the screen used a translucent edge.

⛔ NO GREEN, same as the screen theme. `ok` is the accent, not a second hue.

WCAG AA ON PAPER, checked rather than eyeballed. Body ink against white must clear 4.5:1, and
`tests/test_print_contrast.py` computes it. Printed at 300dpi on a cheap OPD printer with low
toner, anything marginal on screen becomes unreadable — so the print palette is deliberately
darker than a straight conversion would give.
"""

from __future__ import annotations

from reportlab.lib.colors import Color, HexColor

# ── ink ──────────────────────────────────────────────────────────────────────
#: Near-black, not pure black. Pure black on white is harsh at body size and produces heavy
#: toner bleed on cheap paper; this is the same optical decision the screen theme makes in
#: the other direction.
INK = HexColor("#14161c")
INK_MUTED = HexColor("#4a4f5e")
INK_FAINT = HexColor("#6b7183")

# ── surfaces ─────────────────────────────────────────────────────────────────
PAPER = HexColor("#ffffff")
#: Section fills. Barely tinted — enough to group, not enough to cost toner or to grey the
#: text sitting on it.
TINT = HexColor("#f6f7fb")
RULE = HexColor("#d6d9e3")
RULE_STRONG = HexColor("#9aa0b2")

# ── the product's hues, re-derived as ink ────────────────────────────────────
#: Periwinkle. Screen `--mk-accent` is a light lavender that vanishes on white; this is the
#: same hue taken down until it reads as a printed accent.
ACCENT = HexColor("#4b4fc4")
ACCENT_TINT = HexColor("#ecedfb")
#: Violet — evidence, exactly as on screen.
EVIDENCE = HexColor("#6b3fa0")
EVIDENCE_TINT = HexColor("#f2ecfa")
#: Amber — caution. Darkened hard: mid-amber on white fails contrast badly.
WARN = HexColor("#8a5a00")
WARN_TINT = HexColor("#fdf3e0")
#: Rose — critical.
DANGER = HexColor("#a3123c")
DANGER_TINT = HexColor("#fdecf1")

#: The demo stripe, matching the on-screen badge's violet.
DEMO = EVIDENCE
DEMO_TINT = EVIDENCE_TINT

# ── type ─────────────────────────────────────────────────────────────────────
FONT = "Inter"
FONT_SEMIBOLD = "Inter-SemiBold"
FONT_BOLD = "Inter-Bold"
FONT_ITALIC = "Inter-Italic"

#: Points. A clinical document is read under bad light by tired people; the body size is a
#: full point larger than a typical report's 9pt for that reason.
SIZE_BODY = 10
SIZE_SMALL = 8.5
SIZE_TINY = 7.5
SIZE_H1 = 20
SIZE_H2 = 12.5
SIZE_H3 = 9.5

LEADING_BODY = 13.5


def flag_colours(flag: str) -> tuple[Color, Color]:
    """Ink and fill for a range flag. A comparison, never an interpretation."""
    return {
        "high": (WARN, WARN_TINT),
        "low": (WARN, WARN_TINT),
        "critical": (DANGER, DANGER_TINT),
    }.get(flag, (INK_MUTED, TINT))

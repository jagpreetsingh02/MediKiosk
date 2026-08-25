"""Every text colour the product uses must actually pass WCAG AA. Measured, not assumed.

The hero is a landing page: white on a lit lavender video is a legitimate treatment there,
and it is emphatically not one for a clinician reading their fortieth history of the morning.
The palette in `frontend/src/design/theme.css` is sampled from that hero, so the risk is
specific and worth pinning: a colour that looked right in the sample is washed out as ink.

This parses the real token file — it does not keep a second copy of the palette that could
drift from it — resolves each `var()` chain, composites the translucent fills over the ground
they actually sit on, and computes the WCAG 2.1 contrast ratio. A token that fails fails the
build.

The thresholds are the standard ones: 4.5:1 for body text, 3:1 for large text (>=24px, or
>=18.66px bold) and for the non-text boundaries that carry meaning.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

THEME = Path(__file__).resolve().parents[1] / "frontend" / "src" / "design" / "theme.css"

AA_BODY = 4.5
AA_LARGE = 3.0

# ---------------------------------------------------------------- parsing


def _declarations() -> dict[str, str]:
    """Every `--mk-*: value;` in theme.css, last definition winning.

    Later blocks override earlier ones, which is what CSS does and what the clinical
    density block at the foot of the file relies on.
    """
    text = THEME.read_text()
    # Strip comments first so a hex inside prose is never read as a value.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    found: dict[str, str] = {}
    for name, value in re.findall(r"(--mk-[a-z0-9-]+)\s*:\s*([^;]+);", text):
        found[name] = value.strip()
    return found


TOKENS = _declarations()


def _resolve(value: str, depth: int = 0) -> str:
    """Follow `var(--x)` chains down to a literal."""
    if depth > 12:
        raise AssertionError(f"var() cycle resolving {value!r}")
    match = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", value.strip())
    if not match:
        return value.strip()
    target = match.group(1)
    assert target in TOKENS, f"{target} is referenced but never defined in theme.css"
    return _resolve(TOKENS[target], depth + 1)


def _rgba(value: str) -> tuple[float, float, float, float]:
    """Parse `#rgb`, `#rrggbb` or `rgba(r, g, b, a)` into 0-255 channels plus alpha."""
    literal = _resolve(value)
    if literal.startswith("#"):
        h = literal[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    m = re.fullmatch(r"rgba?\(([^)]+)\)", literal)
    assert m, f"cannot parse colour {literal!r}"
    parts = [p.strip() for p in m.group(1).replace("/", ",").split(",")]
    r, g, b = (float(parts[i]) for i in range(3))
    a = float(parts[3]) if len(parts) > 3 else 1.0
    return (r, g, b, a)


def _flatten(*layers: str) -> tuple[float, float, float]:
    """Composite a stack of colours, BOTTOM FIRST, into the opaque colour a viewer sees.

    This is the step that makes the numbers real. `--mk-accent-soft` is an 18%-alpha
    periwinkle; asking for its contrast without compositing it over the ground it sits on
    measures a colour nobody ever sees. Likewise a pane fill of 5% white is not a colour —
    it is a modification of whatever is behind it.

    The bottom layer must be opaque, because a stack that never reaches an opaque colour has
    no defined appearance and any ratio computed from it would be fiction.
    """
    assert layers, "nothing to composite"
    br, bg, bb, ba = _rgba(layers[0])
    assert ba == 1.0, f"the bottom layer {layers[0]} must be opaque"
    r, g, b = br, bg, bb
    for layer in layers[1:]:
        lr, lg, lb, la = _rgba(layer)
        r = lr * la + r * (1 - la)
        g = lg * la + g * (1 - la)
        b = lb * la + b * (1 - la)
    return (r, g, b)


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    a, b = _luminance(fg), _luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


#: The ground clinical text actually sits on. The veiled ambient is heaviest exactly where
#: the content column is, so the near-black void alone is the honest backdrop: measuring
#: against the brighter video would flatter every ratio here.
GROUND = "var(--mk-void)"
#: The raised pane most clinical text lives on, bottom-first: ground, then the 5% fill that
#: `[data-surface="clinical"]` uses for a raised card.
PANE = (GROUND, "rgba(255, 255, 255, 0.05)")


# ---------------------------------------------------------------- the tests


@pytest.mark.parametrize(
    "token,threshold,note",
    [
        ("--mk-ink", AA_BODY, "body copy"),
        ("--mk-ink-strong", AA_BODY, "headings"),
        ("--mk-ink-muted", AA_BODY, "supporting prose"),
        ("--mk-accent-ink", AA_BODY, "accent text and links"),
        ("--mk-danger-ink", AA_BODY, "red-flag text"),
        ("--mk-warm-ink", AA_BODY, "caution text"),
        ("--mk-evidence-ink", AA_BODY, "provenance text"),
    ],
)
def test_text_tokens_pass_aa_on_a_pane(token: str, threshold: float, note: str) -> None:
    """Every colour used for reading clinical content, over the pane it sits on."""
    ratio = contrast(_flatten(*PANE, f"var({token})"), _flatten(*PANE))
    assert ratio >= threshold, (
        f"{token} ({note}) is {ratio:.2f}:1 on a raised pane, below AA {threshold}:1. "
        f"Raise the token's lightness in theme.css — do not change its hue."
    )


@pytest.mark.parametrize(
    "token,note",
    [
        ("--mk-ink-subtle", "metadata, never body"),
        ("--mk-accent", "accent fills and glyphs"),
        ("--mk-danger", "red-flag glyphs"),
        ("--mk-warm", "caution glyphs"),
        ("--mk-evidence", "evidence glyphs"),
    ],
)
def test_large_and_non_text_tokens_pass_aa(token: str, note: str) -> None:
    """Large text, icons and meaningful boundaries: the 3:1 threshold."""
    ratio = contrast(_flatten(*PANE, f"var({token})"), _flatten(*PANE))
    assert ratio >= AA_LARGE, f"{token} ({note}) is {ratio:.2f}:1, below AA-large {AA_LARGE}:1"


def test_status_text_passes_on_its_own_tinted_pane() -> None:
    """A red flag's text sits on the red flag's own tint, not on plain glass.

    This is the pairing that actually ships, and the one most likely to fail quietly: the
    tint lifts the background, which *reduces* the contrast of the text on top of it.
    """
    for fg, bg, label in [
        ("--mk-status-ok-fg", "--mk-status-ok-bg", "ok"),
        ("--mk-status-warn-fg", "--mk-status-warn-bg", "caution"),
        ("--mk-status-alert-fg", "--mk-status-alert-bg", "critical"),
        ("--mk-status-info-fg", "--mk-status-info-bg", "evidence"),
    ]:
        backdrop = _flatten(GROUND, f"var({bg})")
        text = _flatten(GROUND, f"var({bg})", f"var({fg})")
        ratio = contrast(text, backdrop)
        assert ratio >= AA_BODY, f"{label}: {fg} on {bg} is {ratio:.2f}:1, below {AA_BODY}:1"


def test_semantic_hues_are_distinguishable_from_each_other() -> None:
    """Accent, caution, critical and evidence must not be confusable.

    They carry different clinical meanings — a physician distinguishes "traced" from
    "unverified" from "red flag" by colour before reading a word. Four hues sampled from one
    video could easily land too close together; this asserts they did not.
    """
    import colorsys

    hues: dict[str, float] = {}
    for name in ("--mk-accent", "--mk-warm", "--mk-danger", "--mk-evidence"):
        r, g, b, _ = _rgba(f"var({name})")
        h, _s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        hues[name] = h * 360

    names = list(hues)
    for i, a in enumerate(names):
        for b_name in names[i + 1 :]:
            gap = abs(hues[a] - hues[b_name])
            gap = min(gap, 360 - gap)
            assert gap >= 40, (
                f"{a} ({hues[a]:.0f}°) and {b_name} ({hues[b_name]:.0f}°) are only "
                f"{gap:.0f}° apart — too close to tell apart at a glance"
            )


def test_no_green_remains_in_the_palette() -> None:
    """Green was the old accent and is gone. This keeps it gone.

    Every literal in the file is checked rather than a hand-written list of token names, so
    a green reintroduced under any name is caught.
    """
    import colorsys

    offenders = []
    for name, raw in TOKENS.items():
        for literal in re.findall(r"#[0-9a-fA-F]{6}\b|rgba?\([^)]*\)", raw):
            try:
                r, g, b, a = _rgba(literal)
            except AssertionError:
                continue
            if a < 0.05:
                continue
            h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            # 80°–170° is green through teal. Only flag when it is actually a hue
            # rather than a near-grey where the maths is meaningless.
            if s > 0.15 and 80 <= h * 360 <= 170:
                offenders.append(f"{name}: {literal} (hue {h * 360:.0f}°)")
    assert not offenders, "green/teal is back in the palette:\n  " + "\n  ".join(offenders)

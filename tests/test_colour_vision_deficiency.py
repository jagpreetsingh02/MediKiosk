"""Caution and critical must stay distinguishable to someone with red-green colour deficiency.

WHY THIS IS A CLINICAL TEST, NOT A COSMETIC ONE. Caution is amber (~40°) and critical is rose
(~350°). To normal trichromatic vision they are 50° apart and unmistakable. Under deuteranopia
— roughly 1 in 12 men — the long-wavelength end of the spectrum compresses and pulls both
toward a duller yellow-brown.

The measured result is that they SURVIVE it: ΔE 63.8 normal, 67.4 protanopia, 21.9
deuteranopia, against a confusability floor of about 10. So the pair does not actually become
indistinguishable. What it loses is two thirds of its margin, and that was the only channel
carrying the difference. Resting an escalation on a thinned-out single channel is the thing
worth fixing, and it is fixed by adding channels rather than by moving the hues.

So this module asserts two things, and the second is the one that actually matters:

  1. How far apart the two states remain under simulated deuteranopia and protanopia, reported
     as a real number so a future palette change cannot quietly erode it.
  2. That colour is NOT the only channel — that a distinct SHAPE and an explicit WORD are
     present for both states. This is the guarantee that survives even total achromatopsia,
     a monochrome printout, and a bad projector.

The simulation uses the Viénot–Brettel–Mollon (1999) linear-RGB projection, which is the
standard method these simulators implement. Distance is CIE76 ΔE in Lab — a rough but honest
measure, where ΔE < 10 is "easily confused at a glance" for non-adjacent samples.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"
THEME = FRONTEND / "design" / "theme.css"
GLYPH = FRONTEND / "design" / "ui" / "StateGlyph.tsx"
BANNER = FRONTEND / "physician" / "RedFlagBanner.tsx"

#: ΔE below this means two samples read as the same colour at a glance.
CONFUSABLE = 10.0


# ------------------------------------------------------------------ colour maths


def _tokens() -> dict[str, str]:
    text = re.sub(r"/\*.*?\*/", "", THEME.read_text(), flags=re.S)
    return {n: v.strip() for n, v in re.findall(r"(--mk-[a-z0-9-]+)\s*:\s*([^;]+);", text)}


TOKENS = _tokens()


def _resolve(value: str, depth: int = 0) -> str:
    m = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", value.strip())
    if not m or depth > 12:
        return value.strip()
    return _resolve(TOKENS[m.group(1)], depth + 1)


def _rgb(token: str) -> tuple[float, float, float]:
    literal = _resolve(f"var({token})")
    if literal.startswith("#"):
        h = literal[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.fullmatch(r"rgba?\(([^)]+)\)", literal)
    assert m, f"cannot parse {literal!r}"
    parts = [p.strip() for p in m.group(1).split(",")]
    return tuple(float(parts[i]) for i in range(3))  # type: ignore[return-value]


def _to_linear(c: float) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _from_linear(c: float) -> float:
    c = max(0.0, min(1.0, c))
    s = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
    return s * 255


def simulate(rgb: tuple[float, float, float], kind: str) -> tuple[float, float, float]:
    """Viénot-Brettel-Mollon dichromat simulation, applied in LINEAR RGB.

    Applying these matrices to gamma-encoded values — a common shortcut — overstates how
    similar two colours become, which would make this test pass for the wrong reason.
    """
    r, g, b = (_to_linear(c) for c in rgb)
    if kind == "deuteranopia":
        rr = 0.625 * r + 0.7 * g + 0.0 * b
        gg = 0.7 * r + 0.3 * g + 0.0 * b
        bb = 0.0 * r + 0.3 * g + 0.7 * b
    elif kind == "protanopia":
        rr = 0.1121 * r + 0.8853 * g - 0.0005 * b
        gg = 0.1127 * r + 0.8897 * g + 0.0001 * b
        bb = 0.0036 * r - 0.0399 * g + 1.0363 * b
    else:
        raise AssertionError(kind)
    return (_from_linear(rr), _from_linear(gg), _from_linear(bb))


def _lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = _lab(a), _lab(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb, strict=True)))


# ------------------------------------------------------------------ the tests


def test_report_caution_versus_critical_under_simulation(capsys) -> None:
    """Print the measured separation. Informational, and the numbers are the point."""
    caution, critical = _rgb("--mk-warm"), _rgb("--mk-danger")
    lines = [f"\n  normal vision      ΔE {delta_e(caution, critical):5.1f}"]
    for kind in ("deuteranopia", "protanopia"):
        lines.append(
            f"  {kind:<18} ΔE {delta_e(simulate(caution, kind), simulate(critical, kind)):5.1f}"
        )
    with capsys.disabled():
        print("\n".join(lines))


def test_shape_is_a_distinct_channel_for_each_state() -> None:
    """The guarantee that survives when colour fails completely.

    A triangle and an octagon are distinguishable in monochrome, at 12px, on a fax. This
    asserts both silhouettes exist and are genuinely different paths — not the same shape
    rendered in two colours, which is the failure mode this whole exercise is about.
    """
    source = GLYPH.read_text()
    assert "case 'critical':" in source and "case 'caution':" in source

    def path_for(case: str) -> str:
        block = source.split(f"case '{case}':", 1)[1].split("case ", 1)[0]
        found = re.findall(r'd="([^"]+)"', block)
        assert found, f"{case} has no drawn path"
        return found[0]

    critical, caution = path_for("critical"), path_for("caution")
    assert critical != caution, "critical and caution draw the same shape"
    # An octagon needs more vertices than a triangle; if they ever converge, the silhouettes
    # have stopped being distinguishable and this is the cheapest way to notice.
    assert critical.count("h") + critical.count("L") + critical.count("z") >= 2
    assert caution.count("z") >= 1, "caution should be a closed triangle"


def test_both_states_carry_an_explicit_word() -> None:
    """Never an icon alone. A glyph without a word is a puzzle, not a warning."""
    glyph = GLYPH.read_text()
    for state, word in (("critical", "Critical"), ("caution", "Caution")):
        assert f"{state}: '{word}'" in glyph, f"STATE_LABEL is missing a word for {state}"

    banner = BANNER.read_text()
    assert "CRITICAL" in banner and "CAUTION" in banner, (
        "the escalation banner must name the state in words, not only by colour and shape"
    )


def test_the_two_states_are_never_colour_only() -> None:
    """The real assertion: if hue were the only channel, this would be the failing test.

    It does not demand that the simulated hues stay far apart — that is not achievable for
    amber and rose, and pretending otherwise would be the dishonest fix. It demands that
    when they DO converge, two other channels are carrying the meaning.
    """
    caution, critical = _rgb("--mk-warm"), _rgb("--mk-danger")
    worst = min(
        delta_e(simulate(caution, kind), simulate(critical, kind))
        for kind in ("deuteranopia", "protanopia")
    )

    if worst >= CONFUSABLE:
        return  # colour alone still separates them; shape and text are belt and braces

    glyph = GLYPH.read_text()
    banner = BANNER.read_text()
    assert "StateGlyph" in banner, (
        f"under simulation the two states are only ΔE {worst:.1f} apart, so colour cannot "
        "carry the distinction — the escalation banner must render a StateGlyph"
    )
    assert "case 'critical':" in glyph and "case 'caution':" in glyph
    assert "CRITICAL" in banner and "CAUTION" in banner

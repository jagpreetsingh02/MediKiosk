#!/usr/bin/env python3
"""Fail the build if a raw colour value appears outside the token file.

WHY THIS EXISTS. A design system stops being a system the moment someone writes `#1a7f4b` at a
call site. It does not break anything that day — it breaks the *next* re-theme, when that one
value stays green while everything around it moves. This project has already paid that cost
once: the physician stylesheet accumulated sixty-nine literals tuned for a white surface, and
when the ground went dark they produced a light amber panel with dark-mode ink written on it —
a contrast failure on the one component whose whole job is to warn a clinician.

So: every hex, `rgb()`, `rgba()`, `hsl()` and Tailwind colour literal belongs in
`frontend/src/design/theme.css` and nowhere else.

THREE EXEMPTIONS, all narrow and all justified:

  * `frontend/src/hero/` — a verbatim port of the design in `ui/`. Its values are the SOURCE
    of the tokens, not a divergence from them, and rewriting them as tokens would destroy the
    thing that makes it a faithful port. It is exempt, and it is the reason the exemption list
    is a list of paths rather than a flag anyone can set.
  * `ui/` itself — not part of the application build at all.
  * `frontend/src/components/ui/` — shadcn's own vendoring convention: components dropped here
    are copy-pasted from an external source and owned/upgraded as a unit, not hand-edited to
    match this app's palette. They bring their own colour system (shadcn's CSS variables, see
    `components/ui/shadcn-tokens.css`) rather than drifting from this one. A component in this
    folder that embeds a colour literal INSIDE an isolated, sandboxed document it builds at
    runtime (an iframe `srcDoc`, for instance) is a different case again — that literal never
    reaches this app's own stylesheet or DOM at all — but the folder-level exemption covers
    both without needing to tell them apart.

Run directly, or via `make lint`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"

#: The one file allowed to hold the palette.
TOKEN_FILE = FRONTEND / "design" / "theme.css"

#: Paths whose colour literals are the source of the tokens rather than a drift from them.
EXEMPT_DIRS = (FRONTEND / "hero", FRONTEND / "components" / "ui")

SCANNED_SUFFIXES = {".css", ".ts", ".tsx", ".js", ".jsx"}

#: Hex (#abc / #aabbcc / #aabbccdd), functional colours, and Tailwind colour literals such as
#: `bg-emerald-500`, `text-slate-100/70`, `border-white/20`.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("hex", re.compile(r"#[0-9a-fA-F]{3,8}\b")),
    ("rgb", re.compile(r"\brgba?\s*\(")),
    ("hsl", re.compile(r"\bhsla?\s*\(")),
    (
        "tailwind",
        re.compile(
            r"\b(?:bg|text|border|from|via|to|ring|fill|stroke|shadow|decoration|outline|"
            r"divide|accent|caret|placeholder)-"
            r"(?:slate|gray|grey|zinc|neutral|stone|red|orange|amber|yellow|lime|green|"
            r"emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b"
        ),
    ),
]

#: `linear-gradient(#fff 0 0)` is the mask-composite idiom, not a colour choice — the value is
#: structural (any opaque colour works) and replacing it with a token would obscure that.
ALLOWED_SUBSTRINGS = ("linear-gradient(#fff 0 0)",)


def _is_exempt(path: Path) -> bool:
    if path == TOKEN_FILE:
        return True
    return any(exempt in path.parents for exempt in EXEMPT_DIRS)


def _strip_comments(text: str, suffix: str) -> str:
    """Blank out comments, preserving line numbers so reported lines stay accurate.

    A hex quoted in prose ("jade was #14a67e") is documentation, not a value, and flagging it
    would push people to stop writing the documentation.
    """

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    if suffix != ".css":
        text = re.sub(r"//[^\n]*", blank, text)
    return text


def violations() -> list[tuple[Path, int, str, str]]:
    found: list[tuple[Path, int, str, str]] = []
    for path in sorted(FRONTEND.rglob("*")):
        if path.suffix not in SCANNED_SUFFIXES or not path.is_file() or _is_exempt(path):
            continue
        source = _strip_comments(path.read_text(encoding="utf-8"), path.suffix)
        for lineno, line in enumerate(source.splitlines(), 1):
            for allowed in ALLOWED_SUBSTRINGS:
                line = line.replace(allowed, "")
            for kind, pattern in PATTERNS:
                match = pattern.search(line)
                if match:
                    found.append((path, lineno, kind, line.strip()[:96]))
                    break
    return found


def main() -> int:
    found = violations()
    if not found:
        scanned = sum(
            1
            for p in FRONTEND.rglob("*")
            if p.suffix in SCANNED_SUFFIXES and p.is_file() and not _is_exempt(p)
        )
        print(f"  ok  no raw colour values outside theme.css — {scanned} files scanned")
        return 0

    print(f"  FAIL  {len(found)} raw colour value(s) outside theme.css\n")
    for path, lineno, kind, text in found:
        print(f"    {path.relative_to(ROOT)}:{lineno}  [{kind}]  {text}")
    print(
        "\n  Colours belong in frontend/src/design/theme.css as semantic tokens.\n"
        "  Add a token there (--mk-surface, --mk-ink-muted, --mk-accent, --mk-state-…)\n"
        "  and reference it with var(). See that file's header for why."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

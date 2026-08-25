#!/usr/bin/env python3
"""Derive the PDF's fonts from the exact files the web build serves.

WHY NOT JUST USE HELVETICA. ReportLab ships the base-14 fonts and they need no embedding, so
a PDF in Helvetica is one dependency lighter. But the brief on screen is set in Inter, and a
printed report in a different face is a different document — the requirement is the same
typeface, and "close enough" is how a report stops looking like it came from the product.

WHY A SCRIPT RATHER THAN COMMITTED BINARIES ALONE. The TTFs ARE committed (see data/fonts/),
because a build should not depend on node_modules being installed. This script is how they
are regenerated, so nobody has to guess where a 66KB binary in the repo came from.

    python scripts/make_pdf_fonts.py

TWO CONVERSIONS HAPPEN HERE, and both matter:

  woff2 -> ttf        ReportLab cannot read woff2 at all.
  variable -> static  @fontsource ships Inter as a VARIABLE font. ReportLab has no support
                      for the `wght` axis, and embedding the variable file directly gives
                      one arbitrary weight for everything. Each weight is instantiated as
                      its own static face instead.
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ROOT / "frontend" / "node_modules" / "@fontsource-variable" / "inter" / "files"
)
SRC = FILES / "inter-latin-wght-normal.woff2"
#: A REAL italic face, not a synthesised slant. `<i>` appears in every empty-section line,
#: and ReportLab cannot fake one — without this the family registration has no italic to
#: point at and the whole document fails to build.
SRC_ITALIC = FILES / "inter-latin-wght-italic.woff2"
OUT = ROOT / "data" / "fonts"

#: The three weights the print stylesheet uses. Body, headings, and the wordmark.
WEIGHTS = ((400, "Regular"), (600, "SemiBold"), (700, "Bold"))


def main() -> int:
    if not SRC.exists():
        print(f"source font missing: {SRC}")
        print("run `npm install` in frontend/ first")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    if SRC_ITALIC.exists():
        italic = instancer.instantiateVariableFont(TTFont(SRC_ITALIC), {"wght": 400})
        italic.flavor = None
        dest = OUT / "Inter-Italic.ttf"
        italic.save(dest)
        print(f"  {dest.relative_to(ROOT)}  {dest.stat().st_size:>7} bytes")
    for weight, label in WEIGHTS:
        font = TTFont(SRC)
        static = instancer.instantiateVariableFont(font, {"wght": weight})
        static.flavor = None  # drop the woff2 compression
        dest = OUT / f"Inter-{label}.ttf"
        static.save(dest)
        print(f"  {dest.relative_to(ROOT)}  {dest.stat().st_size:>7} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

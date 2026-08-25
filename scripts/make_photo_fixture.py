"""Synthesise a handheld phone photo of a printed document — the OCR test fixtures.

    python scripts/make_photo_fixture.py <flat.png> <out.jpg> [severity=1.0]

Builds `data/fixtures/documents/prescription_photo_handheld.jpg`, which reliably reproduces the
5-to-S substitution the verification lane exists to catch. See that fixture's README.

THIS IS A SIMULATION, NOT A PHOTOGRAPH, and that is stated wherever its numbers are quoted. It
reproduces the degradations a real handheld shot carries — and only those:

    perspective   the page photographed off-axis, so it is a trapezium not a rectangle
    shadow        a soft gradient across part of the page: one overhead light, with the
                  phone between it and the paper
    vignette      the falloff a lens gives toward the corners
    noise         sensor noise at indoor ISO
    blur          slight defocus from a hand-held shot
    JPEG          compression artefacts at a phone's default quality

What it cannot reproduce is a real sensor, a real lens and real paper. Numbers measured against
it are indicative, not a substitute for photographing an actual printed page.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

src = Path(sys.argv[1])
out = Path(sys.argv[2])
severity = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

page = Image.open(src).convert("L")
# Put the page on a larger dark "desk" so perspective has somewhere to move into.
W, H = int(page.width * 1.25), int(page.height * 1.25)
canvas = Image.new("L", (W, H), color=90)
canvas.paste(page, ((W - page.width) // 2, (H - page.height) // 2))

# --- perspective: photographed from above-left, tilted ------------------------
k = 0.06 * severity
coeffs_src = [(0, 0), (W, 0), (W, H), (0, H)]
dst = [(W * k, H * k * 0.5), (W * (1 - k * 0.3), 0), (W, H * (1 - k * 0.4)), (W * k * 0.4, H)]
def _find_coeffs(pa, pb):
    m: list[list[float]] = []
    for p1, p2 in zip(pa, pb, strict=True):
        m.append([p2[0], p2[1], 1, 0, 0, 0, -p1[0]*p2[0], -p1[0]*p2[1]])
        m.append([0, 0, 0, p2[0], p2[1], 1, -p1[1]*p2[0], -p1[1]*p2[1]])
    # Least-squares solve for the 8 perspective coefficients PIL wants.
    a = np.asarray(m, dtype=float)
    b = np.asarray(pa, dtype=float).reshape(8)
    return np.linalg.solve(a.T @ a, a.T @ b)
canvas = canvas.transform((W, H), Image.PERSPECTIVE,
                          _find_coeffs(dst, coeffs_src), Image.BICUBIC, fillcolor=90)

arr = np.asarray(canvas, dtype=np.float32)

# --- shadow: a soft diagonal band across part of the page ---------------------
yy, xx = np.mgrid[0:H, 0:W]
band = (xx / W) * 0.9 + (yy / H) * 0.5
shadow = 1.0 - (0.55 * severity) * np.clip((band - 0.55) / 0.45, 0, 1) ** 1.3
# --- vignette -----------------------------------------------------------------
cy, cx = H / 2, W / 2
r = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2)
vignette = 1.0 - (0.28 * severity) * np.clip(r - 0.35, 0, 1.4) ** 1.6
arr = arr * shadow * vignette

# --- sensor noise -------------------------------------------------------------
rng = np.random.default_rng(11)
arr = arr + rng.normal(0, 7.0 * severity, arr.shape)
img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")
# --- slight handheld defocus ---------------------------------------------------
img = img.filter(ImageFilter.GaussianBlur(radius=0.7 * severity))
# --- phone resolution and JPEG -------------------------------------------------
img = img.convert("RGB").resize((3024, int(3024 * H / W)), Image.LANCZOS)
img.save(out, format="JPEG", quality=78)
print(f"  wrote {out.name}  {img.width}x{img.height}  severity={severity}")

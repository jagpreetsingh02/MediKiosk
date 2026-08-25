# `prescription_photo_handheld.jpg` — the 5-to-S fixture

A simulated handheld photograph of `prescription_scan.png`: off-axis perspective, a shadow
gradient, lens vignette, sensor noise, handheld defocus, 3024px, JPEG q78. Built by
`scripts/make_photo_fixture.py`.

## Why it is kept

It reliably reproduces a **5 → S substitution**:

```
on the paper   TAB. AMLODIPINE 5MG OD x 30 days
OCR reads      AMLODIPINE SMG          confidence 0.94
```

That number matters. **0.94 is high confidence.** The engine is not hedging — it is confident
and wrong, which is the failure mode a confidence threshold cannot catch and the exact reason
the verification lane exists. A patient shown "AMLODIPINE SMG" alone might well confirm it;
shown the crop of their own line beside it, the mismatch is obvious and Correct is one tap.

Amlodipine 5mg and 10mg are both ordinary doses, so a misread digit here is not a typo — it is
a different prescription.

## Do not "fix" it

The temptation on seeing this fixture fail is to tune the thresholding until it reads 5MG. That
would be tuning to one image. The point is not that this photograph is hard; it is that OCR
returns confident errors on ordinary input, and the product's answer to that is a human
checking it against the source — not a better score.

If a preprocessing change makes this read correctly, good — but keep the fixture, because the
next photograph will do the same thing somewhere else.

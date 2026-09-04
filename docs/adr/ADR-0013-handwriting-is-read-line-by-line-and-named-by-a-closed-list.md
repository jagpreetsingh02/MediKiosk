# ADR-0013 — Handwriting is read line by line, and a medicine is named only from a closed list

**Context.** MediKiosk could read a *printed* prescription well and a *handwritten* one not at
all. Tesseract on the handwritten fixture returns "Tab Augmtin 625 ep x 59" at 0.32 confidence
and "PCM 526 sos" at 0.80 — and the second is the dangerous one, because 526 is a misread of
500 that arrives looking clean. The brief asks for the handwriting model
`khedim/Medical-Prescription-OCR`, with Tesseract as the fallback, and for the output to be an
*understandable* prescription rather than a transcription.

That opens three ways to be confidently wrong, and each needed a decision.

---

### 1. The model never sees a page

`khedim/Medical-Prescription-OCR` is a TrOCR encoder-decoder fine-tuned on crops of **single**
handwritten prescription lines. Its decoder is a language model with a bounded output and no
concept of a newline. Given a whole prescription it does not error — it emits one fluent,
plausible line and drops the rest, and at the API boundary that is indistinguishable from
success.

**Decision.** Validate → deskew → denoise → contrast → segment into lines → one inference per
crop → reassemble in reading order. The model is only ever asked the question it was trained
on. Segmentation is a **projection profile**, not a learned detector: a row of a page either
carries ink or it does not, which is a measurement — reproducible, millisecond-fast on a
kiosk with no GPU, and wrong in visible ways rather than confident ones.

**And a page read only in part is not used at all.** Measured with the base TrOCR checkpoint
on `prescription_scan.png`: 11 lines segmented, 3 returned, each individually confident. That
result is a prescription missing two of its four drugs, with no gap anywhere to show it. Below
`trocr_min_line_yield` the page goes to Tesseract **whole**. A worse reading of the entire
prescription beats a good reading of a quarter of it.

### 2. A medicine name comes from a closed list or from nowhere

"Augmtin" is obviously Augmentin to a pharmacist. It is *also* obviously something to a
language model asked what drug it resembles — and the model answers with identical fluency
whether the input was "Augmtin", "Augmntn" or a smudge. A wrong medicine name that reads
confidently is worse than none, because none is visibly a gap.

**Decision.** Constrained matching against `data/terminology/medications.json`. The output can
only ever be a string already in that file. A correction is applied automatically only when
it is strong **and** unambiguous **and** the OCR was confident in the characters **and** the
first two letters anchor — four conditions, because each alone has a failure mode the others
catch. Anything less is returned as a *suggestion with the name left null*: "possibly
Augmentin — 88% match" is useful to a pharmacist; "Augmentin" would be a claim.

A token OCR marked illegible is never auto-corrected however well it scores. A confident match
on characters nobody read is a confident match on a guess.

**The threshold is measured.** An adversarial sweep mutates every generic and brand in the
dictionary and asserts none auto-corrects to a *different* medicine:

| corruption | mutations | auto-corrected | wrong medicine |
|---|---:|---:|---:|
| one character deleted | 2491 | 74% | **0** |
| one character substituted | 1175 | 39% | **0** |
| two characters transposed | 1198 | 38% | **0** |
| two characters substituted | 1211 | 7% | **0** |
| two characters deleted | 1076 | 29% | **1** |

The one failure is real and is recorded rather than hidden: `Ciploric` losing two characters
becomes `Ciplo`, which is a closer match to the genuinely different brand `Ciplox`. Two
simultaneous character losses in a six-letter brand is severe corruption, and the mitigation
is not a higher threshold — it is that the original transcription stays on screen beside the
interpretation, where a pharmacist sees "Ciplo → Ciplox" and stops.

### 3. Dosing shorthand is a table, and a dose is never corrected

**Decision.** BD, OD, TDS, SOS, HS, AC, PC and the `1-0-1` grid resolve by **exact lookup**
against `data/terminology/prescription-abbreviations.yaml`. No similarity scoring anywhere in
that path. These are definitions, not judgements: BD has meant twice daily on every
prescription written in India for as long as prescriptions have been written in India, and a
model resolving it would be slower, non-reproducible, unavailable offline, and occasionally
wrong — which applied to a frequency means a rescue medicine taken four times a day.

Two entries in that file are separations that look pedantic and are not. `SOS` is **not** a
frequency: "when you need it" has no times-per-day. And frequency is **not** timing: "BD bf"
is twice daily *and* before food, and one field loses one of them.

A **dose is never corrected, only questioned**. Where a resolved medicine's strength is not
one it is dispensed in, the line is flagged for a human — never rewritten. 526 might be a
compounded preparation, a strength this formulary is missing, or simply what the doctor wrote.
This check is what catches the "PCM 526 sos" class of error, which nothing else in the
pipeline sees: the name resolves, the confidence is respectable, and the record would have
said Paracetamol 526.

---

**The output shape.** `raw_ocr_text`, `interpreted_text` and `medications` travel together on
every route that carries any of them, and every field carries its raw text, its provenance and
its confidence. OCR confidence and interpretation confidence are reported **separately**
because they are independent: a crisp photograph of an unknown drug is high on the first and
zero on the second. A client rendering the interpretation alone has removed the only check
anyone has on it, which is why the API does not offer that as an option.

**Alternatives considered.** Pass the whole image to the model (fails silently — see §1). Ask
an LLM to correct the drug name (unbounded output; the failure is fluent). Use edit distance
with no margin test (`Amlo` auto-corrects at 0.86 while three other drugs sit within 0.01).
Merge the two engines' text where they disagree (produces a sentence no engine read and no
human wrote). Correct an implausible dose to the nearest known strength (the one edit this
system must never make).

**Status.** Accepted. Not yet verified against the fine-tuned weights:
`khedim/Medical-Prescription-OCR` is a **gated** Hugging Face repo and 401s without an
authorised token, so the pipeline around it has been proven against
`microsoft/trocr-base-handwritten` and the fine-tune has not been run. `docs/EVALUATION.md`
says so beside every number. Set `HF_TOKEN` in `.env` and install
`requirements-handwriting.txt` to run it for real; `/about` reports `tokenConfigured` so a
demo audience can see which of the two is happening.

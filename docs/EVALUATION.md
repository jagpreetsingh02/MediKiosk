# Evaluation

*Numbers below were produced by `python -m eval.runner --both` on 2026-08-23, commit at the
time of writing. Reproduce with one command; nothing here is hand-copied.*

---

## Why this document exists

Almost no competing team will report measured numbers. The ones that do will report them on
the data they tuned against. This document reports both, and reports the gap.

---

## The metrics, and the current numbers

| Metric | Target | Development (n=50) | **Held-out (n=12)** |
|---|---|---|---|
| Hallucination rate — facts with no valid source span | **0**, hard-enforced | **0.0000** | **0.0000** |
| Unsourced claims in generated summaries | **0**, hard-enforced | **0** | **0** |
| Red-flag sensitivity on emergency scripts | **≥ 0.98** | **1.0000** | **1.0000** |
| Emergency scripts with every expected flag caught | 1.00 | **1.0000** | **1.0000** |
| Priority under-calls (escalated less than gold) | 0 | **0** | **0** |
| Forbidden flags fired (over-triggering) | 0 | **0** | **0** |
| Extraction accuracy vs gold slots | tracked | 1.0000 | **0.9048** |
| History completeness (mean) | tracked, trending up | 0.9928 | **0.9695** |
| Time to physician-ready summary (median) | tracked | 1 ms | 1 ms |
| Scripts completing without error | all | 50/50 | 12/12 |

**Read the held-out column.** The development column is the number the system was fixed
against and it is reported only so the gap is visible.

### The gap, and what it means

```
Metric                                           dev    held-out         gap
--------------------------------------------------------------------------
Hallucination rate                            0.0000      0.0000     +0.0000
Red-flag sensitivity                          1.0000      1.0000     +0.0000
Extraction accuracy                           1.0000      0.9048     -0.0952
History completeness                          0.9928      0.9695     -0.0233
Priority accuracy                             1.0000      1.0000     +0.0000
```

The interesting result is the *shape* of that table, not any single figure.

**Extraction accuracy drops 9.5 points on unseen phrasing. The safety metrics do not move at
all.** That is not luck; it is the architecture showing up in the measurements. Extraction is
the part that depends on having seen a turn of phrase before, so it degrades on new phrasing
exactly as you would expect. Hallucination rate and red-flag sensitivity do not depend on the
extractor at all:

- **Hallucination rate is 0 because `record_fact()` refuses an unsourced fact**, not because
  the extractor is good. A worse extractor produces *fewer* facts, never unsourced ones.
- **Red-flag sensitivity is 1.0 because the rules run over whatever was recorded**, and every
  question is answerable by tap. When extraction fails on a spoken answer, the question
  degrades to touch and the tap still reaches the rule engine.

`h12-all-asr-fails` is the script that demonstrates this deliberately: every spoken answer in
it is unintelligible, every one degrades to touch, and the history still completes.

### Where extraction actually failed on held-out data

Two misses, both in `hpi`:

| Path | Utterance | Expected | Got |
|---|---|---|---|
| `hpi.radiation` | "it shoots into my left shoulder and arm" | `left_arm` | nothing |
| `hpi.onset` | "it came on abruptly while I was at rest" | `sudden` | nothing |

Both are missing phrasings, not wrong answers — the extractor recorded nothing rather than
recording something incorrect, which is the failure direction we want. Neither changed the
red flag: `h01` still escalated to `immediate` on the other recorded facts.

**These have deliberately not been fixed.** Adding "shoulder and arm" and "came on abruptly"
to the lexicon would raise held-out extraction to 1.00 and make the held-out set worthless.
They are listed here so the next person can see exactly what the 9.5-point gap consists of.

---

## Methodology

### The gold set

**50 development scripts** in `eval/scripts/`, hand-authored. Composition:

| Class | n | What it exercises |
|---|---|---|
| `emergency` | 17 | Every red-flag family. False negatives here are the only unacceptable error. |
| `plain` | 12 | Routine presentations. Mostly there to catch **over**-triggering. |
| `low_literacy` | 8 | Hinglish and colloquial phrasing: *gutka*, *kala pakhana*, *saans phool*. |
| `rambling` | 5 | The symptom buried in an anecdote; a relative's illness told as their own. |
| `contradictory` | 4 | Patient contradicts themselves; stoic patient under-reports. |
| `mixed` | 4 | Declines, AYUSH mode, ASR failure. |

Languages: 41 English, 9 Hindi/Hinglish. 20 scripts expect `immediate`, 7 `urgent`, 23
`routine`. 46 individual red-flag rule ids are expected across 27 scripts.

**12 held-out scripts** in `eval/holdout/`, written *after* the lexicon was tuned, with a
standing rule recorded in `scripts/make_holdout_scripts.py`: whatever number they produce is
the number published, and no lexicon entry is ever added to improve it.

### How a script is scored

Each script names the exact slot values expected and the exact rule ids that must fire. A
script saying "should detect an emergency" is not scoreable, so none of them say that.
Scripts also name **forbidden** rule ids — rules that must *not* fire — which is what catches
a rule so loose it fires on everybody.

Every script runs through the real state machine, the real extractor and the real rule
engine. There are no mocks in the harness.

### What "hallucination rate" counts

Facts recorded with no usable source span, over all facts recorded. It is 0 by construction —
`record_fact()` raises rather than writing one — so the harness is checking that the choke
point has not been bypassed, which is a different and more useful thing than checking a model.

The second row, **unsourced claims in generated summaries**, is the one that would catch a
regression in practice: it counts summary lines whose text contains a word that no recorded
fact supports. That check is what makes prose smoothing safe to offer.

### Honest caveats

1. **The 50-script set was tuned against.** Three lexicon gaps and two extractor bugs were
   found and fixed by running it (see below). Its 1.0000 extraction figure is therefore an
   upper bound and should not be quoted on its own. This is the reason the held-out set exists.
2. **Scripts are synthetic and written by one person.** They encode one person's model of how
   patients speak. Real OPD recordings would move these numbers, probably downward, and no
   claim here should be read as a clinical validation.
3. **Timing is not end-to-end.** 1 ms median is the *computation* — machine walk, extraction,
   rule evaluation, projection, summary assembly and the traceability check. It excludes the
   human, network, ASR and TTS. The honest end-to-end figure is dominated by how long a
   patient takes to answer ~30 questions, which these scripts do not model.
4. **Extraction ran on the offline rule-based backend.** With `GROQ_API_KEY` set, `--both`
   re-runs against the hosted model and reports the delta. That comparison is the reason the
   offline backend exists; see "Does the LLM help?" below.
5. **The held-out set is small (12).** A 9.5-point gap on 12 scripts has wide error bars.
   It is an indication, not a measurement.

---

## What the evaluation found (bugs it caught, not numbers it reported)

The harness earned its place by failing. Every item below was a real defect found by running
it, not by reading the code:

| Found | Defect | Severity |
|---|---|---|
| First eval run | `Rule.fires()` passed the clause list where the values dict belongs, so **every `any:` red-flag rule silently never fired**. Sensitivity would have been catastrophic in a demo. | Critical |
| First eval run | `allergy.reaction` had no phrase lexicon at all, so an anaphylaxis history narrated in plain words reached the rule engine as nothing. | Critical |
| First eval run | `breathlessness` had no negated-verb phrasings — "could not breathe" matched nothing. | High |
| First eval run | `cough_3wk` matched "teen hafte se khansi" but not "khansi ... teen hafte se". Word order lost a TB screening trigger. | High |
| Second eval run | The extractor read **negated symptoms as present**: "a heavy feeling, like pressure, not sharp" yielded `sharp`. This is the mechanism by which a system invents a symptom nobody reported. | Critical |
| Third eval run | Negation suppression was applied to options that *mean* absence, so "no, I never smoke" recorded nothing instead of `never`. | Medium |
| First eval run | Gold script `s30` expected `RF-PAIN-01` at severity 8, but the rule needs ≥ 9. **The eval caught the script being wrong, not the system.** | — |

The negation bug is the one worth dwelling on. It was invisible to every unit test, it
produced a confident, well-formed, fully-sourced fact, and the fact was wrong in the exact
direction that matters. Provenance does not protect you from it: the span "not sharp" really
does contain the word "sharp". Only a behavioural test over realistic narration finds it.

---

## Does the LLM actually help?

Unresolved, and deliberately measurable rather than assumed.

Everything above ran on the **offline rule-based extractor** (`app/llm/offline.py`), which is
the default so a demo never depends on a network. With `GROQ_API_KEY` set and
`LLM_BACKEND=groq`, the same harness runs against the hosted model and prints the same table.

The prediction worth testing, stated in advance so it cannot be retrofitted: the LLM should
add little or nothing on `plain` and `low_literacy` scripts, where the phrase lexicon already
covers the vocabulary, and should add real recall on `rambling` ones, where the signal is
buried in a paragraph and no phrase list will find it. If that prediction is wrong, the
finding is that the LLM is not needed for extraction, and that is a legitimate and reportable
result — the deterministic path already meets every safety target.

## OCR backend comparison

Separately measured by `python -m eval.ocr_bench` against `data/fixtures/documents/`
(three document types × three quality levels, with ground truth).

| Backend | Digital PDF | Clean scan | Degraded phone photo |
|---|---|---|---|
| `textlayer` | med recall 1.00, conf 0.99 | *fails honestly* — no text layer | *fails honestly* |
| `tesseract` | med recall 1.00, conf 0.86 | med recall 1.00, conf 0.88 | med recall 0.75–1.00, conf 0.61–0.83 |

The number to look at is the **verification-lane rate**: the share of extracted entities
routed to a human. It rises from 0% on a clean PDF to 60% on a degraded lab photo. That rise
is the system working. Tesseract does not get quietly worse as image quality falls — it stays
roughly as accurate and becomes *less confident*, and the low-confidence lane converts that
into human review instead of into a wrong dosage in a patient's record.

`textlayer` refusing images rather than returning zero entities is deliberate: silently
returning nothing from a scan looks identical to "this document was blank".

---

## Reproducing

```bash
python -m eval.runner --both            # development + held-out + the gap
python -m eval.runner --strict          # exits non-zero on any hard-target failure
python -m eval.runner --holdout         # held-out only
python -m eval.runner --only s01        # one script
python -m eval.ocr_bench                # OCR backend comparison
```

`--strict` is wired into the test suite (`tests/test_eval_harness.py`), so a regression in
hallucination rate or red-flag sensitivity fails the build rather than showing up in a table
nobody re-ran.

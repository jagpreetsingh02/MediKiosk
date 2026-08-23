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
| `hpi.onset` | "it happened out of nowhere" | `sudden` | `after_event` |

The first is a missing phrasing: the extractor recorded nothing rather than something wrong,
which is the failure direction we want.

The second is more interesting and worth the diagnosis. `sudden` has "out of nowhere" in its
lexicon and *does* match — but `after_event` matches too, on the word **"happened"**, which
the extractor harvested automatically from that option's own label, *"After something happened
(fall, food, effort)"*. "happened" is a generic verb, it appears earlier in the sentence, and
the positional tiebreak hands it the win. The mechanism at fault is deriving match phrases
from label words without filtering generic ones.

**Neither has been fixed, including the mechanism.** Fixing the label-word filter would raise
held-out extraction and burn the only unbiased number in this document. The correct sequence
is to fix it *and then write new held-out scripts*, not to fix it against these. Recorded here
so the next person inherits the diagnosis rather than rediscovering it.

Neither miss changed a red flag: `h01` still escalated to `immediate` on its other facts.

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
4. **The headline table is the offline rule-based backend.** The hosted-model numbers are
   reported separately under "Does the LLM actually help?" below, on both sets. Reproduce with
   `LLM_BACKEND=groq python -m eval.runner --both`.
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

**Measured, not assumed** — and the answer is more interesting than either "yes" or "no".

Both backends were run over both sets. `openai/gpt-oss-120b` via Groq
(`llama-3.3-70b-versatile`, named in the original brief, has been decommissioned and the API
404s on it).

### Development set (n=50) — the rules win, but the comparison is rigged

| Metric | Offline rules | Groq `gpt-oss-120b` |
|---|---|---|
| Hallucination rate | **0.0000** | **0.0000** |
| Red-flag sensitivity | **1.0000** | 0.9333 |
| Priority under-calls | **0** | 1 |
| Extraction accuracy | **1.0000** | 0.8972 |
| Median time to summary | **1 ms** | 4,510 ms |

This table flatters the rules and should not be quoted on its own: **the lexicon was tuned
against these 50 scripts and the model was not.** That is precisely the bias the held-out set
exists to remove.

### Held-out set (n=12) — the honest comparison, and the LLM wins

| Metric | Offline rules | Groq `gpt-oss-120b` |
|---|---|---|
| Hallucination rate | **0.0000** | **0.0000** |
| Red-flag sensitivity | **1.0000** | **1.0000** |
| Priority under-calls | **0** | **0** |
| Extraction accuracy | 0.9048 | **0.9524** |
| History completeness | 0.9695 | **0.9778** |
| Median time to summary | **1 ms** | 1,843 ms |

**On phrasing neither backend has seen, the model is about 5 points better at extraction and
about 1,800× slower, and the two are indistinguishable on every safety metric.**

### What that actually means

Three conclusions, and the third is the one that matters architecturally.

1. **The LLM buys extraction recall on novel phrasing, and nothing else.** +4.8 points on
   held-out extraction is real and worth having. It bought exactly zero on hallucination rate,
   red-flag sensitivity and priority accuracy, because those are not extractor properties.
2. **The rule extractor generalises better than expected.** 0.9048 on phrasing it was never
   tuned for is a high floor for a phrase lexicon, and it is the reason the offline default is
   defensible rather than a compromise. The two held-out misses are listed above.
3. **The safety guarantees are backend-independent.** Swap the extraction engine entirely —
   rules for a 120-billion-parameter model — and hallucination rate stays 0 and red-flag
   sensitivity stays 1.0. That is the strongest evidence in this document that the guarantees
   come from `record_fact()` and the rule engine rather than from anything being clever.

### A prediction that was wrong, recorded because it was wrong

An earlier draft of this document predicted, in advance, that the LLM would "add little or
nothing on `plain` and `low_literacy` scripts and real recall on `rambling` ones". Measured:

| Difficulty | Offline | Groq | |
|---|---|---|---|
| `rambling` | 1.00 | 1.00 | tied — **predicted a model win, got none** |
| `low_literacy` | 1.00 | 0.68 | **model much worse — the opposite of the prediction** |
| `plain` | 1.00 | 0.94 | model slightly worse |

(Development-set figures, so the rule column is inflated. The direction is still informative.)

The `low_literacy` result is the interesting one: on Hinglish narration the phrase lexicon
beats the hosted model comfortably, because *gutka*, *kala pakhana* and *saans phool* are
exactly the vocabulary a curated list captures and a general model handles inconsistently. The
intuition that LLMs are obviously better at messy real-world speech did not survive being
measured.

### The operational finding

Running the harness against Groq for the first time produced 429s, and those surfaced a
genuine bug: **an unreachable model returned a 503 to the patient instead of degrading to
touch.** The deterministic spine was supposed to cover exactly that case and did not. Fixed
(`voice.py` now treats an LLM failure identically to a bad transcript) and pinned by
`test_the_interview_completes_with_the_model_dead`, which unplugs the model and walks a
complete interview by tap.

Latency is also a deployment fact, not a footnote: 1.8–4.5 s per spoken turn against ~30
questions is minutes of added wait per patient in a queue of thousands. For the OPD volumes in
the problem statement, the offline path is not merely the safe default — it is the only one
whose timing works.

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

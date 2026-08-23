# MediKiosk — build status

**SIH26047** · All India Institute of Ayurveda, Ministry of Ayush
Target: working vertical slice demoing at the SRM internal hackathon, September 2026.

*Last updated 2026-08-24.*

---

## Where it stands

**All seven phases are built and running.** The whole path works end to end: a patient
authenticates with a (mock) ABHA ID, picks a language, gives granular audio-explained consent,
answers by speaking or tapping interchangeably, scans a prior prescription, and a physician
reviews a source-linked draft summary, corrects it, and commits it as a FHIR R4 bundle — after
which the session data is purged.

| | |
|---|---|
| Tests | **200 passing** + a browser smoke test; `ruff`, `mypy` (76 files) and `tsc` clean |
| Backend | ~14,000 lines across 76 modules, 40 API endpoints |
| Frontend | ~3,600 lines, four surfaces, one component per file |
| Content in YAML/JSON | ~1,700 lines — the interview, the rules, the lexicon, the consent scripts |
| Gold evaluation | 50 development scripts + 12 held-out |
| Runs with | no Docker, no network, no API key (SQLite + offline extractor by default) |

### One command

```bash
make setup && make demo
```

Kiosk at `http://127.0.0.1:5173/`, physician review at `/physician`, API docs at `:8000/docs`,
and `:8000/about` lists every invariant and — bluntly — everything that is mocked.

---

## Phase status

| Phase | State | Notes |
|---|---|---|
| **0** Skeleton and contracts | Done | Fact ledger + projection, `record_fact()` choke point, SIH 25026 components ported (`docs/PORTED.md`) |
| **1** Deterministic dialogue | Done | 51 questions across 9 sections, all YAML. Walks with the LLM monkeypatched to raise |
| **2** Extraction layer | Done | Four verification gates. Offline rule extractor is the default; Groq behind the same protocol |
| **3** Voice | Done | Dual-mode, barge-in, per-question degradation. Real noisy WAV fixtures at three SNRs |
| **4** Documents | Done | Two OCR backends, benchmarked. Handwriting lane is structural, not advisory |
| **5** Summary + physician screen | Done | Traceability gate fails generation outright. Click-to-source, 22 red-flag rules |
| **6** ABDM + AYUSH | Done | Consent gate, FHIR bundle with Provenance per resource, audit chain, session purge, Dashavidha |
| **Eval harness** | Done | The differentiator — see below |

### Built after the first pass, from the final build prompt

| Feature | Why it earned its place |
|---|---|
| **Demo mode** (`/demo`) | Five one-click synthetic cases. Without it there is no 90-second demo — nobody taps 49 answers in front of a jury. Each case plays a gold eval script through the **real** pipeline; nothing is pre-recorded. |
| **Contradiction detection** | A patient says "no medicines" while holding a prescription for metformin. Both facts are kept, neither wins, the physician resolves it. Five rules in YAML; five real conflicts on the demo prescription. |
| **Jury drawer** (`d`) | Live state-machine node, facts by tier, "facts with no source: 0", rules evaluated vs fired, which backends are actually running, audit-chain state. Makes the invisible engineering visible without cluttering the clinical screen. |
| **Landing page** | Ten seconds of the demo, and it frames everything — including "This system does not diagnose" above the fold. |
| **Patient review** | The patient reads back what they said before a physician sees it. The cheapest guard against a mishearing reaching a clinician. |
| **Complaint-aware branching** | A cough is no longer asked about pain radiation. Exclusion is by deny-list, so an *unknown* complaint still gets the pain questions. |
| **FHIR preview** | The bundle can be inspected before commit. Transmits nothing; tested not to. |

---

## The measured numbers

`make eval` reproduces all of this.

| Metric | Target | Development (n=50) | **Held-out (n=12)** |
|---|---|---|---|
| Hallucination rate | **0**, hard-enforced | **0.0000** | **0.0000** |
| Unsourced claims in summaries | **0**, hard-enforced | **0** | **0** |
| Red-flag sensitivity | **≥ 0.98** | **1.0000** | **1.0000** |
| Priority under-calls | 0 | **0** | **0** |
| Extraction accuracy | tracked | 1.0000 | **0.9048** |
| History completeness | tracked | 0.9928 | **0.9695** |
| Time to physician-ready summary | tracked | 1 ms median | 1 ms median |

**Read the held-out column.** The 12 held-out scripts were written *after* the extraction
lexicon was tuned, with a standing rule that whatever they score is what gets published.

The finding is the shape of the table, not any single figure: **extraction drops 9.5 points on
unseen phrasing while the safety metrics do not move at all.** That is the architecture showing
up in the measurements — hallucination rate is 0 because `record_fact()` refuses unsourced
facts, not because the extractor is good, and red-flag sensitivity holds because every question
is answerable by tap, so a failed extraction degrades to touch and the tap still reaches the
rule engine.

Full methodology, caveats and the two held-out misses (listed by name, deliberately unfixed) are
in `docs/EVALUATION.md`.

### Rules vs the hosted LLM, measured on held-out data

| Metric | Offline rules | Groq `gpt-oss-120b` |
|---|---|---|
| Hallucination rate | **0.0000** | **0.0000** |
| Red-flag sensitivity | **1.0000** | **1.0000** |
| Extraction accuracy | 0.9048 | **0.9524** |
| Median time to summary | **1 ms** | 1,843 ms |

**The model buys about 5 points of extraction recall on unseen phrasing, buys nothing on any
safety metric, and costs roughly 1,800× the latency.** That is the whole case for the
architecture: the LLM is an optional enhancement to one stage, and the guarantees hold
identically whichever backend is running.

Two findings worth flagging. First, on `low_literacy` Hinglish the rule lexicon beats the
hosted model comfortably (1.00 vs 0.68 on the development set) — the opposite of a prediction
this repo made in writing beforehand, and recorded in `docs/EVALUATION.md` because it was
wrong. Second, at 1.8–4.5 s per spoken turn across ~30 questions, the hosted path adds minutes
per patient; at OPD volumes the offline path is not just the safe default, it is the only one
whose timing works.

### OCR backends, measured rather than argued about

| Backend | Digital PDF | Clean scan | Degraded phone photo |
|---|---|---|---|
| `textlayer` | recall 1.00, conf 0.99 | *fails honestly* | *fails honestly* |
| `tesseract` | recall 1.00, conf 0.86 | recall 1.00, conf 0.88 | recall 0.75–1.00, conf 0.61–0.83 |

The number that matters is the share routed to human verification: **0% on a clean PDF, 60% on a
degraded lab photo**. That rise is the system working. Tesseract does not get quietly worse as
quality falls — it stays roughly as accurate and becomes *less confident*, and the low-confidence
lane converts that into human review instead of a wrong dosage in a record.

---

## What the evaluation caught

The harness earned its place by failing, not by passing. Every one of these was a real defect
found by running it:

| Defect | Severity |
|---|---|
| `Rule.fires()` passed the clause list where the values dict belongs — **every `any:` red-flag rule silently never fired** | Critical |
| `allergy.reaction` had no phrase lexicon, so an anaphylaxis history in plain words reached the rule engine as nothing | Critical |
| The extractor read **negated symptoms as present**: "a heavy feeling, like pressure, not sharp" yielded `sharp` | Critical |
| An unreachable model returned a 503 to the patient instead of degrading to touch — found by a real Groq rate-limit, now pinned by a test that unplugs the model and walks a whole interview | Critical |
| `breathlessness` had no negated-verb phrasings — "could not breathe" matched nothing | High |
| `cough_3wk` matched one word order but not the other, losing a TB screening trigger | High |
| Negation suppression applied to options that *mean* absence, so "no, I never smoke" recorded nothing | Medium |
| Gold script `s30` expected a rule at severity 8 that needs ≥ 9 — **the eval caught the script being wrong, not the system** | — |
| Complaint-aware branching, first attempt, used an allow-list — which stopped asking about pain character and radiation for any complaint that did not map to a coded option, **including two cardiac emergencies** described vaguely ("just a little discomfort, my wife made me come"). Now a deny-list: an unknown complaint gets more questions, never fewer | Critical |
| `reopen()` reset the cursor but `next_question()` skips already-answered paths, so a patient correcting an answer was silently returned to the same screen | High |
| CSS grid auto-placement put the clinical summary in the 380px right rail and the source drawer in the main column — every Python test passed while the physician screen looked broken | High |

The negation bug is the one worth dwelling on. It was invisible to every unit test, produced a
confident, well-formed, fully-sourced fact, and the fact was wrong in the direction that matters.
Provenance does not protect against it — the span "not sharp" really does contain "sharp". Only
behavioural testing over realistic narration finds it.

---

## What the second build prompt asked for, and what I chose not to do

`SIH26047_CLAUDE_CODE_FINAL_BUILD_PROMPT.md` describes 52 sections of work and opens by
assuming this repo is "an existing 28-question prototype" — it never was. The full audit,
including a gap table against every section, is in **[docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)**.

27 of its 28 success criteria are met. Four things I deliberately did **not** build, because
they would make the codebase worse rather than more complete:

- **`TranslationBackend` protocol** — it would have no consumer. Untranslated questions already
  fall back to English *visibly* (ADR-0007). An abstraction with one mock and no caller is
  clutter.
- **Caregiver mode** — genuinely useful in a real OPD, invisible in a 90-second demo. A
  `source_role` field and a toggle, to add when the demo is not the constraint.
- **A separate "Simple Mode" toggle** — the kiosk *is* simple mode. A toggle implies a worse
  default, and there isn't one.
- **A web `/evaluation` page** — the CLI harness, `docs/EVALUATION.md` and the jury drawer
  already answer "show me the metrics" from three directions. A fourth would be a fourth place
  for the same numbers to drift apart.

## Changes to the original brief

Three things turned out differently from the plan, all recorded here rather than quietly absorbed:

1. **`llama-3.3-70b-versatile` no longer exists.** The model named in the brief has been
   decommissioned by Groq and the API 404s on it. The default is now `openai/gpt-oss-120b`,
   verified against `GET /openai/v1/models`. Check that endpoint before changing it again.
2. **Groq also hosts Whisper**, which was not in the plan and is a better server-side ASR
   option than the Vosk path for a ten-language kiosk — no per-language model download, no
   extra credential. Added as `app/speech/groq_whisper.py` behind the existing
   `SpeechBackend` protocol. It does **not** displace the on-device client backend, which is
   what the shipped kiosk uses because it survives a dead network.
3. **Full translation of all ten languages was not attempted.** Every question carries English
   and Hindi; the rest fall back to English and the API marks `translationMissing: true` so the
   gap is visible in the UI rather than silently served. Fabricating eight languages of clinical
   phrasing I cannot verify would be worse than an honest fallback.

---

## Known gaps and honest limitations

**Nothing here is hidden in a footnote — a judge should be able to find all of it in `/about`.**

- **The ABHA identity layer is a mock.** Locally-signed JWTs, issuer `mock-abdm-idp`, demo OTP
  `123456`, and a permanent banner in the kiosk UI saying so. Not an ABDM integration.
- **The terminology tables are a hand-seeded demo subset** — 24 ICD-11 concepts, 15 NAMASTE, 65
  Dashavidha — not the full NAMASTE release the SIH 25026 service ingested. The ingestion path
  is the same; the data volume is not. Any coding-coverage claim must say so.
- **The gold scripts are synthetic and written by one person.** They encode one person's model
  of how patients speak. Real OPD recordings would move the numbers, probably downward. This is
  not a clinical validation.
- **The 1 ms median is computation only** — machine walk, extraction, rules, projection, summary
  and the traceability check. It excludes the human, the network, ASR and TTS. The honest
  end-to-end figure is dominated by how long a patient takes to answer ~30 questions.
- **The held-out set is small (12).** A 9.5-point gap on 12 scripts has wide error bars. It is
  an indication, not a measurement.
- **Dashavidha Pariksha is patient-reportable subset only.** Classical Prakriti assessment rests
  on observation and pulse examination by a vaidya. The physician screen labels it
  "patient-reported, pending vaidya examination" (ADR-0009).
- **The Bhashini backend is written but unverified against the live endpoint** — we have no
  government credentials. Request/response shapes follow the published pipeline contract; treat
  the first live call as an integration test.
- **The HIS endpoint is a documented FHIR `POST /Bundle` with a stub receiver.** No vendor
  integration, per the problem statement's scope.

---

## What I would do next, in order

1. **Record real speech.** Every ASR number in this repo is about the *degradation policy*, not
   recognition accuracy, because synthetic TTS in synthetic noise measures nothing. Twenty
   recordings of real speakers in a real corridor would be the single highest-value addition.
2. **Grow the held-out set to ~40.** The generalisation estimate is the most valuable number
   here and it currently rests on 12 scripts.
3. **Get a clinician to review `redflags.yaml` and `core.yaml`.** They are deliberately readable
   without Python for exactly this reason, and they have not yet been read by a doctor.
4. **Ingest the real NAMASTE release** through the ported pipeline, so coding coverage becomes a
   real number instead of a demo subset.
5. **Exercise the Alembic migration against real Postgres.** The initial migration is
   generated and the compose stack runs it, but it has only been validated against SQLite.

---

## Commit history

| Commit | Contents |
|---|---|
| `58f09da` | Phases 0–1 — contracts, ported compliance spine, deterministic dialogue |
| `12f280e` | Phases 2–4 — extraction, voice, documents |
| `103fd9f` | Phases 5–6 — red flags, summary, consent, FHIR, API surface |
| `0ce2ed1` | Evaluation harness — 50 gold scripts, 12 held-out, and the gap |

Each message records whether a rule or the LLM was chosen for that phase's work, and why.

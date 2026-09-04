# AGENT.md — working on MediKiosk

Read this before changing anything. It is short on purpose; the long-form reasoning lives in
`docs/`.

MediKiosk is a patient-facing clinical intake platform for **SIH26047** (All India Institute of
Ayurveda, Ministry of Ayush). It produces a structured, source-linked clinical **history** for a
physician to review before an OPD consultation. **It does not diagnose.**

---

## The six invariants

These are architectural, not aspirational. Each is enforced in code, and each has a test that
fails the build if it is violated. **If a change conflicts with one of these, stop and raise it
rather than working around it.**

| # | Invariant | Where it is enforced | Test |
|---|---|---|---|
| 1 | **Never diagnoses.** No endpoint returns an assessment, differential or probability. | `ClinicalHistory` has no assessment-shaped field; `assert_no_assessment()` scans every outbound payload | `test_invariant_no_diagnosis.py` |
| 2 | **Provenance or nothing.** Every fact carries the verbatim utterance or document span it came from, with a tier of `stated` / `confirmed` / `document`. There is no fourth tier. | `record_fact()` — the single writer | `test_invariant_provenance.py` |
| 3 | **Red flags escalate, never de-escalate.** | `Priority` has no member below `ROUTINE`; `raise_priority()` refuses a downward move | `test_summary_and_redflags.py` |
| 4 | **The physician is the committer.** | ABAC restricts `summary.commit` to `clinician`, *and* the body must carry `confirmed: true` | `test_api_end_to_end.py` |
| 5 | **Codes are retrieved, never generated.** Unmapped is a valid 200. | `emit_coding()` — the closed-vocabulary guard, ported from SIH 25026 | `test_api_end_to_end.py` |
| 6 | **Consent gates everything, and sessions die.** | `FactLedger.consent_scopes` + `purge()` on submit / TTL / revocation; every AI call hits the hash-chained audit log | `test_invariant_audit_chain.py` |

### The three things you must not do

1. **Do not add a bypass to `record_fact()`.** No `force=`, no `skip_validation=`, no
   `trust_me=`. A test asserts the signature has none. The absence is the feature.
2. **Do not construct a `Fact` outside `app/contracts/record.py`.** A source-scanning test
   fails the build if you do. (One exception exists and is documented: rehydrating a stored
   row in `app/api/deps.py`.)
3. **Do not let the LLM decide what to ask next.** The state machine walks
   `data/ontology/*.yaml` and nothing else.

---

## Rule or LLM?

The standing question for every new feature, and the answer goes in the commit message.

**The LLM has exactly two jobs.** Both are additive, both are verified, and neither can change
the shape of the record:

1. **Extract slot values from free narration** (`app/llm/extraction.py`). It must return a
   `quote`, and the quote is checked by string search against the actual transcript — not by
   asking the model whether it was honest. Four gates, then `record_fact()` re-checks
   independently.
2. **Smooth prose within a summary section** (`app/modules/summary/prose.py`). Output goes
   through the same token check; one unsupported word and the deterministic bullets are kept.

A **third** model was added for handwriting (`app/modules/documents/trocr.py`), and it is
the same bargain: it recognises characters on a single cropped line and decides nothing.
What it sees, what is kept, and whether the page is trusted at all are rules around it, and
every way it can fail ends at Tesseract. See ADR-0013.

**Everything else is a rule**, including the parts that look like they want a model:

| Task | Why a rule | Where |
|---|---|---|
| Which question comes next | Reproducible, works offline, cannot skip the allergy question | `modules/dialogue/machine.py` |
| Emergency detection | A missed escalation is the only unacceptable error; rules are auditable by a clinician | `redflags/engine.py` + `data/ontology/redflags.yaml` |
| Prescription / lab parsing | A prescription line has a grammar; regex is exact, instant, and gives character offsets for the bbox | `modules/documents/entities.py` |
| Dosing shorthand (BD → twice daily) | A definition, not a judgement, and identical on every prescription in India | `modules/documents/sig.py` + YAML |
| Correcting a misread medicine name | Constrained matching against a closed list with a score, because a *generated* name is fluent and occasionally a different drug | `modules/documents/medications.py` |
| Which text lines are on a page | A row either carries ink or it does not — a measurement, reproducible with no GPU | `modules/documents/segmentation.py` |
| Out-of-range flagging | A range comparison, not an interpretation | `modules/documents/ranges.py` |
| Summary assembly | Predictable structure is what makes a summary readable in 90 seconds | `modules/summary/assemble.py` |

---

## Content lives in YAML, not Python

A clinician must be able to change the interview without touching code. If you find yourself
writing a clinical string in a `.py` file, it belongs in `data/` instead.

| File | What it holds |
|---|---|
| `data/ontology/core.yaml` | Chief complaint, SOCRATES HPI, PMH, surgical, drugs/allergy, family, personal |
| `data/ontology/ros.yaml` | Review of systems |
| `data/ontology/ayush.yaml` | Dashavidha Pariksha + Ahara-Vihara, each answer naming a code |
| `data/ontology/redflags.yaml` | The 22 escalation rules |
| `data/ontology/lexicon.yaml` | Phrase → option mappings, the Hinglish / low-literacy layer |
| `config/consent-scopes.yaml` | The five consent scopes and their audio scripts |
| `config/policy.yaml` | ABAC roles, purposes and actions |
| `data/terminology/*.json` | CodeSystems (ICD-11 subset, NAMASTE, Dashavidha) and reference ranges |
| `data/terminology/prescription-abbreviations.yaml` | Sig codes — BD, TDS, SOS, HS, AC, 1-0-1. Exact lookup, no scoring |
| `data/terminology/medications.json` | The closed list a misread medicine name may be corrected **to**. Not a CodeSystem; emits no codes |

Terminology content is **data**, never code. No medical code string is written at a call site.

---

## Layout

```
app/
  contracts/     provenance.py (the tiers), history.py (ClinicalHistory), record.py (THE CHOKE POINT),
                 projection.py (ledger -> history), no_diagnosis.py
  modules/
    dialogue/    Module A — ontology loader, deterministic machine, answers, voice
    documents/   Module B — OCRBackend protocol + 3 impls (textlayer, tesseract, trocr),
                 preprocess + segmentation (the handwriting lane), sig, medications,
                 prescription, entities, ranges, timeline, pipeline
    summary/     Module C — assemble, prose, traceability (the gate), generate
    consent/     Module D — consent, session lifecycle + purge, HIS push
  redflags/      the rule engine (Invariant 3)
  llm/           protocol, schemas, offline rule extractor, groq, registry, extraction
  speech/        protocol + local / client / groq_whisper / bhashini backends
  terminology/   guard.py (ported: emit_coding), store.py, sidecar.py
  fhir/          r4.py (R4B models, stamped 4.0.1), bundle.py, outcomes.py
  auth/ audit/   ported from SIH 25026 — see docs/PORTED.md
  api/           33 endpoints
eval/            50 gold scripts + 12 held-out + runner + OCR benchmark
frontend/src/    kiosk/ (patient) and physician/ (review) — one component per file
```

---

## Commands

```bash
make setup        # venv + pip + npm
make demo         # API + frontend, one command, no Docker needed
make test         # 180+ tests
make lint         # ruff + mypy + tsc, all must be clean
make eval         # 50 gold scripts + 12 held-out + the gap between them
make check        # lint + test + eval-strict — run before committing
```

Python is **plain `venv` + `pip`** (no uv, no poetry). SQLite by default so everything runs
with no Docker and no network.

---

## Conventions

- **One component per file** in the frontend. The user customises pieces independently.
- **camelCase on the wire, snake_case in Python.** Enforced at the API boundary by
  `api_dump()`. If a field arrives snake_case in the frontend, that is a backend bug — do not
  add a mapping layer.
- **An ADR for every non-obvious decision**, in `docs/adr/`, in the style of ADR-0002.
- **Commit at every phase boundary**, and say in the message whether you reached for a rule or
  the LLM, and why.
- **`ruff` and `mypy` clean at every phase.** Not "mostly clean".

## Out of scope — do not build

No diagnosis, no triage-to-specialty routing, no treatment suggestion. No real patient data
ever — synthetic fixtures only. No kiosk hardware integration. No production ABDM credentials
(the mock IdP stands in). No hospital HIS vendor integration beyond the documented FHIR
endpoint and its stub receiver.

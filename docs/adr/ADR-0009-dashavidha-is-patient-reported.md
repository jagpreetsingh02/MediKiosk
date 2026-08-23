# ADR-0009 — Dashavidha Pariksha is captured as patient-report, and labelled as such

**Context.** The problem statement asks for an AYUSH extended interview capturing the tenfold
examination. Classical Dashavidha Pariksha is not a questionnaire: Prakriti, Sara and Samhanana
are determined by a vaidya through observation, palpation and pulse examination. A kiosk cannot
do any of that.

**Decision.** Capture the **patient-reportable subset** — the questions a person can honestly
answer about their own build, digestion, stamina, sleep and adaptability — and label the whole
section "Ayurvedic assessment (patient-reported)" everywhere it appears: in the ontology title,
in the summary section heading, and in the FHIR bundle.

Vaya is not asked at all. It is derived from the date of birth in the ABHA token, because
asking a patient their age band when the token already carries their age wastes a question in a
two-minute consultation.

Every answer names a code in the Dashavidha CodeSystem, and the sidecar retrieves it. The
ontology never constructs one (Invariant 5).

**Alternatives.** Claim full Dashavidha assessment (untrue, and a vaidya reviewing the output
would spot it immediately, which is worse than not offering it); omit the section (the problem
statement asks for it, and the patient-reportable subset genuinely saves consultation time).

**Consequences.** The output is a *starting point for* a vaidya's examination, not a
substitute. `data/terminology/dashavidha.json` is also a MediKiosk-local CodeSystem — AYUSH has
not published one — and it says so in its own `publisher` field. When AYUSH publishes, the
ingestion path is unchanged and only the JSON is replaced.

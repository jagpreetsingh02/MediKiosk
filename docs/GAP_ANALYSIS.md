# MediKiosk gap analysis

Date: 24 August 2026

## Quantified result

Scoring the handoff's exact 40 capabilities with equal weights gives:

| Status | Count | Share |
|---|---:|---:|
| DONE | 12 | 30% |
| PARTIAL | 22 | 55% |
| MISSING | 4 | 10% |
| UNSAFE | 2 | 5% |

Weighted maturity (DONE=1, PARTIAL=0.5, MISSING/UNSAFE=0) is **57.5%**, leaving a **42.5% gap**. The eight-item longitudinal spine is only **25% mature**: Encounter, durable fact, timeline, and AYUSH longitudinalization are partial; Patient, medication history, recurrence, and historical similarity are missing.

## Capability matrix

| Capability | Status | Primary gap |
|---|---|---|
| Longitudinal Patient model | MISSING | No durable Patient or patient history APIs |
| Encounter model | PARTIAL | Temporary session only |
| ClinicalFact model | PARTIAL | Structured facts are purged |
| Source provenance | PARTIAL | Not durable; exported coverage incomplete |
| Adaptive state machine | DONE | Preserve |
| SOCRATES branching | DONE | Preserve |
| Voice ASR | PARTIAL | Browser dependency; confidence defect |
| Voice TTS | PARTIAL | Device/language behavior unverified |
| Multilingual flow | PARTIAL | English/Hindi content; other visible fallbacks |
| Touch/text fallback | DONE | Preserve |
| Low-confidence speech fallback | UNSAFE | Confidence 0 becomes 0.7 in browser |
| Consent | UNSAFE | Missing authorization/ownership checks on routes |
| Identity/ABHA mock | PARTIAL | Mock is allowed; ownership enforcement absent |
| Document upload | DONE | Add durable reference policy |
| OCR | DONE | Preserve |
| Medication extraction | DONE | Promote to longitudinal event |
| Lab extraction | PARTIAL | Projection loses some semantics |
| Bounding-box provenance | PARTIAL | No original page rendering |
| Timeline | PARTIAL | Current session documents only |
| Medication history | MISSING | No cross-visit state/query |
| Symptom recurrence | MISSING | No episode aggregation |
| Historical similarity retrieval | MISSING | No implementation/vector query |
| Contradiction detection | DONE | Extend across visits |
| Red-flag engine | PARTIAL | Proposal decisions not persisted |
| Patient review | DONE | Preserve |
| Physician dashboard | PARTIAL | Current encounter, not longitudinal cockpit |
| Click-to-source | PARTIAL | Transcript works; scan evidence does not |
| Physician edit/confirm | PARTIAL | No per-fact accept/reject |
| Draft summary | DONE | Preserve as one view |
| FHIR bundle | PARTIAL | Incomplete resources/provenance |
| HIS stub | DONE | Clearly label stub |
| Audit trail | PARTIAL | Missing red-flag decision persistence |
| Session teardown | DONE | Must promote confirmed facts first |
| AYUSH mode | PARTIAL | Buried opt-in; not longitudinal |
| Dashavidha capture | PARTIAL | Coding helper not wired |
| Terminology validation | DONE | Demo subset only |
| Demo mode | PARTIAL | No real multi-visit similarity demo |
| Evaluation harness | PARTIAL | No longitudinal/auth/similarity metrics |
| Offline fallback | PARTIAL | Text/touch good; voice claim unproven |
| Tests | PARTIAL | 200 pass, but critical target paths absent |

## Highest-priority gaps

1. Fix route ownership/authorization and false ASR confidence.
2. Add durable Patient/Encounter/Fact/Evidence models and transactional promotion before purge.
3. Build cross-visit timeline and medication history.
4. Add explainable same-patient similarity/recurrence.
5. Connect OCR verification and original document evidence.
6. Close FHIR/AYUSH provenance and evaluation gaps.


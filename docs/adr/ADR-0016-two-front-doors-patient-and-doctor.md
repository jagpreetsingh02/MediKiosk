# ADR-0016 — Two front doors: Patient and Doctor

**Context.** The product had one front door and one primary action. The hero's `Start` button
opened `/intake`; the physician workspace was a link in the nav corner and a round icon; the
patient's own record was a sentence below the fold ("Been seen already? See your records").

That shape is right for a kiosk bolted to a wall, where the only person who will ever touch it
is a patient. It is wrong for the product, which has exactly two kinds of user who want
opposite things on arrival — a patient wants their record and today's visit, a doctor wants the
list of people waiting — and it had three concrete consequences:

1. **The doctor's half of the system was invisible on the screen that introduces the system.**
2. **The patient's own record was the least discoverable thing in it**, reachable only from a
   sentence under the fold, despite being the surface a patient returns to most often.
3. **The two roles' components had begun to mix.** `PatientPortal.tsx` imported
   `LongitudinalTimeline`, `MedicationHistory` and `EvidenceDrawer` from `physician/`
   (ADR-0015 records the decision, and it was a reasonable one — the data shape is identical).
   Nothing broke. What it meant was that the patient's screen sat one prop away from any
   control a future edit added to a physician component. That was not hypothetical: the
   clinician's "Needs reconciliation" chip — a sentence written for somebody reading *about* a
   patient — was already rendering on the patient's own medicines tab, and only a human
   reading the page could have noticed.

**Decision.**

**The first screen is the fork.** Two doors of equal weight, labelled in the words each user
would use about themselves: *I am a patient*, *I am a doctor*. Not "intake" and "physician
review", which are the system's words for its own parts. `Try demo` stays as the quiet third
action, because "try it" is not a role.

**Each door owns a workflow, and the two do not overlap.**

| | Patient (`/patient`, `/intake`) | Doctor (`/doctor`, `/physician`) |
|---|---|---|
| opens on | their own confirmed record | who is waiting, and who is next |
| reads | visits, timeline, medicines, papers, what changed | the brief, today's intake, timeline, medicines, similar visits, documents |
| writes | a visit (the kiosk), a paper (OCR) | verifications, corrections, the commit |

`/physician` stays mounted alongside `/doctor` rather than redirecting: the demo launcher deep
links `?session=…`, and a redirect drops the query string.

**The separation is structural, not a matter of care.** `patient/` and `physician/` never
import from each other; `physician/` never imports from `kiosk/` either, because the kiosk *is*
the patient surface. The three views both roles genuinely need —
`LongitudinalTimeline`, `MedicationHistory`, `EvidenceDrawer` — moved to `frontend/src/record/`,
which imports from neither. Where their language differs by reader, that is an explicit
`audience` prop over **wording only**, never over which rows are shown: the patient sees the
same reconciliation finding a clinician does, said as "the doctor will check this with you".
`tests/test_role_separation.py` scans the import graph and fails the build on a regression, in
the same spirit as `test_ocr_has_one_front_door.py`.

**The patient's new capabilities reuse the existing pipeline exactly.** Two of the five patient
tabs are new, and neither adds a route or a table:

* **My papers** lists the rows on the patient's own timeline that carry a `documentRef` —
  which is precisely the set of papers that made it onto the record — and can open the original
  page. Adding one creates a real intake session with `history` + `documents` consent and runs
  the kiosk's own `DocumentUpload` against `POST /api/v1/sessions/{ref}/documents`, the single
  OCR front door.
* **What changed** joins the confirmed visits (`/encounters`) to the timeline's `encounterRef`,
  so the patient can see the record *becoming* what it says today rather than only its current
  state.

**The doctor's two new affordances are the same story.** `NextPatient` renders `queue[0]` —
the server's ordering, never re-derived here — as the workspace's opening state, replacing
"Select a patient from the queue". `DocumentIntake` posts a paper handed across the desk to
the same session document route the kiosk uses, so it goes through `ingest()`, the consent
gate, the size limit and `record_fact()` unchanged, and lands unverified entities in the
verification lane that already exists.

**Alternatives.**

*A patient-side document store, so "upload a record" did not need a visit.* Rejected. It would
mean a document that is part of a patient's record without a physician ever having confirmed
it, which is Invariant 4 with a hole in it, and a second promotion path into durable evidence
alongside `promote()`. The honest version is the one built: the upload runs now, the reading is
shown to the patient immediately, and the screen says in words that it joins the record once a
doctor confirms it.

*Letting the doctor grant the `documents` consent scope when uploading for a patient who
declined it.* Rejected — a permission a clinician can give themselves over a patient's papers
is not a permission. `consent.grant` stays with `patient` in `config/policy.yaml`; the 403 and
its wording reach the doctor's screen unedited, and the next step is the patient's.

*Redirecting `/physician` to `/doctor`.* Rejected: it drops `?session=`.

*Two separate applications, or a role stored on the session.* Rejected as far more than the
problem needs. The roles are already separated where it counts — ABAC actions,
`assert_session_access`, `_resolve()` — and none of that is touched here. This is a
reorganisation of screens.

**Consequences.**

No backend change was required and none was made: no new route, no schema change, no policy
edit, nothing touched in OCR, provenance, the audit chain, FHIR/HIS or the clinical logic. The
patient's new upload path creates an ordinary intake session, so a paper added from the portal
appears in the doctor's queue as a session with no interview answers — which is a true
statement about what it is, and the doctor's queue is where it should be visible.

A patient adding a paper consents to `history` as well as `documents`, because `history` is a
required scope and a session cannot exist without it. The consent record therefore says
exactly what was agreed, and the screen names both before the file picker opens.

`ADR-0008` ("two surfaces share nothing") and `ADR-0013` ("one visual language, two densities")
both stand. This changes neither: the two surfaces still share one ground and one material,
still run at two densities, and now share exactly three components — in a folder that belongs
to neither of them, with a test that says so.

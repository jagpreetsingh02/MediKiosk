# ADR-0015 — A patient reads its own timeline, medications and document pages

**Context.** `app/api/routes_patient.py` grew four routes that give the *physician* the whole
longitudinal record — `/timeline`, `/medications`, the document page image, and (already
patient-reachable) `/brief`. The first three were gated by `session.read`, the ABAC action only
`clinician` holds, on the theory that the raw payload — `factRef`, `documentRef`, ontology-shaped
statuses — was clinician bookkeeping a patient screen shouldn't show.

In practice `H.timeline()` and `H.medication_history()` (`app/modules/encounter/history.py`)
already return plain-language rows (`label`, `detail`, `status`, `howWeKnow`) with no ontology
paths, tiers or confidence scores — the same class of already-safe, already-exposed identifiers
`/brief`, `/brief/patient` and `/encounters` hand back today (`encounterRef`, `documentRef`).
The patient portal (`PatientPortal.tsx`) had no medication history or upload timeline at all as
a result, even though the physician workspace's `LongitudinalTimeline` and `MedicationHistory`
components already render this exact data shape correctly.

**Decision.** Widen `patient_timeline`, `patient_medications` and `document_file` from
`require_action("session.read")` / `require_action("document.read")` to
`require_any_action("session.read", "report.read_own")` and
`require_any_action("document.read", "document.read_own")` respectively — the same pattern
already used on `/brief`, `/brief/patient`, `/brief.pdf` and `/encounters` in this file.
`_resolve()` is the ownership choke point for every one of these routes regardless of which
action let the caller in; widening the action does not touch it. `document.read_own` was
already granted to `patient` in `config/policy.yaml` for the kiosk's own-document verification
lane, so no policy file change was needed — only reusing a grant that existed for a different
route.

No new endpoints, no stripped/duplicate payload shape. The frontend mounts the SAME
`LongitudinalTimeline` and `MedicationHistory` components the physician workspace uses, at
patient density, in `PatientPortal.tsx`.

**Alternatives.** A parallel patient-only endpoint returning a hand-stripped payload — rejected
for the reason `to_patient_view()` already exists as a *derivation* of the clinician brief
rather than a second assembly: two payload shapes for the same underlying data drift apart, and
`to_patient_view()`'s own docstring names that drift as the failure mode being avoided. Keeping
the routes clinician-only and building nothing for the patient side — rejected per the feature
request this ADR accompanies.

**Consequences.** A patient's timeline/medications response can carry a `factRef` or
`documentRef` — both already opaque strings a patient token could already retrieve via
`/encounters` and the evidence route, so this does not create a new information disclosure, only
a new route reachable with data already reachable elsewhere. `tests/test_patient_self_service.py`
scans the route source for the widened dependencies and confirms `patient` still holds
`report.read_own`/`document.read_own` in the policy file, so a regression that silently narrows
the action back to clinician-only fails the build.

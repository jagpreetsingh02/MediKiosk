"""The synthetic/real boundary, and the one place it is enforced.

⛔ WHY THIS IS A MODULE AND NOT A CONVENTION.

Guest mode writes REAL ROWS INTO THE REAL SCHEMA. That is deliberate — a demo backed by a
parallel fake code path proves nothing about the product, and every previous shortcut of that
kind in this repo (the OCR back door, the seeded "voice" confidence) had to be undone later.
The cost of doing it honestly is that demo data and clinical data now live in the same tables,
distinguished by one boolean.

A boolean everyone is trusted to remember is not a boundary. So:

    every retrieval that can return rows belonging to a DIFFERENT patient
    must pass through `restrict_to_cohort()`

and `tests/test_synthetic_boundary.py` fails the build on a cross-patient query that does not.

THE RULE IS SYMMETRIC, and the second half is the half that matters:

    a demo patient must not retrieve against a real one
        — a judge at a stand would be shown a stranger's medical history

    a real patient must not retrieve against a demo one
        — a clinician would be shown a "similar previous visit" that was invented for a
          conference, presented in the same type, with the same click-to-source affordance,
          and nothing on the screen would say it was fiction

The first is a privacy breach. The second is a clinical safety failure, and it is the one a
`WHERE is_synthetic = false` written from the demo's point of view would miss entirely.

WHAT IS NOT RESTRICTED, on purpose: looking up your OWN record by `patient_ref` or `abha_ref`.
Those are exact-identity reads already gated by `_resolve()` in the API layer, and filtering
them by cohort would break guest mode's ability to read the record it just created.
"""

from __future__ import annotations

from sqlalchemy import Select

from app.db.durable import Patient


def restrict_to_cohort[S: Select](statement: S, *, viewer: Patient) -> S:
    """Confine a cross-patient query to the viewer's own cohort.

    The statement must already join or select `Patient`; this adds the WHERE clause that
    keeps synthetic and real records from ever seeing each other.

        stmt = select(Encounter).join(Patient)
        stmt = restrict_to_cohort(stmt, viewer=patient)

    Matching on equality rather than on a hardcoded `false` is what makes it symmetric: the
    same call is correct from either side, so there is no version of this that is right for
    production and wrong for the demo.
    """
    return statement.where(Patient.is_synthetic == viewer.is_synthetic)  # type: ignore[return-value]


def same_cohort(a: Patient, b: Patient) -> bool:
    """Whether two patients may appear in each other's retrieval results at all."""
    return bool(a.is_synthetic) == bool(b.is_synthetic)


def cohort_label(patient: Patient) -> str:
    """What the UI must say about this record. Never blank for a synthetic one."""
    return "synthetic" if patient.is_synthetic else "clinical"

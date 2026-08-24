"""The clinical brief — what a physician gets back for the intake they were given.

WHY THIS EXISTS. Everything upstream of here is capture: the patient answers, documents
are read, facts are recorded with their provenance. What came back out was prose. A
paragraph is readable, but it does not let anyone *see* that forty-nine answers and three
lab reports became something a clinician can act on in ninety seconds. This module is the
return value of the whole system.

WHAT IT IS ALLOWED TO SAY, which is the hard part.

Invariant 1 is absolute: MediKiosk never diagnoses. So every number below is one of two
things, and never a third:

  * a **recorded observation** — a value that appeared on a document or was stated by the
    patient, carried with its date and its source;
  * an **arithmetic relation between recorded observations** — a difference, a count, a
    span of days, a set intersection.

Subtraction is not prediction. "HbA1c is 1.7 higher than on 10 Feb 2025" is a fact about
two measurements. "HbA1c is worsening" is a clinical judgement, and this module does not
make it: `delta` is a number and a direction word describing the *number*, never the
patient. There are no risk scores, no probabilities, no severity indices, and no
percentages anywhere in this file — a percentage between two encounters reads as a
likelihood, and the physician screen has refused to print one since the similarity work.

The range flags are the same deal. `range_flag` is set by comparing a value to the
reference interval **printed on the report itself**, which `AGENT.md` already classifies
as "a range comparison, not an interpretation".
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.durable import (
    ClinicalFactRecord,
    Encounter,
    MedicationEvent,
    ObservationEvent,
    Patient,
    RedFlagEventRecord,
)
from app.modules.encounter import history as H

#: How many points make a line worth drawing. One measurement is a value, not a trend, and
#: rendering it as a chart would imply a shape that was never measured.
MIN_SERIES = 2

#: Analytes worth leading with when a patient has many. Ordered by how often they change
#: management in a general OPD, not by any scoring of this patient.
PRIORITY_ANALYTES = (
    "hba1c",
    "fasting_glucose",
    "haemoglobin",
    "creatinine",
    "total_cholesterol",
    "tsh",
    "esr",
)


def _direction(delta: float) -> str:
    """A word describing the NUMBER, never the patient.

    "higher" is a statement about two measurements. "worse" would be a clinical judgement
    about a person, and this system does not make those.
    """
    if abs(delta) < 1e-9:
        return "unchanged"
    return "higher" if delta > 0 else "lower"


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


async def observation_series(db: AsyncSession, patient_id: int) -> list[dict[str, Any]]:
    """Every analyte with enough measurements to have a shape, oldest first.

    Each series carries the reference interval that was printed on the report, so the chart
    can draw the band rather than the frontend inventing one — a normal range invented in
    the browser would be a clinical claim made by a stylesheet.
    """
    rows = list(
        (
            await db.execute(
                select(ObservationEvent)
                .where(ObservationEvent.patient_id == patient_id)
                .order_by(ObservationEvent.observed_on)
            )
        )
        .scalars()
        .all()
    )

    grouped: dict[str, list[ObservationEvent]] = {}
    for row in rows:
        if row.value is None or row.observed_on is None:
            # An undated or non-numeric result is real and is kept elsewhere; it simply
            # cannot be a point on a time axis, and inventing a date for it would be
            # fabricating provenance.
            continue
        grouped.setdefault(row.analyte_key or row.display.casefold(), []).append(row)

    series: list[dict[str, Any]] = []
    for key, points in grouped.items():
        if len(points) < MIN_SERIES:
            continue
        points.sort(key=lambda r: r.observed_on or date.min)
        latest, previous = points[-1], points[-2]
        delta = round((latest.value or 0) - (previous.value or 0), 4)
        series.append(
            {
                "analyteKey": key,
                "display": latest.display,
                "unit": latest.unit,
                "referenceLow": latest.reference_low,
                "referenceHigh": latest.reference_high,
                "rangeSource": latest.range_source,
                "points": [
                    {
                        "observedOn": _iso(p.observed_on),
                        "value": p.value,
                        "rangeFlag": p.range_flag,
                        "documentRef": p.source_document_ref,
                    }
                    for p in points
                ],
                "latest": {
                    "value": latest.value,
                    "observedOn": _iso(latest.observed_on),
                    "rangeFlag": latest.range_flag,
                },
                # Arithmetic between two measurements. Not a trajectory, not a forecast.
                "change": {
                    "delta": delta,
                    "direction": _direction(delta),
                    "sinceOn": _iso(previous.observed_on),
                    "sinceValue": previous.value,
                },
                "outOfRangeCount": sum(1 for p in points if p.range_flag in ("high", "low")),
            }
        )

    order = {k: i for i, k in enumerate(PRIORITY_ANALYTES)}
    series.sort(key=lambda s: (order.get(s["analyteKey"], len(order)), s["display"]))
    return series


async def recurrence(
    db: AsyncSession, patient_id: int, *, exclude_encounter_id: int | None = None
) -> dict[str, Any]:
    """How often this patient has been seen, and for what — by counting, not by inferring.

    A physician asking "have they been here for this before?" is asking a question about
    the record, and the record can answer it exactly.
    """
    encounters = [e for e in await H.encounters_for(db, patient_id) if e.kind == "intake"]
    by_headline: dict[str, list[Encounter]] = {}
    for encounter in encounters:
        by_headline.setdefault((encounter.headline or "Unspecified").strip().casefold(), []).append(
            encounter
        )

    ordered = sorted(by_headline.values(), key=lambda rows: (-len(rows), rows[0].headline or ""))
    groups: list[dict[str, Any]] = [
        {
            "headline": rows[0].headline,
            "count": len(rows),
            "occurredOn": [_iso(r.occurred_at.date()) for r in rows],
            "encounterRefs": [r.encounter_ref for r in rows],
        }
        for rows in ordered
    ]
    return {
        "visits": len(encounters),
        "firstSeenOn": _iso(min(e.occurred_at.date() for e in encounters)) if encounters else None,
        "groups": groups,
        "note": (
            "Counts of confirmed visits on this patient's record. Not a prediction and not "
            "a statement about cause."
        ),
    }


async def medication_snapshot(db: AsyncSession, patient_id: int) -> dict[str, Any]:
    """What is on the record, and how each item is known.

    `medication_history()` already threads a drug across visits and refuses to conclude
    that a prescription means the medicine is still being taken. This adds only the counts
    a header needs.
    """
    threads = await H.medication_history(db, patient_id)
    return {
        "count": len(threads),
        "needsReconciliation": [t["name"] for t in threads if t["needsReconciliation"]],
        "threads": threads,
        "note": (
            "Status describes how each mention is KNOWN. A past prescription is not "
            "evidence of current use."
        ),
    }


async def red_flags(db: AsyncSession, encounter_id: int | None) -> dict[str, Any]:
    """Deterministic rules: how many ran, which fired, and the evidence for each.

    "No rule fired" is reported as exactly that. It is not, and must never be rendered as,
    "this patient is low risk".
    """
    if encounter_id is None:
        return {"evaluated": 0, "fired": [], "note": "No confirmed encounter yet."}
    rows = list(
        (
            await db.execute(
                select(RedFlagEventRecord).where(RedFlagEventRecord.encounter_id == encounter_id)
            )
        )
        .scalars()
        .all()
    )
    fired = [
        {
            "ruleId": r.rule_id,
            "level": r.level,
            "rationale": r.rationale,
            "evidence": r.evidence_json,
        }
        for r in rows
        if r.fired
    ]
    return {
        "evaluated": len(rows),
        "fired": fired,
        "note": (
            f"{len(rows)} deterministic rules were evaluated and {len(fired)} fired. "
            "'No rule fired' is not a statement that this patient is low risk."
        ),
    }


async def what_changed(
    db: AsyncSession, *, patient_id: int, current: Encounter | None
) -> dict[str, Any]:
    """Set difference between this visit's recorded features and the previous visit's.

    The most common question at the start of a follow-up consultation is "what is different
    since last time", and it is answerable by comparing two sets of recorded values. No
    weighting, no ranking — appearing in one set and not the other is the whole test.
    """
    if current is None:
        return {"comparedWith": None, "new": [], "resolved": [], "persisting": []}

    prior = [
        e
        for e in await H.encounters_for(db, patient_id)
        if e.kind == "intake" and e.id != current.id and e.occurred_at < current.occurred_at
    ]
    if not prior:
        return {"comparedWith": None, "new": [], "resolved": [], "persisting": []}

    previous = max(prior, key=lambda e: e.occurred_at)
    now_features = await H.current_features(db, current.id)
    then_features = await H.current_features(db, previous.id)

    def flatten(features: dict[str, set[str]]) -> set[tuple[str, str]]:
        return {(path, value) for path, values in features.items() for value in values}

    now, then = flatten(now_features), flatten(then_features)
    def shape(pairs: set[tuple[str, str]]) -> list[dict[str, str]]:
        return [{"path": path, "value": value} for path, value in sorted(pairs)]
    return {
        "comparedWith": {
            "encounterRef": previous.encounter_ref,
            "occurredOn": _iso(previous.occurred_at.date()),
            "headline": previous.headline,
        },
        "new": shape(now - then),
        "resolved": shape(then - now),
        "persisting": shape(now & then),
        "note": (
            "Recorded features present in one visit and not the other. "
            "A comparison, not a judgement."
        ),
    }


async def build(db: AsyncSession, patient: Patient) -> dict[str, Any]:
    """Assemble the whole brief for one patient."""
    encounters = await H.encounters_for(db, patient.id)
    intakes = [e for e in encounters if e.kind == "intake"]
    current = max(intakes, key=lambda e: e.occurred_at) if intakes else None

    facts = 0
    if current is not None:
        facts = (
            await db.execute(
                select(ClinicalFactRecord).where(ClinicalFactRecord.encounter_id == current.id)
            )
        ).scalars().all().__len__()

    documented = list(
        (
            await db.execute(
                select(MedicationEvent).where(MedicationEvent.patient_id == patient.id)
            )
        )
        .scalars()
        .all()
    )

    return {
        "patientRef": patient.patient_ref,
        "displayName": patient.display_name,
        "generatedAt": datetime.now(UTC).isoformat(),
        "current": None
        if current is None
        else {
            "encounterRef": current.encounter_ref,
            "occurredOn": _iso(current.occurred_at.date()),
            "headline": current.headline,
            "priority": current.priority,
            "completeness": current.completeness,
            "confirmedBy": current.confirmed_by,
            "factCount": facts,
        },
        "trends": await observation_series(db, patient.id),
        "medications": await medication_snapshot(db, patient.id),
        "recurrence": await recurrence(db, patient.id),
        "redFlags": await red_flags(db, current.id if current else None),
        "changed": await what_changed(db, patient_id=patient.id, current=current),
        "counts": {
            "encounters": len(intakes),
            "observations": len(await observation_series(db, patient.id)),
            "medicationEvents": len(documented),
        },
        "notice": (
            "A structured view of what is on this patient's record. It contains no "
            "assessment, no differential and no probability — every number here is a "
            "recorded measurement or arithmetic between recorded measurements."
        ),
    }

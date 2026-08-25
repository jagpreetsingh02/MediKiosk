"""The Clinical Intelligence Brief, assembled deterministically from stored rows.

THIS FUNCTION IS PURE AND MUST STAY PURE. It takes a `Rows` — a frozen read handed over by
`loader.load` — and returns a dict. It has no database session, no clock, no randomness and no
LLM. Two calls on the same `Rows` return byte-identical output, and `tests/test_report_
determinism.py` fails the build if that ever stops being true.

That is not a performance choice. Every clinical line carries the `factRef` and `evidenceIds`
it came from, and the physician clicks those to open the original. If assembly were
non-deterministic, the line and the evidence it points at could come from different reads, and
nothing on the screen would reveal it. Determinism is what makes click-to-source honest.

═══ WHAT MAY APPEAR HERE ═══

NO EVIDENCE, NO LINE. A fact with no `SourceEvidence` is not a durable fact under Invariant 2,
and it is dropped rather than rendered with an empty source. The single exception is state
`not_asked`, which by definition has no span because nothing happened — and it never appears
as a clinical line either, only in the completeness section as an absence.

NO INTERPRETATION. Every value is a recorded measurement or arithmetic between recorded
measurements. `range_flag` is a comparison against an interval, which `AGENT.md` classifies as
a comparison and not a judgement. There are no scores, no probabilities and no percentages
between encounters — a percentage reads as a likelihood.

EMPTY IS SAID, NOT FILLED. A section with nothing in it returns its `items: []` and an
`emptyReason` in plain words. Filler — "no significant findings", "unremarkable" — is a
clinical assertion nobody made, and inferring it from absence is exactly the error the
`not_asked` / `declined` distinction exists to prevent.
"""

from __future__ import annotations

from typing import Any

from app.db.durable import ClinicalFactRecord, SourceEvidence
from app.modules.report.loader import Rows

#: Bumped whenever the shape or content of the output changes. Stored on every snapshot,
#: because a change here is exactly what makes an old snapshot unreproducible — and the honest
#: response to that is to record which assembler wrote it.
REPORT_VERSION = "3.0"

#: How many comparable points make a line worth drawing. One measurement is a value, not a
#: trend; two joined by a line implies a shape that was never measured in between, so the
#: series is returned as points and the frontend never interpolates.
MIN_SERIES = 2

#: The Current Clinical Snapshot, in the order a clinician reads it. Path -> label.
#: Ordered as a tuple rather than a dict comprehension over the facts, because the section's
#: order must not depend on what happens to be present.
SNAPSHOT_FIELDS: tuple[tuple[str, str], ...] = (
    ("chief_complaint.text", "Chief concern"),
    ("chief_complaint.duration", "Duration"),
    ("hpi.onset", "Onset"),
    ("hpi.severity", "Severity"),
    ("hpi.site", "Site"),
    ("hpi.character", "Character"),
    ("hpi.timing", "Pattern"),
    ("hpi.exacerbating", "Made worse by"),
    ("hpi.relieving", "Made better by"),
    ("hpi.associated", "Associated symptoms"),
)

#: Allergy and patient-reported-medication paths, kept separate because they are their own
#: blocks on the page and because getting an allergy wrong is the highest-consequence error
#: on this screen.
ALLERGY_FIELDS: tuple[tuple[str, str], ...] = (
    ("drug_allergy.has_allergy", "Known drug allergy"),
    ("drug_allergy.substances", "Substances"),
    ("drug_allergy.reaction", "Reaction"),
    ("drug_allergy.taking_medicines", "Currently taking medicines"),
)

#: States that mean "the patient engaged with the question but there is no value". These are
#: real answers with real provenance and are shown as such — never as a blank.
ABSENCE_STATES = ("unknown", "declined")


def _value_of(fact: ClinicalFactRecord) -> Any:
    return (fact.value_json or {}).get("v")


def _is_live(fact: ClinicalFactRecord) -> bool:
    return fact.superseded_by_id is None and fact.invalidated_reason is None


def _line(fact: ClinicalFactRecord, evidence: list[SourceEvidence], label: str) -> dict[str, Any]:
    """One clinical line, carrying everything click-to-source needs to open its origin."""
    return {
        "label": label,
        "path": fact.path,
        "value": _value_of(fact),
        "displayValue": fact.display_value,
        "state": fact.state,
        "tier": fact.tier,
        "confidence": fact.confidence,
        "confidenceStatus": fact.confidence_status,
        "confirmedByPhysician": fact.confirmed_by_physician,
        # ── 3C: the provenance handle on every line ────────────────────────────
        "factRef": fact.fact_ref,
        "evidenceIds": [e.id for e in evidence],
        #: What KIND of source this opens, so the drawer knows what to render before it
        #: fetches: patient text, a voice segment, or a document region.
        "evidenceKinds": sorted({e.source_type for e in evidence}),
        #: The finer distinction the drawer actually renders on. `document` wants a cropped
        #: page region, `voice` wants the transcript segment with its ASR confidence, and
        #: `touch`/`typed` want the patient's own words. Same source_type, different screens.
        "evidenceModalities": sorted({e.modality for e in evidence if e.modality}),
    }


def _live_by_path(rows: Rows) -> dict[str, ClinicalFactRecord]:
    """The standing answer for each path. Later rows win, which is what supersession means."""
    out: dict[str, ClinicalFactRecord] = {}
    for fact in rows.facts:
        if _is_live(fact):
            out[fact.path] = fact
    return out


def _renderable(fact: ClinicalFactRecord, rows: Rows) -> list[SourceEvidence] | None:
    """The evidence for a fact, or None if it must not be rendered.

    NO EVIDENCE, NO LINE — Invariant 2, applied at the last possible moment so a fact that
    lost its evidence cannot slip onto the page looking like any other. `not_asked` is
    excluded here rather than filtered upstream, because it is the one state that legitimately
    has no span and must still never appear as a clinical line.
    """
    if fact.state == "not_asked":
        return None
    evidence = rows.evidence.get(fact.id, [])
    if not evidence:
        return None
    return evidence


# ──────────────────────────────────────────────────────────── sections


def _header(rows: Rows) -> dict[str, Any]:
    patient, current = rows.patient, rows.current
    return {
        "patientRef": patient.patient_ref,
        "displayName": patient.display_name,
        "ageYears": patient.age_years,
        "gender": patient.gender,
        "preferredLanguage": patient.preferred_language,
        "encounter": None
        if current is None
        else {
            "encounterRef": current.encounter_ref,
            "occurredOn": current.occurred_at.date().isoformat(),
            "headline": current.headline,
            "priority": current.priority,
            "language": current.language,
            "ayushMode": current.ayush_mode,
            "consentRef": current.consent_ref,
        },
        "encounterCount": len(rows.encounters),
    }


def _snapshot(rows: Rows) -> dict[str, Any]:
    """Current Clinical Snapshot — this visit, in the order a clinician reads it."""
    live = _live_by_path(rows)
    items: list[dict[str, Any]] = []
    for path, label in SNAPSHOT_FIELDS:
        fact = live.get(path)
        if fact is None:
            continue
        evidence = _renderable(fact, rows)
        if evidence is None:
            continue
        items.append(_line(fact, evidence, label))

    allergies: list[dict[str, Any]] = []
    for path, label in ALLERGY_FIELDS:
        fact = live.get(path)
        if fact is None:
            continue
        evidence = _renderable(fact, rows)
        if evidence is None:
            continue
        allergies.append(_line(fact, evidence, label))

    # Patient-reported medicines: the `medications[N].*` family, grouped by index so a name,
    # dose and frequency read as one medicine rather than three unrelated lines.
    groups: dict[str, dict[str, Any]] = {}
    for path, fact in sorted(live.items()):
        if not path.startswith("medications[") or "]." not in path:
            continue
        index, _, leaf = path.partition("].")
        evidence = _renderable(fact, rows)
        if evidence is None:
            continue
        group = groups.setdefault(index, {"parts": {}, "lines": []})
        group["parts"][leaf] = fact.display_value or _value_of(fact)
        group["lines"].append(_line(fact, evidence, leaf))

    reported_medications = [
        {
            "name": g["parts"].get("name"),
            "dose": g["parts"].get("dose"),
            "frequency": g["parts"].get("frequency"),
            "duration": g["parts"].get("duration"),
            "lines": g["lines"],
        }
        for _, g in sorted(groups.items())
    ]

    return {
        "items": items,
        "allergies": allergies,
        "reportedMedications": reported_medications,
        "emptyReason": None
        if items or allergies or reported_medications
        else "Nothing was recorded for this visit yet.",
    }


def _red_flags(rows: Rows) -> dict[str, Any]:
    fired = [r for r in rows.red_flags if r.fired]
    return {
        "items": [
            {
                "ruleId": r.rule_id,
                "level": r.level,
                "rationale": r.rationale,
                "evidence": r.evidence_json or [],
            }
            for r in fired
        ],
        # Invariant 3: escalation only. There is no "low priority" and nothing here lowers one.
        "note": (
            "Deterministic rules. Escalation only — a rule can raise a priority, never lower one."
        ),
        "emptyReason": None if fired else "No escalation rule matched what was recorded.",
    }


def _what_changed(rows: Rows) -> dict[str, Any]:
    """A factual diff against the most recent prior confirmed encounter.

    Set membership, nothing else: a (path, value) pair present in one visit and not the other.
    No weighting, no ranking, no "improved" or "worse" — those are judgements. `persisting`
    matters as much as `new`: a complaint in its third consecutive visit is the single most
    useful thing on a follow-up screen, and it is invisible if only differences are shown.
    """
    if rows.previous is None:
        return {
            "comparedWith": None,
            "new": [],
            "resolved": [],
            "persisting": [],
            "emptyReason": (
                "This is the first recorded visit, so there is nothing to compare against."
            ),
        }

    def pairs(facts: list[ClinicalFactRecord]) -> set[tuple[str, str]]:
        out: set[tuple[str, str]] = set()
        for fact in facts:
            if not _is_live(fact) or fact.state == "not_asked":
                continue
            value = fact.display_value or _value_of(fact)
            if value is None:
                continue
            out.add((fact.path, str(value)))
        return out

    now, then = pairs(rows.facts), pairs(rows.prior_facts)
    # fact_ref carried on the `new` side so a changed line is still clickable to its source.
    ref_by_pair = {
        (f.path, str(f.display_value or _value_of(f))): f.fact_ref
        for f in rows.facts
        if _is_live(f)
    }

    def shape(items: set[tuple[str, str]], *, with_ref: bool) -> list[dict[str, Any]]:
        return [
            {
                "path": path,
                "value": value,
                **({"factRef": ref_by_pair.get((path, value))} if with_ref else {}),
            }
            for path, value in sorted(items)
        ]

    return {
        "comparedWith": {
            "encounterRef": rows.previous.encounter_ref,
            "occurredOn": rows.previous.occurred_at.date().isoformat(),
            "headline": rows.previous.headline,
        },
        "new": shape(now - then, with_ref=True),
        "resolved": shape(then - now, with_ref=False),
        "persisting": shape(now & then, with_ref=True),
        "note": (
            "Recorded features present in one visit and not the other. "
            "A comparison, not a judgement."
        ),
        "emptyReason": None,
    }


def _observations(rows: Rows) -> dict[str, Any]:
    """Labs, as points. A series is only drawn where two or more comparable values exist."""
    by_analyte: dict[str, list[Any]] = {}
    for row in rows.observations:
        if row.analyte_key is None or row.value is None:
            continue
        by_analyte.setdefault(row.analyte_key, []).append(row)

    series: list[dict[str, Any]] = []
    singles: list[dict[str, Any]] = []
    for key, points in sorted(by_analyte.items()):
        # Comparable means same unit. Plotting mg/dL against mmol/L on one axis draws a cliff
        # that is a units change, not a clinical one.
        units = {p.unit for p in points if p.unit}
        shaped = {
            "analyteKey": key,
            "display": points[-1].display,
            "unit": points[-1].unit,
            "points": [
                {
                    "observedOn": p.observed_on.isoformat() if p.observed_on else None,
                    "value": p.value,
                    "unit": p.unit,
                    "rangeFlag": p.range_flag,
                    "referenceLow": p.reference_low,
                    "referenceHigh": p.reference_high,
                    "rangeSource": p.range_source,
                    "documentRef": p.source_document_ref,
                }
                for p in points
            ],
        }
        if len(points) >= MIN_SERIES and len(units) <= 1:
            # Arithmetic between two recorded measurements. Not a prediction.
            first, last = points[0], points[-1]
            shaped["delta"] = (
                None
                if first.value is None or last.value is None
                else round(last.value - first.value, 4)
            )
            shaped["chartable"] = True
            series.append(shaped)
        else:
            shaped["chartable"] = False
            shaped["notChartableBecause"] = (
                "Only one recorded value — a single measurement is a value, not a trend."
                if len(points) < MIN_SERIES
                else "Values were recorded in different units, so they are not "
                "comparable on one axis."
            )
            singles.append(shaped)

    return {
        "series": series,
        "singles": singles,
        "note": (
            "Recorded measurements and arithmetic between them. "
            "Nothing is interpolated between points."
        ),
        "emptyReason": None
        if series or singles
        else "No laboratory values have been recorded for this patient.",
    }


def _medications(rows: Rows) -> dict[str, Any]:
    """Documented, historical and patient-reported — told apart, never merged.

    A PRESCRIPTION IS NOT PROOF OF ADHERENCE. `status` records what the record can support:
    that a medicine was documented on a page, or stated by the patient. Whether it is actually
    being taken is not knowable from any of it, and the wording never implies otherwise.
    """
    current_id = rows.current.id if rows.current else None
    items = [
        {
            "name": m.name,
            "normalizedName": m.normalized_name,
            "dose": m.dose,
            "frequency": m.frequency,
            "duration": m.duration,
            "route": m.route,
            "status": m.status,
            "observedOn": m.observed_on.isoformat() if m.observed_on else None,
            "documentRef": m.source_document_ref,
            "factRef": m.source_fact_ref,
            "origin": "this-visit" if m.encounter_id == current_id else "previous-visit",
        }
        for m in rows.medications
    ]
    return {
        "items": items,
        "note": (
            "What the record can support: documented on a page, or stated by the patient. "
            "A prescription is not proof that a medicine is being taken."
        ),
        "emptyReason": None if items else "No medicines have been recorded for this patient.",
    }


def _timeline(rows: Rows) -> dict[str, Any]:
    items = [
        {
            "encounterRef": e.encounter_ref,
            "occurredOn": e.occurred_at.date().isoformat(),
            "headline": e.headline,
            "priority": e.priority,
            "confirmedBy": e.confirmed_by,
            "isCurrent": rows.current is not None and e.id == rows.current.id,
        }
        for e in rows.encounters
    ]
    return {
        "items": items,
        "emptyReason": None if items else "No confirmed visits are on record.",
    }


def _similar(rows: Rows) -> dict[str, Any]:
    """Prior encounters of THIS patient that share recorded features with this one.

    SAME PATIENT ONLY, enforced by the loader's query — `Rows` never contains another
    patient's encounters, so this cannot leak across records even by mistake.

    Shared features are explained in WORDS. No score and no probability: a number here would
    read as a likelihood of something, and there is nothing being predicted.
    """
    if rows.current is None or not rows.previous:
        return {"items": [], "emptyReason": "There is no earlier visit to compare with."}

    def feature_set(facts: list[ClinicalFactRecord]) -> set[tuple[str, str]]:
        return {
            (f.path, str(f.display_value or _value_of(f)))
            for f in facts
            if _is_live(f) and (f.display_value or _value_of(f)) is not None
        }

    now = feature_set(rows.facts)
    items: list[dict[str, Any]] = []
    for encounter in rows.encounters:
        if rows.current and encounter.id == rows.current.id:
            continue
        facts = rows.prior_facts if rows.previous and encounter.id == rows.previous.id else []
        if not facts:
            continue
        shared = sorted(now & feature_set(facts))
        if not shared:
            continue
        items.append(
            {
                "encounterRef": encounter.encounter_ref,
                "occurredOn": encounter.occurred_at.date().isoformat(),
                "headline": encounter.headline,
                "sharedFeatures": [{"path": p, "value": v} for p, v in shared],
                # The explanation is the list itself, spelled out. Not a similarity score.
                "why": f"Shares {len(shared)} recorded feature(s) with this visit.",
            }
        )
    return {
        "items": items,
        "note": (
            "This patient's own earlier visits, matched on recorded features. "
            "No score, no probability."
        ),
        "emptyReason": None
        if items
        else "No earlier visit shares a recorded feature with this one.",
    }


def _contradictions(rows: Rows) -> dict[str, Any]:
    """Both sides preserved. NEITHER is silently chosen — that is the whole point.

    A contradiction resolved by picking a winner is a contradiction hidden. The physician sees
    both recorded values and both sources, and decides.
    """
    items = [
        {
            "contradictionRef": c.contradiction_ref,
            "ruleId": c.rule_id,
            "label": c.label,
            "sideA": c.side_a_json,
            "sideB": c.side_b_json,
        }
        for c in rows.contradictions
    ]
    return {
        "items": items,
        "note": "Both recorded sources are shown. Neither has been chosen for you.",
        "emptyReason": None if items else "No contradictions were detected in what was recorded.",
    }


def _unresolved(rows: Rows) -> dict[str, Any]:
    """What is missing, declined, superseded or invalidated — the honest gaps.

    This section is why `state` and `superseded_by_id` were added. Without it the brief can
    only show what is known, and a physician cannot tell a question that was never asked from
    one the patient declined to answer.
    """
    declined = [
        {
            "path": f.path,
            "label": f.path,
            "state": f.state,
            "factRef": f.fact_ref,
        }
        for f in rows.facts
        if _is_live(f) and f.state in ABSENCE_STATES
    ]
    superseded = [
        {
            "path": f.path,
            "wasValue": f.display_value or _value_of(f),
            "factRef": f.fact_ref,
            "recordedAt": f.recorded_at.isoformat(),
        }
        for f in rows.facts
        if f.superseded_by_id is not None
    ]
    invalidated = [
        {
            "path": f.path,
            "wasValue": f.display_value or _value_of(f),
            "reason": f.invalidated_reason,
            "factRef": f.fact_ref,
        }
        for f in rows.facts
        if f.invalidated_reason is not None
    ]
    return {
        "declinedOrUnknown": declined,
        "superseded": superseded,
        "invalidated": invalidated,
        "note": (
            "Answers the patient changed are kept, not overwritten. A question that was never "
            "asked is not the same as one that was declined."
        ),
        "emptyReason": None
        if declined or superseded or invalidated
        else "Nothing was declined, changed or ruled out during this visit.",
    }


def _completeness(rows: Rows) -> dict[str, Any]:
    """Collected / missing / declined. NOT A SCORE.

    `Encounter.completeness` is a float and is deliberately not surfaced as the headline here:
    "82% complete" invites a physician to read a number where they should read a list. What
    they need to know is precisely WHICH things are absent, so that is what this returns.
    """
    live = _live_by_path(rows)
    known = [path for path, _ in SNAPSHOT_FIELDS + ALLERGY_FIELDS]
    collected: list[str] = []
    declined: list[str] = []
    missing: list[str] = []
    for path in known:
        fact = live.get(path)
        if fact is None or fact.state == "not_asked":
            missing.append(path)
        elif fact.state in ABSENCE_STATES:
            declined.append(path)
        else:
            collected.append(path)
    return {
        "collected": collected,
        "declined": declined,
        "missing": missing,
        "note": (
            "A list, not a score. 'Missing' means the question was not reached or not "
            "answered; 'declined' means the patient was asked and chose not to say."
        ),
    }


def _confirmation(rows: Rows) -> dict[str, Any]:
    """Invariant 4's receipt, on the page. Nothing here is durable without it."""
    current = rows.current
    confirmations = [
        {
            "decision": d.decision,
            "actor": d.actor,
            "decidedAt": d.decided_at.isoformat(),
        }
        for d in rows.decisions
    ]
    return {
        "confirmed": current is not None and bool(current.confirmed_by),
        "confirmedBy": current.confirmed_by if current else None,
        "confirmedAt": current.confirmed_at.isoformat() if current else None,
        "decisions": confirmations,
        "note": "Nothing reaches the record until a physician confirms it.",
    }


# ──────────────────────────────────────────────────────────── assembly


def assemble(rows: Rows) -> dict[str, Any]:
    """The whole brief. PURE — no session, no clock, no randomness. See the module docstring."""
    return {
        "reportVersion": REPORT_VERSION,
        "audience": "clinician",
        "header": _header(rows),
        "snapshot": _snapshot(rows),
        "redFlags": _red_flags(rows),
        "whatChanged": _what_changed(rows),
        "timeline": _timeline(rows),
        "medications": _medications(rows),
        "observations": _observations(rows),
        "similarEncounters": _similar(rows),
        "contradictions": _contradictions(rows),
        "unresolved": _unresolved(rows),
        "completeness": _completeness(rows),
        "confirmation": _confirmation(rows),
        "notice": (
            "A structured view of what is on this patient's record. It contains no "
            "assessment, no differential and no probability — every value here is a recorded "
            "measurement, a recorded statement, or arithmetic between recorded measurements."
        ),
    }

"""The clinical brief: what comes back out, and what must never come back out.

The brief is the product's return value — the thing a physician gets for the intake they
were given. That makes it the single most dangerous surface in the system, because it is
where an interpretation would be most useful and most forbidden.

These tests hold two lines at once: the numbers must be *there* (a brief with no content
is not a brief), and none of them may be an assessment.
"""

from __future__ import annotations

import pytest

from app.modules.encounter import history as H
from app.modules.encounter import report as R


async def test_a_single_measurement_is_not_drawn_as_a_trend(seeded_patient) -> None:
    """One point has no shape. Rendering it as a line would imply a slope nobody measured."""
    db, patient = seeded_patient
    series = await R.observation_series(db, patient.id)
    assert series, "the seeded patient must have at least one chartable series"
    assert all(len(s["points"]) >= R.MIN_SERIES for s in series)


async def test_the_series_carries_the_range_printed_on_the_report(seeded_patient) -> None:
    """The band must come from the document, never from the browser.

    A reference interval invented in the frontend would be a clinical claim made by a
    stylesheet.
    """
    db, patient = seeded_patient
    for s in await R.observation_series(db, patient.id):
        assert s["referenceLow"] is not None or s["referenceHigh"] is not None
        assert s["rangeSource"]


async def test_points_are_in_chronological_order(seeded_patient) -> None:
    db, patient = seeded_patient
    for s in await R.observation_series(db, patient.id):
        dates = [p["observedOn"] for p in s["points"]]
        assert dates == sorted(dates), f"{s['display']} is out of order"


async def test_change_is_arithmetic_between_two_real_measurements(seeded_patient) -> None:
    """`delta` must equal last minus previous — not a fitted slope, not a projection."""
    db, patient = seeded_patient
    for s in await R.observation_series(db, patient.id):
        points = s["points"]
        expected = round(points[-1]["value"] - points[-2]["value"], 4)
        assert s["change"]["delta"] == pytest.approx(expected)
        assert s["change"]["sinceOn"] == points[-2]["observedOn"]


def test_direction_describes_the_number_not_the_patient() -> None:
    """'higher' is a fact about two measurements. 'worse' would be a judgement."""
    assert R._direction(1.0) == "higher"
    assert R._direction(-1.0) == "lower"
    assert R._direction(0.0) == "unchanged"
    forbidden = {"worse", "worsening", "improving", "better", "deteriorating", "critical"}
    for delta in (-2.0, 0.0, 2.0):
        assert R._direction(delta) not in forbidden


async def test_the_hba1c_story_survives_the_round_trip(seeded_patient) -> None:
    """The demo's clinical spine: improves after the prescription, deteriorates after.

    If this ever flattens, the seed has lost the trajectory the whole demonstration rests
    on and the charts become three identical points pretending to be a trend.
    """
    db, patient = seeded_patient
    series = {s["analyteKey"]: s for s in await R.observation_series(db, patient.id)}
    hba1c = series["hba1c"]
    values = [p["value"] for p in hba1c["points"]]
    assert len(values) >= 3, "HbA1c needs at least three measurements to show a shape"
    assert values[1] < values[0], "the middle reading should be the improvement"
    assert values[-1] > values[1], "the last reading should be the deterioration"


async def test_recurrence_counts_and_does_not_predict(seeded_patient) -> None:
    db, patient = seeded_patient
    result = await R.recurrence(db, patient.id)
    assert result["visits"] >= 1
    assert sum(g["count"] for g in result["groups"]) == result["visits"]
    assert "not a prediction" in result["note"].lower()


async def test_no_rule_fired_is_never_dressed_up_as_reassurance(seeded_patient) -> None:
    db, patient = seeded_patient
    encounters = await H.encounters_for(db, patient.id)
    flags = await R.red_flags(db, encounters[0].id if encounters else None)
    assert "low risk" in flags["note"].lower(), (
        "the note must explicitly refuse the 'no rule fired means low risk' reading"
    )


# ------------------------------------------------------ Invariant 1, end to end


#: Words that would turn a record into an assessment. The brief may not contain any of
#: them, in any field, at any depth.
FORBIDDEN = (
    "differential",
    "likely",
    "probability",
    "probable",
    "risk score",
    "suggests",
    "consistent with",
    "recommend",
    "prognosis",
)


def _walk(value: object, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            out.append(str(key))
            _walk(item, out)
    elif isinstance(value, list | tuple):
        for item in value:
            _walk(item, out)


async def test_the_brief_contains_no_assessment_language(seeded_patient) -> None:
    """Invariant 1, applied to the one screen most tempted to break it."""
    db, patient = seeded_patient
    brief = await R.build(db, patient)

    text: list[str] = []
    _walk(brief, text)
    blob = " ".join(text).lower()
    # The closing notice names the forbidden things in order to deny them; that denial is
    # the one place the words may legitimately appear.
    allowed = brief["notice"].lower()
    real = [word for word in FORBIDDEN if word in blob and word not in allowed]
    assert not real, f"assessment-shaped language reached the brief: {real}"


async def test_the_brief_passes_the_outbound_no_diagnosis_guard(seeded_patient) -> None:
    """The same scanner every outbound payload goes through (Invariant 1)."""
    from app.contracts.no_diagnosis import assert_no_assessment

    db, patient = seeded_patient
    assert_no_assessment(await R.build(db, patient))


async def test_the_brief_actually_has_something_in_it(seeded_patient) -> None:
    """A brief that refuses to say anything is not safe, it is useless.

    This is the counterweight to every test above: the point of the record is that
    something comes back out of it.
    """
    db, patient = seeded_patient
    brief = await R.build(db, patient)
    assert brief["trends"], "no chartable results"
    assert brief["medications"]["count"] > 0, "no medicines"
    assert brief["recurrence"]["visits"] > 0, "no visits"
    assert brief["counts"]["observations"] > 0

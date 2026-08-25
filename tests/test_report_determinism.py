"""The brief is a pure function, and this is what keeps it one.

WHY THIS MATTERS MORE THAN IT LOOKS. Every clinical line in the brief carries the `factRef`
and `evidenceIds` it came from, and a physician clicks those to open the original statement or
document region. That contract only holds if the line and its evidence came from the same
read. A brief that assembled differently on two runs could show a line whose refs point at a
different fact than the one rendered — and nothing on screen would reveal it.

So `assemble()` is pure by construction: it takes a frozen `Rows` and has no session, no clock
and no randomness available to it. These tests fail the build if anyone reintroduces one — the
most likely being a `datetime.now()` for "generated at", which is why that field lives on the
snapshot writer and not in the payload.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.durable import ClinicalFactRecord, Encounter, Patient, SourceEvidence
from app.modules.report import brief
from app.modules.report.loader import Rows

BRIEF_SOURCE = Path(brief.__file__)


def _fact(**kw) -> ClinicalFactRecord:
    defaults = dict(
        id=1,
        encounter_id=1,
        fact_ref="fact_aaa",
        path="chief_complaint.text",
        value_json={"v": "headache"},
        display_value="headache",
        tier="stated",
        state="stated",
        confidence=0.9,
        confidence_status="measured",
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        superseded_by_id=None,
        invalidated_reason=None,
        confirmed_by_physician=False,
    )
    return ClinicalFactRecord(**{**defaults, **kw})


def _evidence(fact_id: int = 1, ev_id: int = 10) -> SourceEvidence:
    return SourceEvidence(
        id=ev_id,
        fact_id=fact_id,
        source_type="utterance",
        verbatim="my head hurts",
        language="en",
    )


def _rows(**kw) -> Rows:
    patient = Patient(
        id=1, patient_ref="pat_test", display_name="Test", year_of_birth=1970, gender="female"
    )
    encounter = Encounter(
        id=1,
        encounter_ref="enc_test",
        patient_id=1,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        kind="intake",
        confirmed_by="dr.test",
        confirmed_at=datetime(2026, 1, 1, tzinfo=UTC),
        priority="routine",
    )
    base = dict(
        patient=patient,
        encounters=[encounter],
        current=encounter,
        previous=None,
        facts=[_fact()],
        prior_facts=[],
        evidence={1: [_evidence()]},
    )
    return Rows(**{**base, **kw})


def _dump(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def test_two_runs_on_the_same_rows_are_byte_identical() -> None:
    rows = _rows()
    assert _dump(brief.assemble(rows)) == _dump(brief.assemble(rows))


def test_the_payload_carries_no_timestamp_of_its_own() -> None:
    """`generatedAt` in the payload would make byte-equality impossible and prove nothing.

    It is metadata about the render, not content, so it belongs to the snapshot writer. This
    catches it being helpfully added back.
    """
    payload = _dump(brief.assemble(_rows()))
    assert "generatedAt" not in payload, (
        "a clock in the payload breaks determinism; stamp it on the snapshot instead"
    )


def test_assemble_cannot_reach_a_database_or_a_clock() -> None:
    """A source scan, because the bug would be a *correct-looking* call.

    A `datetime.now()` added to a section function would pass every other test in this file's
    neighbourhood — the output would still be well-formed and the section would still be
    right. Only the import graph shows it.
    """
    tree = ast.parse(BRIEF_SOURCE.read_text(encoding="utf-8"))
    banned_calls = {"now", "utcnow", "today", "random", "uuid4", "shuffle", "time"}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in banned_calls:
                offenders.append(f"line {node.lineno}: {name}()")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            if "sqlalchemy" in module or module.startswith("app.db.session"):
                # The row TYPES are fine to import; a session or a query builder is not.
                for alias in node.names:
                    if alias.name in {"select", "AsyncSession", "get_sessionmaker"}:
                        offenders.append(f"line {node.lineno}: imports {alias.name}")
    assert not offenders, (
        "assemble() must stay pure — no clock, no randomness, no database:\n  "
        + "\n  ".join(offenders)
    )


def test_a_fact_with_no_evidence_never_reaches_the_page() -> None:
    """Invariant 2 at the render boundary: no evidence, no line."""
    rows = _rows(evidence={})
    payload = brief.assemble(rows)
    assert payload["snapshot"]["items"] == []
    assert payload["snapshot"]["emptyReason"], "an empty section must say why, not sit blank"


def test_not_asked_never_renders_as_a_clinical_line() -> None:
    """The one state allowed to exist without a span must still never look like an answer."""
    rows = _rows(facts=[_fact(state="not_asked", display_value=None, value_json=None)])
    payload = brief.assemble(rows)
    assert payload["snapshot"]["items"] == []
    assert "chief_complaint.text" in payload["completeness"]["missing"]


def test_declined_is_reported_separately_from_missing() -> None:
    """'We never asked' and 'she chose not to say' are different facts about the visit."""
    rows = _rows(facts=[_fact(state="declined", display_value=None, value_json=None)])
    payload = brief.assemble(rows)
    completeness = payload["completeness"]
    assert "chief_complaint.text" in completeness["declined"]
    assert "chief_complaint.text" not in completeness["missing"]
    assert any(
        d["path"] == "chief_complaint.text" for d in payload["unresolved"]["declinedOrUnknown"]
    )


def test_a_superseded_fact_is_kept_and_reported_not_dropped() -> None:
    """Changing an answer appends. The old value stays readable, with its evidence."""
    old = _fact(id=1, fact_ref="fact_old", display_value="headache", superseded_by_id=2)
    new = _fact(id=2, fact_ref="fact_new", display_value="chest pain")
    rows = _rows(facts=[old, new], evidence={1: [_evidence(1, 10)], 2: [_evidence(2, 11)]})
    payload = brief.assemble(rows)

    shown = [i["displayValue"] for i in payload["snapshot"]["items"]]
    assert shown == ["chest pain"], "the live answer is the one that stands"
    superseded = payload["unresolved"]["superseded"]
    assert [s["wasValue"] for s in superseded] == ["headache"], (
        "the replaced answer must remain visible — overwriting it would let a line point at "
        "the source of a statement the patient corrected"
    )


def test_an_invalidated_fact_leaves_the_page_but_not_the_record() -> None:
    """A dead branch is ruled out, with its reason — never silently deleted."""
    dead = _fact(invalidated_reason="Asked about pregnancy; patient is male")
    payload = brief.assemble(_rows(facts=[dead]))
    assert payload["snapshot"]["items"] == []
    assert payload["unresolved"]["invalidated"][0]["reason"].startswith("Asked about pregnancy")


def test_no_percentage_or_probability_appears_anywhere() -> None:
    """Invariant 1. A percentage between encounters reads as a likelihood of something.

    SCANS KEYS AND DATA, NOT PROSE. The first version of this matched the payload as one
    string and failed on the notice that says the brief "contains no probability" — the
    disclaimer, not a violation. Explanatory copy is exactly where these words SHOULD appear,
    so the check skips the known prose fields and looks at the structure instead.
    """
    banned = ("probability", "likelihood", "riskscore", "confidenceinterval", "percentile")
    prose_keys = {"note", "notice", "emptyReason", "why", "notChartableBecause", "rationale"}
    offenders: list[str] = []

    def walk(node: object, path: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if any(b in key.lower() for b in banned):
                    offenders.append(f"{path}.{key} (key)")
                if key not in prose_keys:
                    walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
        elif isinstance(node, str):
            for b in banned:
                if b in node.lower():
                    offenders.append(f"{path} = {node!r}")

    walk(brief.assemble(_rows()))
    assert not offenders, "interpretation leaked into the data:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("section", ["snapshot", "redFlags", "medications", "observations"])
def test_every_empty_section_explains_itself(section: str) -> None:
    """Never a blank space where a reader supplies their own meaning."""
    rows = _rows(facts=[], evidence={}, medications=[], observations=[], red_flags=[])
    payload = brief.assemble(rows)
    assert payload[section]["emptyReason"], f"{section} went blank without saying why"

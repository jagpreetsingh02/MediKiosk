"""Phase 1 — the deterministic spine. Exhaustive, because this is the part that still works
when the demo network drops and the model is unreachable."""
from __future__ import annotations

import pytest

from app.contracts.provenance import Modality
from app.contracts.record import FactLedger
from app.modules.dialogue.answers import record_answer, record_derived
from app.modules.dialogue.machine import DialogueMachine, DialogueState
from app.modules.dialogue.ontology import (
    Condition,
    evaluate_condition,
    load_ontology,
    should_ask,
)


def test_ontology_loads_and_is_internally_consistent() -> None:
    onto = load_ontology(ayush=True)
    assert len(onto.sections) == 9
    assert len(onto.by_id) == len(onto.by_path), "ids and paths must be 1:1"
    for question in onto.by_id.values():
        assert "en" in question.prompt
        if question.kind in ("single_choice", "multi_choice"):
            assert question.options
            values = [o.value for o in question.options]
            assert len(values) == len(set(values)), f"{question.id} has duplicate option values"


def test_every_question_is_answerable_by_tap() -> None:
    """Invariant of the kiosk: speech is never the only way to answer anything."""
    onto = load_ontology(ayush=True)
    unanswerable = [
        q.id for q in onto.by_id.values()
        if q.kind in ("single_choice", "multi_choice", "duration") and not q.options
    ]
    assert not unanswerable, f"questions with no tap options: {unanswerable}"


def test_ayush_sections_only_load_in_ayush_mode() -> None:
    assert load_ontology(ayush=False).section("ayush") is None
    assert load_ontology(ayush=True).section("ayush") is not None


@pytest.mark.parametrize(
    ("clause", "values", "expected"),
    [
        (Condition(path="a", eq="x"), {"a": "x"}, True),
        (Condition(path="a", eq="x"), {"a": "y"}, False),
        (Condition(path="a", eq="x"), {}, False),
        (Condition(path="a", eq="x"), {"a": ["x", "y"]}, True),
        (Condition(path="a", **{"in": ["x", "z"]}), {"a": "z"}, True),
        (Condition(path="a", not_in=["x"]), {"a": "y"}, True),
        (Condition(path="a", contains="pain"), {"a": "chest pain now"}, True),
        (Condition(path="a", gte=12), {"a": 30}, True),
        (Condition(path="a", lte=55), {"a": 64}, False),
        (Condition(path="a", recorded=True), {"a": "anything"}, True),
        (Condition(path="a", recorded=True), {}, False),
        (Condition(path="a", not_recorded=True), {}, True),
        (Condition(path="a", gte=12), {"a": "not a number"}, False),
    ],
)
def test_condition_dsl(clause, values, expected) -> None:
    assert evaluate_condition(clause, values) is expected


def test_unknown_path_never_opens_a_branch() -> None:
    """A branch guarded by 'the patient said yes' must not open before we have asked."""
    onto = load_ontology()
    surgical_detail = onto.by_id["psh.which"]
    assert should_ask(surgical_detail, {}) is False
    assert should_ask(surgical_detail, {"past_surgical.any": False}) is False
    assert should_ask(surgical_detail, {"past_surgical.any": True}) is True


def test_pregnancy_question_is_gated_deterministically() -> None:
    question = load_ontology().by_id["ph.pregnancy"]
    assert should_ask(question, {"demographics.gender": "female", "demographics.age_years": 30})
    assert not should_ask(question, {"demographics.gender": "male", "demographics.age_years": 30})
    assert not should_ask(question, {"demographics.gender": "female", "demographics.age_years": 8})
    assert not should_ask(question, {"demographics.gender": "female", "demographics.age_years": 70})


def _walk(answers: dict, *, ayush: bool = False, demographics: dict | None = None):
    state = DialogueState(session_id="s", language="en", ayush_mode=ayush)
    state.values.update(demographics or {})
    ledger = FactLedger("s")
    machine = DialogueMachine(state, ledger)
    order: list[str] = []
    guard = 0
    while (q := machine.next_question()) is not None and guard < 200:
        guard += 1
        order.append(q.question_id)
        if q.question_id in answers:
            value, modality = answers[q.question_id]
            record_answer(
                machine, ledger, turn_id=q.turn_id, question_id=q.question_id,
                value=value, modality=modality,
            )
        else:
            machine.decline(q.question_id)
    for question, value, _code in machine.derived_questions():
        record_derived(machine, ledger, question, value)
    return order, ledger, machine


MINIMAL = {
    "cc.text": ("fever", Modality.TOUCH),
    "cc.duration": ("days_1_3", Modality.TOUCH),
    "hpi.site": ("whole_body", Modality.TOUCH),
}


def test_machine_is_deterministic_across_identical_runs() -> None:
    first, _, _ = _walk(MINIMAL)
    second, _, _ = _walk(MINIMAL)
    assert first == second, "the same answers must produce the same question order, always"


def test_machine_runs_with_the_llm_unavailable(monkeypatch) -> None:
    """Unplug the model entirely. The spine must not notice."""
    import app.llm.offline as offline_module

    def explode(*args, **kwargs):
        raise RuntimeError("no LLM available — this must never be reached by the spine")

    monkeypatch.setattr(offline_module.OfflineLLM, "complete", explode, raising=False)
    order, ledger, _ = _walk(MINIMAL)
    assert len(order) > 20
    assert len(ledger.active_facts()) == 3


def test_declining_records_an_absence_not_a_value() -> None:
    _, ledger, _ = _walk({})
    assert not ledger.active_facts(), "declining must never write a value"
    assert ledger.absences, "declining must be recorded as an explicit absence"
    reasons = {a.reason.value for a in ledger.absences}
    assert "declined" in reasons


def test_closed_branch_records_not_asked() -> None:
    answers = dict(MINIMAL)
    answers["psh.any"] = (False, Modality.TOUCH)
    _, ledger, _ = _walk(answers)
    not_asked = {a.path for a in ledger.absences if a.reason.value == "not_asked"}
    assert "past_surgical.which" in not_asked
    assert "past_surgical.year" in not_asked


def test_full_socrates_hpi_is_walked() -> None:
    answers = {
        "cc.text": ("pain", Modality.TOUCH),
        "cc.duration": ("week_1", Modality.TOUCH),
        "hpi.site": ("chest", Modality.TOUCH),
        "hpi.onset": ("sudden", Modality.TOUCH),
        "hpi.character": ("pressure", Modality.TOUCH),
        "hpi.radiation": ("left_arm", Modality.TOUCH),
        "hpi.associated": (["sweating"], Modality.TOUCH),
        "hpi.timing": ("constant", Modality.TOUCH),
        "hpi.exacerbating": (["worse_effort"], Modality.TOUCH),
        "hpi.severity": (9, Modality.TOUCH),
    }
    order, ledger, machine = _walk(answers)
    socrates_paths = {f.path for f in ledger.active_facts() if f.path.startswith("hpi.")}
    assert socrates_paths == {
        "hpi.site", "hpi.onset", "hpi.character", "hpi.radiation",
        "hpi.associated", "hpi.timing", "hpi.exacerbating", "hpi.severity",
    }, "all eight SOCRATES elements must be captured"


def test_radiation_is_not_asked_for_a_limb_complaint() -> None:
    answers = dict(MINIMAL)
    answers["hpi.site"] = ("limbs", Modality.TOUCH)
    _, ledger, _ = _walk(answers)
    not_asked = {a.path for a in ledger.absences if a.reason.value == "not_asked"}
    assert "hpi.radiation" in not_asked


def test_derived_vaya_is_computed_not_asked() -> None:
    order, ledger, _ = _walk(
        MINIMAL, ayush=True, demographics={"demographics.age_years": 64},
    )
    assert "ayush.vaya" not in order, "a derived question must never be put to the patient"
    vaya = ledger.at_path("ayush.vaya")
    assert vaya and vaya[0].value == "vriddha"
    assert "derived from" in vaya[0].source.verbatim


def test_progress_never_exceeds_one_hundred_percent() -> None:
    _, _, machine = _walk(MINIMAL)
    progress = machine.progress()
    assert 0 <= progress["percent"] <= 100


def test_answer_to_an_unknown_option_is_refused(machine, ledger) -> None:
    from app.core.errors import ValidationError

    q = machine.next_question()
    with pytest.raises(ValidationError, match="not options of this question"):
        record_answer(
            machine, ledger, turn_id=q.turn_id, question_id=q.question_id,
            value="not_a_real_option", modality=Modality.TOUCH,
        )


def test_exclusive_option_clears_the_others(machine, ledger) -> None:
    """'None of these' plus a symptom is a mis-tap; the exclusive answer wins."""
    while (q := machine.next_question()) is not None and q.question_id != "ros.resp":
        machine.decline(q.question_id)
    assert q is not None
    facts = record_answer(
        machine, ledger, turn_id=q.turn_id, question_id="ros.resp",
        value=["none", "cough"], modality=Modality.TOUCH,
    )
    assert facts[0].value == ["none"]

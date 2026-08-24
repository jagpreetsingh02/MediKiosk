"""Going back and changing an answer, without corrupting what was already recorded.

The rule the whole feature rests on: **a changed answer supersedes, it never overwrites.** A
patient who says "chest" and then corrects it to "abdomen" has told the physician something —
and a system that silently replaces the first answer has destroyed it. The ledger is
append-only for exactly this reason, so Back is a navigation feature that must not become a
mutation feature.
"""

from __future__ import annotations

import pytest

from tests.helpers import tap


@pytest.fixture
def known_paths():
    from app.modules.dialogue.ontology import load_ontology

    return load_ontology().known_paths


def _first_questions(machine, count: int) -> list:
    """Walk the machine forward, answering each question, and collect what was asked."""
    asked = []
    for _ in range(count):
        question = machine.next_question()
        if question is None:
            break
        asked.append(question)
        option = question.options[0]["value"] if question.options else "something"
        tap(machine.ledger, question.path, option, question_id=question.question_id)
        machine.state.values[question.path] = option
        machine.state.cursor += 1
    return asked


def test_back_lands_on_the_previous_answered_question(machine) -> None:
    asked = _first_questions(machine, 3)
    assert len(asked) >= 2, "need at least two questions to go back over"

    target = machine.previous_answered()
    assert target == asked[-1].question_id


def test_there_is_nowhere_to_go_back_to_before_the_first_answer(machine) -> None:
    """Back must be disabled, not broken, on the first question."""
    assert machine.previous_answered() is None


def test_a_reopened_question_reports_the_answer_already_on_file(machine) -> None:
    asked = _first_questions(machine, 2)
    target = asked[-1]

    existing = machine.current_answer(target.question_id)
    assert existing is not None
    assert existing["declined"] is False
    assert existing["verbatim"], "the patient must see what they said, not a blank screen"


def test_changing_an_answer_supersedes_the_old_fact_and_keeps_it(machine, known_paths) -> None:
    """The core guarantee. Both answers survive; only one is active."""
    asked = _first_questions(machine, 2)
    target = asked[-1]
    original = machine.ledger.at_path(target.path)[0]

    assert machine.reopen(target.question_id) is True
    reasked = machine.next_question()
    assert reasked is not None and reasked.question_id == target.question_id

    replacement = (
        target.options[1]["value"] if len(target.options) > 1 else "a different answer"
    )
    tap(machine.ledger, target.path, replacement, question_id=target.question_id)

    active = machine.ledger.at_path(target.path)
    assert len(active) == 1, "exactly one answer is current"
    assert active[0].value == replacement

    everything = machine.ledger.at_path(target.path, active_only=False)
    assert len(everything) == 2, "the original answer must still be in the record"
    superseded = next(f for f in everything if f.fact_id == original.fact_id)
    assert superseded.superseded_by == active[0].fact_id
    assert superseded.value == original.value, "the old answer is kept verbatim, not edited"


def test_going_back_does_not_delete_anything(machine) -> None:
    """Reopening on its own is navigation. Nothing leaves the ledger until a new answer."""
    _first_questions(machine, 3)
    before = len(machine.ledger.facts)

    target = machine.previous_answered()
    assert target is not None
    machine.reopen(target)

    assert len(machine.ledger.facts) == before


def test_a_declined_question_can_be_gone_back_to(machine) -> None:
    """"I would rather not answer" is a decision, and a patient may change it."""
    question = machine.next_question()
    assert question is not None
    machine.decline(question.question_id)
    machine.state.cursor += 1

    assert machine.previous_answered() == question.question_id
    existing = machine.current_answer(question.question_id)
    assert existing is not None and existing["declined"] is True

    machine.reopen(question.question_id)
    assert question.question_id not in machine.state.declined, (
        "reopening must clear the decline, or the question is skipped again immediately"
    )


def test_branching_is_recalculated_after_a_changed_answer(machine) -> None:
    """A new answer that closes a branch must stop those questions being asked.

    `hpi.character` is asked for a pain complaint and skipped for a cough — but only once
    `hpi.site` is recorded, which is why both are answered here. Conditions are evaluated
    against current values on every `next_question()` call, so recalculation is a property of
    the machine rather than something Back has to remember to do. The test pins it, because
    the alternative — stale questions from a branch the patient just closed — makes a
    corrected answer worse than no correction at all.
    """
    from tests.helpers import tap as record

    complaint = machine.next_question()
    assert complaint is not None and complaint.question_id == "cc.text"
    record(machine.ledger, complaint.path, "pain", question_id=complaint.question_id)
    machine.state.cursor += 1

    site = next(q for q in _peek(machine, 6) if q.question_id == "hpi.site")
    record(machine.ledger, site.path, "chest", question_id=site.question_id)

    asked_for_pain = {q.question_id for q in _peek(machine, 14)}
    assert "hpi.character" in asked_for_pain, "a pain complaint must reach the SOCRATES branch"

    # The patient goes back and says it is a cough, not pain.
    machine.reopen(complaint.question_id)
    record(machine.ledger, complaint.path, "cough", question_id=complaint.question_id)
    machine.state.cursor += 1

    asked_for_cough = {q.question_id for q in _peek(machine, 14)}
    assert "hpi.character" not in asked_for_cough, (
        "changing the complaint to a cough must close the pain branch; if this fails the "
        "conditions are being evaluated against stale values"
    )


def _peek(machine, count: int) -> list:
    """Look at the next `count` questions without recording answers, then rewind."""
    cursor = machine.state.cursor
    seen = []
    for _ in range(count):
        question = machine.next_question()
        if question is None:
            break
        seen.append(question)
        machine.state.cursor += 1
    machine.state.cursor = cursor
    return seen

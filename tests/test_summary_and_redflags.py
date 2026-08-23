"""Phase 5 — the summary, its traceability gate, and Invariant 3."""

from __future__ import annotations

import pytest

from app.contracts.history import Demographics
from app.contracts.projection import project
from app.contracts.record import FactLedger
from app.core.errors import DeEscalationAttempt, TraceabilityError
from app.modules.summary.assemble import SummaryLine, build
from app.modules.summary.generate import generate
from app.modules.summary.prose import smooth
from app.modules.summary.traceability import enforce
from app.redflags.engine import Priority, evaluate, load_rules, raise_priority
from tests.helpers import tap

CARDIAC = [
    ("chief_complaint.text", "pain"),
    ("chief_complaint.duration", "days_1_3"),
    ("hpi.site", "chest"),
    ("hpi.onset", "sudden"),
    ("hpi.character", "pressure"),
    ("hpi.radiation", "jaw_neck"),
    ("hpi.associated", ["sweating", "breathlessness"]),
    ("hpi.severity", 9),
    ("past_medical.conditions", ["diabetes", "hypertension"]),
    ("personal_history.tobacco", "current_smoke"),
]


def _ledger(facts) -> FactLedger:
    ledger = FactLedger("s_test")
    for path, value in facts:
        tap(ledger, path, value)
    return ledger


# ------------------------------------------------------------------ Invariant 3


def test_there_is_no_priority_below_routine() -> None:
    """A missing flag is not a claim that the patient is low-priority."""
    assert [p.name for p in Priority] == ["ROUTINE", "URGENT", "IMMEDIATE"]
    assert min(Priority) is Priority.ROUTINE


def test_raise_priority_refuses_to_lower() -> None:
    assert raise_priority(Priority.ROUTINE, Priority.URGENT) is Priority.URGENT
    assert raise_priority(Priority.URGENT, Priority.URGENT) is Priority.URGENT
    with pytest.raises(DeEscalationAttempt):
        raise_priority(Priority.IMMEDIATE, Priority.URGENT)
    with pytest.raises(DeEscalationAttempt):
        raise_priority(Priority.URGENT, Priority.ROUTINE)


def test_every_rule_is_additive_only() -> None:
    for rule in load_rules().rules:
        assert rule.level in ("urgent", "immediate")


def test_a_later_evaluation_never_walks_a_session_back() -> None:
    """Fewer facts this round must not un-escalate a patient escalated earlier."""
    escalation = evaluate(FactLedger("empty"), current_priority=Priority.IMMEDIATE)
    assert escalation.priority is Priority.IMMEDIATE
    assert not escalation.flags


def test_cardiac_presentation_escalates_to_immediate() -> None:
    escalation = evaluate(_ledger(CARDIAC))
    assert escalation.priority is Priority.IMMEDIATE
    assert "RF-CARD-01" in {f.rule_id for f in escalation.flags}


@pytest.mark.parametrize(
    ("facts", "expected_rule"),
    [
        ([("review_of_systems.neurological", ["facial_droop"])], "RF-NEURO-01"),
        ([("review_of_systems.neurological", ["thunderclap"])], "RF-NEURO-02"),
        ([("review_of_systems.neurological", ["neck_stiff"])], "RF-NEURO-03"),
        ([("review_of_systems.gastrointestinal", ["melaena"])], "RF-BLEED-01"),
        ([("review_of_systems.gastrointestinal", ["haematemesis"])], "RF-BLEED-01"),
        ([("review_of_systems.respiratory", ["haemoptysis"])], "RF-BLEED-02"),
        ([("hpi.associated", ["breathlessness"])], "RF-RESP-01"),
        ([("drug_allergy.allergy_reaction", "collapse")], "RF-SYS-02"),
        ([("review_of_systems.genitourinary", ["retention"])], "RF-SYS-05"),
        (
            [("personal_history.pregnancy", "maybe"), ("hpi.site", "abdomen")],
            "RF-OBS-01",
        ),
        (
            [
                ("review_of_systems.respiratory", ["cough_3wk", "night_sweats"]),
            ],
            "RF-RESP-02",
        ),
    ],
)
def test_each_emergency_family_fires(facts, expected_rule) -> None:
    """An `any:` clause bug once made every one of these silently never fire."""
    escalation = evaluate(_ledger(facts))
    assert expected_rule in {f.rule_id for f in escalation.flags}, (
        f"{expected_rule} did not fire on {facts}"
    )


def test_a_routine_presentation_fires_nothing() -> None:
    escalation = evaluate(_ledger([("hpi.site", "joints"), ("hpi.severity", 3)]))
    assert escalation.priority is Priority.ROUTINE
    assert not escalation.flags


def test_every_proposal_is_logged_fired_or_not() -> None:
    escalation = evaluate(_ledger(CARDIAC))
    assert len(escalation.proposals) == len(load_rules().rules)
    assert any(p.fired for p in escalation.proposals)
    assert any(not p.fired for p in escalation.proposals)


def test_llm_cannot_invent_an_emergency() -> None:
    escalation = evaluate(
        _ledger([("hpi.site", "joints")]),
        llm_candidates=[{"rule_id": "RF-MADE-UP", "reason": "vibes"}],
    )
    assert not escalation.flags
    invented = next(p for p in escalation.proposals if p.rule_id == "RF-MADE-UP")
    assert not invented.fired and "cannot invent" in (invented.discarded_because or "")


def test_llm_cannot_suppress_an_emergency() -> None:
    """The model is not consulted about whether a fired rule should stand."""
    escalation = evaluate(
        _ledger(CARDIAC),
        llm_candidates=[{"rule_id": "RF-CARD-01", "reason": "probably just reflux"}],
    )
    assert escalation.priority is Priority.IMMEDIATE
    assert "RF-CARD-01" in {f.rule_id for f in escalation.flags}


def test_llm_proposal_the_rules_reject_is_logged_for_review() -> None:
    escalation = evaluate(
        _ledger([("hpi.site", "joints")]),
        llm_candidates=[{"rule_id": "RF-CARD-01", "reason": "patient seemed short of breath"}],
    )
    proposal = next(
        p for p in escalation.proposals if p.rule_id == "RF-CARD-01" and p.proposed_by == "llm"
    )
    assert not proposal.fired
    assert "clinician makes to" in (proposal.discarded_because or "")


def test_flags_name_the_facts_that_triggered_them() -> None:
    ledger = _ledger(CARDIAC)
    escalation = evaluate(ledger)
    known = {f.fact_id for f in ledger.facts}
    for flag in escalation.flags:
        assert flag.triggering_fact_ids
        assert set(flag.triggering_fact_ids) <= known


# ------------------------------------------------------------------ summary


def _history(ledger: FactLedger):
    return project(ledger, demographics=Demographics(age_years=64, gender="female"))


def test_summary_is_a_draft_until_a_physician_commits() -> None:
    ledger = _ledger(CARDIAC)
    result = generate(_history(ledger), ledger, escalation=evaluate(ledger))
    assert result.summary.status == "draft"
    assert "DRAFT" in result.to_dict()["notice"]


def test_summary_carries_no_assessment() -> None:
    ledger = _ledger(CARDIAC)
    payload = generate(_history(ledger), ledger, escalation=evaluate(ledger)).to_dict()
    text = " ".join(
        line["text"].casefold() for section in payload["sections"] for line in section["lines"]
    )
    for banned in ("likely", "consistent with", "suggestive of", "probable diagnosis", "rule out"):
        assert banned not in text, f"summary contains assessment language: {banned!r}"


def test_every_fact_line_resolves_to_a_recorded_fact() -> None:
    ledger = _ledger(CARDIAC)
    result = generate(_history(ledger), ledger, escalation=evaluate(ledger))
    assert result.traceability.ok
    known = {f.fact_id for f in ledger.facts}
    for line in result.summary.fact_lines():
        assert line.fact_ids
        assert set(line.fact_ids) <= known


def test_traceability_rejects_a_line_with_no_source() -> None:
    ledger = _ledger(CARDIAC)
    summary = build(_history(ledger))
    summary.sections[1].lines.append(SummaryLine(text="Complaint: fever", fact_ids=[]))
    with pytest.raises(TraceabilityError, match="no source"):
        enforce(summary, ledger)


def test_traceability_rejects_a_dangling_fact_id() -> None:
    ledger = _ledger(CARDIAC)
    summary = build(_history(ledger))
    summary.sections[1].lines.append(
        SummaryLine(text="Complaint: pain", fact_ids=["fact_doesnotexist"])
    )
    with pytest.raises(TraceabilityError, match="not in the ledger"):
        enforce(summary, ledger)


def test_traceability_rejects_a_model_invented_word() -> None:
    """The hallucination detector. If this stops working the whole guarantee is theatre."""
    ledger = _ledger(CARDIAC)
    summary = build(_history(ledger))
    real_id = ledger.facts[0].fact_id
    summary.sections[1].lines.append(
        SummaryLine(
            text="Complaint: crushing retrosternal pain radiating ischaemically",
            fact_ids=[real_id],
        )
    )
    with pytest.raises(TraceabilityError, match="not supported by any recorded fact"):
        enforce(summary, ledger)


def test_generation_fails_completely_rather_than_partially() -> None:
    """No half-verified summary: a physician cannot tell which half was checked."""
    ledger = _ledger(CARDIAC)
    summary = build(_history(ledger))
    summary.sections[1].lines.append(SummaryLine(text="Complaint: pericarditis", fact_ids=[]))
    with pytest.raises(TraceabilityError):
        enforce(summary, ledger)


def test_absences_are_printed_not_hidden() -> None:
    ledger = _ledger([("hpi.site", "chest")])
    result = generate(_history(ledger), ledger)
    gaps = next(s for s in result.summary.sections if s.section_id == "gaps")
    assert any("Not asked" in line.text for line in gaps.lines)


def test_no_flags_says_so_explicitly() -> None:
    """A blank escalation section reads as 'nothing found', which is a claim we do not make."""
    ledger = _ledger([("hpi.site", "joints")])
    result = generate(_history(ledger), ledger, escalation=evaluate(ledger))
    escalation = next(s for s in result.summary.sections if s.section_id == "red_flags")
    assert "not a statement" in escalation.lines[0].text


def test_unmapped_problems_are_labelled_not_hidden() -> None:
    from app.contracts.history import ProblemEntry, Slot, SlotStatus

    ledger = _ledger(CARDIAC)
    history = _history(ledger)
    history.problems.append(
        ProblemEntry(
            entry_id="p1",
            reported_term=Slot(
                path="problems[0].reported_term",
                value="pain",
                status=SlotStatus.RECORDED,
                fact_ids=[ledger.facts[0].fact_id],
            ),
            reported_year=Slot(path="problems[0].reported_year"),
            coding=None,
            unmapped=True,
        )
    )
    summary = build(history)
    text = " ".join(line.text for s in summary.sections for line in s.lines)
    assert "[unmapped]" in text


def test_click_to_source_resolves_every_line() -> None:
    ledger = _ledger(CARDIAC)
    result = generate(_history(ledger), ledger, escalation=evaluate(ledger))
    sourced = [line for line in result.sourced_lines if line["kind"] == "fact"]
    assert sourced
    for line in sourced:
        assert line["sources"], f"no source resolved for: {line['text']}"
        for source in line["sources"]:
            assert source["verbatim"]
            assert source["tier"] in ("stated", "confirmed", "document")


def test_offline_backend_keeps_bullets_rather_than_faking_prose() -> None:
    ledger = _ledger(CARDIAC)
    summary = build(_history(ledger))
    _, outcomes = smooth(summary, ledger)
    assert outcomes and not outcomes[0].applied
    assert "offline backend" in (outcomes[0].reason or "")


def test_smoothing_that_invents_a_word_is_discarded(monkeypatch) -> None:
    """The model gets one attempt and no negotiation."""
    from app.llm.protocol import LLMResponse

    class Inventive:
        name, version, offline = "stub", "t", False

        def complete(self, *, system, user, schema_hint):
            return LLMResponse(
                text='{"prose": "Crushing retrosternal ischaemic pain with diaphoresis."}',
                model_name=self.name,
                model_version=self.version,
                prompt="p",
                offline=False,
            )

    import app.modules.summary.prose as prose_module

    monkeypatch.setattr(prose_module, "get_llm", lambda: Inventive())
    ledger = _ledger(CARDIAC)
    summary = build(_history(ledger))
    before = [line.text for line in summary.sections[2].lines]
    summary, outcomes = smooth(summary, ledger)
    hpi = next(o for o in outcomes if o.section_id == "hpi")
    assert not hpi.applied
    assert hpi.unsupported_tokens
    assert [line.text for line in summary.sections[2].lines] == before


def test_smoothing_that_stays_within_the_facts_is_applied(monkeypatch) -> None:
    from app.llm.protocol import LLMResponse

    class Faithful:
        name, version, offline = "stub", "t", False

        def complete(self, *, system, user, schema_hint):
            return LLMResponse(
                text=('{"prose": "Site: Chest. Onset: All at once, suddenly. Severity 9 of 10."}'),
                model_name=self.name,
                model_version=self.version,
                prompt="p",
                offline=False,
            )

    import app.modules.summary.prose as prose_module

    monkeypatch.setattr(prose_module, "get_llm", lambda: Faithful())
    ledger = _ledger(CARDIAC)
    summary = build(_history(ledger))
    summary, outcomes = smooth(summary, ledger)
    hpi = next(o for o in outcomes if o.section_id == "hpi")
    assert hpi.applied
    prose_line = next(line for line in summary.sections[2].lines if line.kind == "fact")
    assert prose_line.fact_ids, "smoothed prose must inherit every fact id it summarises"

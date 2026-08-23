"""The eval harness runs as part of the test suite, in strict mode.

A metric that is only checked when somebody remembers to run a script is not a guarantee.
These tests make a regression in hallucination rate or red-flag sensitivity fail the build.
"""
from __future__ import annotations

import pytest

from eval.runner import Report, load_scripts, run_script


@pytest.fixture(scope="module")
def dev_report() -> Report:
    return Report([run_script(s) for s in load_scripts()])


@pytest.fixture(scope="module")
def holdout_report() -> Report:
    return Report([run_script(s) for s in load_scripts(holdout=True)])


def test_the_gold_set_is_the_size_it_claims() -> None:
    assert len(load_scripts()) == 50
    assert len(load_scripts(holdout=True)) >= 12


def test_gold_set_covers_every_difficulty_class() -> None:
    classes = {s.difficulty for s in load_scripts()}
    assert classes == {
        "emergency", "plain", "low_literacy", "rambling", "contradictory", "mixed"
    }


def test_gold_set_includes_non_english_scripts() -> None:
    assert sum(1 for s in load_scripts() if s.language != "en") >= 8


def test_every_emergency_script_names_specific_rules() -> None:
    """'Should detect an emergency' is not scoreable. Every one must name rule ids."""
    for script in load_scripts() + load_scripts(holdout=True):
        if script.expected_priority in ("urgent", "immediate"):
            assert script.expected_red_flags, f"{script.id} names no expected rule"


def test_hallucination_rate_is_zero(dev_report: Report) -> None:
    assert dev_report.hallucination_rate == 0.0


def test_no_unsourced_summary_claims(dev_report: Report) -> None:
    assert dev_report.unsourced_summary_claims == 0


def test_red_flag_sensitivity_meets_target(dev_report: Report) -> None:
    assert dev_report.red_flag_sensitivity >= 0.98, (
        f"missed: {[(r.script_id, r.missed_flags) for r in dev_report.results if r.missed_flags]}"
    )


def test_no_priority_under_calls(dev_report: Report) -> None:
    """Escalating less than the gold script requires is the dangerous direction."""
    assert not dev_report.priority_under_calls, [
        r.script_id for r in dev_report.priority_under_calls
    ]


def test_no_forbidden_flags_fire(dev_report: Report) -> None:
    """A rule that fires on a routine patient is a rule nobody will trust."""
    assert not dev_report.forbidden_fired, [
        (r.script_id, r.forbidden_fired) for r in dev_report.forbidden_fired
    ]


def test_every_script_completes(dev_report: Report) -> None:
    assert not dev_report.failures(), [
        (r.script_id, r.error) for r in dev_report.failures()
    ]


def test_declines_are_absences_never_values(dev_report: Report) -> None:
    offenders = [r.script_id for r in dev_report.results if not r.declined_ok]
    assert not offenders, f"declined questions recorded a value in: {offenders}"


# ------------------------------------------------------------------ held-out


def test_safety_metrics_hold_on_unseen_phrasing(holdout_report: Report) -> None:
    """The load-bearing claim of docs/EVALUATION.md.

    Extraction degrades on phrasing the lexicon has not seen — that is expected and measured.
    The safety guarantees must NOT degrade, because they do not come from the extractor.
    """
    assert holdout_report.hallucination_rate == 0.0
    assert holdout_report.unsourced_summary_claims == 0
    assert holdout_report.red_flag_sensitivity >= 0.98
    assert not holdout_report.priority_under_calls
    assert not holdout_report.forbidden_fired


def test_holdout_extraction_is_reported_not_enforced(holdout_report: Report) -> None:
    """Held-out extraction is allowed to be imperfect. Pinning it would invite tuning.

    The floor is loose on purpose: it catches a catastrophic regression without creating a
    number anybody is tempted to optimise against.
    """
    assert holdout_report.extraction_accuracy >= 0.70


def test_total_asr_failure_still_completes_the_history(holdout_report: Report) -> None:
    """h12: every spoken answer unintelligible. Dual-mode input must carry the session."""
    result = next(r for r in holdout_report.results if r.script_id.startswith("h12"))
    assert result.degraded_turns >= 3, "the ASR failures did not degrade to touch"
    assert result.ok
    assert result.matched_slots == result.expected_slots

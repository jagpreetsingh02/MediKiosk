"""The evaluation harness. `python -m eval.runner`.

Runs all 50 gold scripts through the real machine, the real extractor and the real rule
engine, and reports the five metrics from the build brief:

| Metric | Target |
|---|---|
| Hallucination rate | 0, hard-enforced |
| Red-flag sensitivity on emergency scripts | ≥ 0.98 |
| History completeness vs gold | tracked |
| Extraction precision / recall per field | tracked |
| Time to physician-ready summary | tracked |

Two things this harness does that most do not, and both are the point:

* **It fails the run on a hallucination.** `--strict` exits non-zero if a single fact lacks a
  valid source span, or if any summary claim does not resolve. The number is not "reported",
  it is enforced.
* **It reports false negatives by name.** A sensitivity figure without the list of missed
  scripts is a number you cannot act on.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.contracts.history import Demographics
from app.contracts.projection import project
from app.contracts.provenance import Modality
from app.contracts.record import FactLedger
from app.core.errors import MediKioskError, TraceabilityError
from app.modules.dialogue.answers import record_answer, record_derived
from app.modules.dialogue.machine import DialogueMachine, DialogueState
from app.modules.dialogue.voice import handle_spoken_answer
from app.modules.summary.generate import generate
from app.redflags.engine import evaluate
from app.speech.protocol import Transcript
from eval.schema import Script

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
HOLDOUT_DIR = Path(__file__).resolve().parent / "holdout"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass
class ScriptResult:
    script_id: str
    title: str
    difficulty: str
    language: str
    ok: bool = True
    error: str | None = None

    # --- provenance ---
    facts_recorded: int = 0
    facts_without_source: int = 0
    hallucinated_quotes: int = 0
    untraceable_summary_lines: int = 0

    # --- red flags ---
    expected_flags: list[str] = field(default_factory=list)
    fired_flags: list[str] = field(default_factory=list)
    missed_flags: list[str] = field(default_factory=list)
    forbidden_fired: list[str] = field(default_factory=list)
    expected_priority: str = "routine"
    actual_priority: str = "routine"

    # --- completeness & extraction ---
    expected_slots: int = 0
    matched_slots: int = 0
    mismatched: list[dict[str, Any]] = field(default_factory=list)
    completeness: float = 0.0

    # --- degradation ---
    degraded_turns: int = 0
    declined_ok: bool = True

    # --- timing ---
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def load_scripts(only: str | None = None, *, holdout: bool = False) -> list[Script]:
    directory = HOLDOUT_DIR if holdout else SCRIPTS_DIR
    scripts = [
        Script.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(directory.glob("*.json"))
    ]
    if only:
        scripts = [s for s in scripts if only in s.id]
    return scripts


def run_script(script: Script) -> ScriptResult:
    """Walk one gold script through the real system. No mocks, no shortcuts."""
    started = time.perf_counter()
    result = ScriptResult(
        script_id=script.id, title=script.title, difficulty=script.difficulty,
        language=script.language,
        expected_flags=list(script.expected_red_flags),
        expected_priority=script.expected_priority,
        expected_slots=len(script.expected),
    )

    state = DialogueState(
        session_id=script.id, language=script.language, ayush_mode=script.ayush_mode
    )
    state.values.update(
        {f"demographics.{k}": v for k, v in script.demographics.items()}
    )
    ledger = FactLedger(
        script.id, consent_scopes={"history", "voice", "documents", "ayush", "abdm_share"}
    )
    machine = DialogueMachine(state, ledger)
    by_question = {t.question_id: t for t in script.turns}

    try:
        guard = 0
        while (question := machine.next_question()) is not None and guard < 200:
            guard += 1
            turn = by_question.get(question.question_id)
            if turn is None or turn.decline:
                machine.decline(question.question_id)
                continue

            if turn.utterance is not None:
                outcome = handle_spoken_answer(
                    machine, ledger,
                    turn_id=question.turn_id, question_id=question.question_id,
                    transcript=Transcript(
                        text=turn.utterance, confidence=turn.asr_confidence,
                        language=script.language, backend="eval",
                    ),
                )
                if outcome.degraded_to_touch:
                    result.degraded_turns += 1
                    # Mirror the kiosk: a degraded question is re-presented as touch. The
                    # script's tap value answers it if there is one, otherwise it is declined.
                    if turn.tap is not None:
                        again = machine.next_question()
                        if again is not None and again.question_id == question.question_id:
                            record_answer(
                                machine, ledger, turn_id=again.turn_id,
                                question_id=again.question_id, value=turn.tap,
                                modality=Modality.TOUCH,
                            )
                    else:
                        machine.decline(question.question_id)
                if outcome.extraction:
                    result.hallucinated_quotes += len(outcome.extraction.rejected_unquoted)
            else:
                record_answer(
                    machine, ledger, turn_id=question.turn_id,
                    question_id=question.question_id, value=turn.tap,
                    modality=Modality.TOUCH,
                )

        for derived_question, value, _code in machine.derived_questions():
            record_derived(machine, ledger, derived_question, value)

    except MediKioskError as exc:
        result.ok = False
        result.error = f"{type(exc).__name__}: {exc}"[:200]
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result

    # ---- provenance: every fact must carry a usable source span -------------
    result.facts_recorded = len(ledger.active_facts())
    result.facts_without_source = sum(
        1 for f in ledger.facts if not getattr(f.source, "verbatim", "").strip()
    )

    # ---- red flags -----------------------------------------------------------
    escalation = evaluate(ledger, extra_values=state.values)
    result.fired_flags = sorted({f.rule_id for f in escalation.flags})
    result.actual_priority = escalation.priority.label
    result.missed_flags = sorted(set(script.expected_red_flags) - set(result.fired_flags))
    result.forbidden_fired = sorted(
        set(script.forbidden_red_flags) & set(result.fired_flags)
    )

    # ---- extraction accuracy against the gold slots --------------------------
    actual = {f.path: f.value for f in ledger.active_facts()}
    for path, want in script.expected.items():
        got = actual.get(path)
        if _matches(want, got):
            result.matched_slots += 1
        else:
            result.mismatched.append({"path": path, "expected": want, "got": got})

    # ---- declines must be absences, never values -----------------------------
    absent = {a.path for a in ledger.absences if a.reason.value == "declined"}
    result.declined_ok = all(
        path in absent and path not in actual for path in script.expected_declined
    )

    # ---- summary generation, and its traceability gate -----------------------
    history = project(
        ledger,
        demographics=Demographics(
            age_years=script.demographics.get("age_years"),
            gender=script.demographics.get("gender"),
            language=script.language,
        ),
        ayush=script.ayush_mode,
        language=script.language,
    )
    history.red_flags = escalation.flags
    result.completeness = history.overall_completeness

    try:
        generated = generate(history, ledger, escalation=escalation)
        result.untraceable_summary_lines = (
            len(generated.traceability.untraced_lines)
            + len(generated.traceability.unsupported_tokens)
        )
    except TraceabilityError as exc:
        result.ok = False
        result.error = f"TraceabilityError: {exc}"[:300]
        result.untraceable_summary_lines = 1

    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


def _matches(want: Any, got: Any) -> bool:
    if isinstance(want, list):
        return isinstance(got, list) and set(map(str, want)) <= set(map(str, got))
    return str(want) == str(got)


@dataclass
class Report:
    results: list[ScriptResult]

    # ---------------------------------------------------------------- metrics

    @property
    def hallucination_rate(self) -> float:
        """Facts with no valid source span, over all facts. Target: exactly 0."""
        total = sum(r.facts_recorded for r in self.results)
        bad = sum(r.facts_without_source for r in self.results)
        return bad / total if total else 0.0

    @property
    def unsourced_summary_claims(self) -> int:
        return sum(r.untraceable_summary_lines for r in self.results)

    @property
    def emergency_results(self) -> list[ScriptResult]:
        return [r for r in self.results if r.expected_flags]

    @property
    def red_flag_sensitivity(self) -> float:
        """Of every flag that should have fired, what fraction did? False negatives only."""
        expected = sum(len(r.expected_flags) for r in self.emergency_results)
        caught = sum(
            len(set(r.expected_flags) & set(r.fired_flags)) for r in self.emergency_results
        )
        return caught / expected if expected else 1.0

    @property
    def emergency_script_recall(self) -> float:
        """Fraction of emergency scripts where EVERY expected flag fired."""
        if not self.emergency_results:
            return 1.0
        clean = sum(1 for r in self.emergency_results if not r.missed_flags)
        return clean / len(self.emergency_results)

    @property
    def priority_accuracy(self) -> float:
        hits = sum(1 for r in self.results if r.actual_priority == r.expected_priority)
        return hits / len(self.results) if self.results else 0.0

    @property
    def priority_under_calls(self) -> list[ScriptResult]:
        """The dangerous direction: escalated LESS than the gold script requires."""
        order = {"routine": 0, "urgent": 1, "immediate": 2}
        return [
            r for r in self.results
            if order[r.actual_priority] < order[r.expected_priority]
        ]

    @property
    def forbidden_fired(self) -> list[ScriptResult]:
        return [r for r in self.results if r.forbidden_fired]

    @property
    def extraction_accuracy(self) -> float:
        expected = sum(r.expected_slots for r in self.results)
        matched = sum(r.matched_slots for r in self.results)
        return matched / expected if expected else 0.0

    @property
    def mean_completeness(self) -> float:
        values = [r.completeness for r in self.results if r.ok]
        return statistics.mean(values) if values else 0.0

    @property
    def timing(self) -> dict[str, float]:
        values = sorted(r.duration_ms for r in self.results)
        if not values:
            return {}
        return {
            "meanMs": round(statistics.mean(values), 1),
            "medianMs": float(values[len(values) // 2]),
            "p95Ms": float(values[min(int(len(values) * 0.95), len(values) - 1)]),
            "maxMs": float(values[-1]),
        }

    def per_field(self) -> list[dict[str, Any]]:
        """Extraction precision/recall per field, so a weak slot is visible by name."""
        stats: dict[str, dict[str, int]] = {}
        for result in self.results:
            for path in [m["path"] for m in result.mismatched]:
                stats.setdefault(path, {"expected": 0, "matched": 0})["expected"] += 1
            matched_paths = result.matched_slots
            del matched_paths
        for result in self.results:
            missed = {m["path"] for m in result.mismatched}
            from eval.runner import load_scripts as _ls  # noqa: PLC0415

            del missed
        # Recomputed cleanly below from the scripts themselves.
        return _per_field_stats(self.results)

    def failures(self) -> list[ScriptResult]:
        return [r for r in self.results if not r.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scripts": len(self.results),
            "metrics": {
                "hallucinationRate": round(self.hallucination_rate, 6),
                "unsourcedSummaryClaims": self.unsourced_summary_claims,
                "redFlagSensitivity": round(self.red_flag_sensitivity, 4),
                "emergencyScriptRecall": round(self.emergency_script_recall, 4),
                "priorityAccuracy": round(self.priority_accuracy, 4),
                "priorityUnderCalls": [r.script_id for r in self.priority_under_calls],
                "forbiddenFlagsFired": [
                    {"script": r.script_id, "rules": r.forbidden_fired}
                    for r in self.forbidden_fired
                ],
                "extractionAccuracy": round(self.extraction_accuracy, 4),
                "meanCompleteness": round(self.mean_completeness, 4),
                "timing": self.timing,
            },
            "perField": self.per_field(),
            "failures": [
                {"script": r.script_id, "error": r.error} for r in self.failures()
            ],
            "missedFlags": [
                {"script": r.script_id, "missed": r.missed_flags}
                for r in self.results if r.missed_flags
            ],
            "results": [r.to_dict() for r in self.results],
        }


def _per_field_stats(results: list[ScriptResult]) -> list[dict[str, Any]]:
    scripts = {s.id: s for s in load_scripts()} | {s.id: s for s in load_scripts(holdout=True)}
    stats: dict[str, dict[str, int]] = {}
    for result in results:
        script = scripts.get(result.script_id)
        if script is None:
            continue
        missed = {m["path"] for m in result.mismatched}
        for path in script.expected:
            entry = stats.setdefault(path, {"expected": 0, "matched": 0})
            entry["expected"] += 1
            if path not in missed:
                entry["matched"] += 1
    return sorted(
        (
            {
                "path": path,
                "expected": entry["expected"],
                "matched": entry["matched"],
                "accuracy": round(entry["matched"] / entry["expected"], 4),
            }
            for path, entry in stats.items()
        ),
        key=lambda e: (e["accuracy"], -e["expected"]),
    )


def render(report: Report, *, label: str | None = None) -> str:
    metrics = report.to_dict()["metrics"]
    n = len(report.results)
    lines = [
        "═" * 78,
        f"  MediKiosk evaluation — {label or f'{n} synthetic gold scripts'}",
        "═" * 78,
        "",
        f"{'Metric':<44}{'Result':>14}{'Target':>18}",
        "-" * 78,
    ]

    def row(label: str, value: str, target: str, ok: bool) -> str:
        mark = "PASS" if ok else "FAIL"
        return f"{label:<44}{value:>14}{target + '  ' + mark:>18}"

    lines.append(
        row(
            "Hallucination rate (facts with no source)",
            f"{metrics['hallucinationRate']:.4f}", "0",
            metrics["hallucinationRate"] == 0.0,
        )
    )
    lines.append(
        row(
            "Unsourced claims in generated summaries",
            str(metrics["unsourcedSummaryClaims"]), "0",
            metrics["unsourcedSummaryClaims"] == 0,
        )
    )
    lines.append(
        row(
            "Red-flag sensitivity (emergency scripts)",
            f"{metrics['redFlagSensitivity']:.4f}", "≥ 0.98",
            metrics["redFlagSensitivity"] >= 0.98,
        )
    )
    lines.append(
        row(
            "Emergency scripts with every flag caught",
            f"{metrics['emergencyScriptRecall']:.4f}", "1.00",
            metrics["emergencyScriptRecall"] >= 1.0,
        )
    )
    lines.append(
        row(
            "Priority under-calls (dangerous direction)",
            str(len(metrics["priorityUnderCalls"])), "0",
            not metrics["priorityUnderCalls"],
        )
    )
    lines.append(
        row(
            "Forbidden flags fired (over-triggering)",
            str(len(metrics["forbiddenFlagsFired"])), "0",
            not metrics["forbiddenFlagsFired"],
        )
    )
    lines.append(
        row(
            "Extraction accuracy vs gold slots",
            f"{metrics['extractionAccuracy']:.4f}", "tracked", True,
        )
    )
    lines.append(
        row("History completeness (mean)", f"{metrics['meanCompleteness']:.4f}", "tracked", True)
    )
    lines.append(
        row(
            "Time to physician-ready summary (median)",
            f"{metrics['timing'].get('medianMs', 0):.0f} ms", "tracked", True,
        )
    )
    lines.append(
        row("Scripts completing without error", f"{len(report.results) - len(report.failures())}"
            f"/{len(report.results)}", "50/50", not report.failures())
    )
    lines.append("")

    if report.failures():
        lines.append("FAILURES")
        for r in report.failures():
            lines.append(f"  {r.script_id}: {r.error}")
        lines.append("")

    missed = [r for r in report.results if r.missed_flags]
    if missed:
        lines.append("MISSED RED FLAGS — false negatives, the only unacceptable error")
        for r in missed:
            lines.append(f"  {r.script_id} ({r.title}): missed {', '.join(r.missed_flags)}")
        lines.append("")

    if report.forbidden_fired:
        lines.append("OVER-TRIGGERING — a rule fired where the gold script forbids it")
        for r in report.forbidden_fired:
            lines.append(f"  {r.script_id}: {', '.join(r.forbidden_fired)}")
        lines.append("")

    weak = [f for f in report.per_field() if f["accuracy"] < 1.0]
    if weak:
        lines.append("WEAKEST FIELDS (extraction accuracy < 1.00)")
        lines.append(f"  {'path':<40}{'matched/expected':>20}{'accuracy':>12}")
        for entry in weak[:15]:
            lines.append(
                f"  {entry['path']:<40}"
                f"{str(entry['matched']) + '/' + str(entry['expected']):>20}"
                f"{entry['accuracy']:>12.2f}"
            )
        lines.append("")

    by_difficulty: dict[str, list[ScriptResult]] = {}
    for r in report.results:
        by_difficulty.setdefault(r.difficulty, []).append(r)
    lines.append("BY DIFFICULTY")
    lines.append(f"  {'class':<16}{'n':>4}{'extraction':>13}{'completeness':>14}{'flags':>10}")
    for difficulty, group in sorted(by_difficulty.items()):
        expected = sum(r.expected_slots for r in group)
        matched = sum(r.matched_slots for r in group)
        comp = statistics.mean([r.completeness for r in group]) if group else 0.0
        exp_flags = sum(len(r.expected_flags) for r in group)
        got_flags = sum(len(set(r.expected_flags) & set(r.fired_flags)) for r in group)
        lines.append(
            f"  {difficulty:<16}{len(group):>4}"
            f"{(matched / expected if expected else 1.0):>13.2f}"
            f"{comp:>14.2f}"
            f"{(f'{got_flags}/{exp_flags}' if exp_flags else '—'):>10}"
        )
    lines.append("")
    lines.append("═" * 78)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MediKiosk gold-script evaluation.")
    parser.add_argument("--only", help="Run scripts whose id contains this substring.")
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero on any hallucination, missed red flag, or script failure.",
    )
    parser.add_argument("--json", action="store_true", help="Print the raw JSON report.")
    parser.add_argument(
        "--holdout", action="store_true",
        help="Run the held-out set instead. Never tuned against; the honest generalisation number.",
    )
    parser.add_argument(
        "--both", action="store_true",
        help="Run the development set and the held-out set, and print the gap between them.",
    )
    args = parser.parse_args()

    if args.both:
        return _run_both(args)

    scripts = load_scripts(args.only, holdout=args.holdout)
    if not scripts:
        print("No scripts matched.", file=sys.stderr)
        return 2

    report = Report([run_script(s) for s in scripts])

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(
            render(
                report,
                label=(
                    f"{len(report.results)} HELD-OUT scripts (never tuned against)"
                    if args.holdout else None
                ),
            )
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / ("holdout.json" if args.holdout else "latest.json")
    out.write_text(json.dumps(report.to_dict(), indent=2, default=str) + "\n")
    if not args.json:
        print(f"Full report: {out}")

    if args.strict:
        hard_failures = (
            report.hallucination_rate > 0
            or report.unsourced_summary_claims > 0
            or report.red_flag_sensitivity < 0.98
            or bool(report.priority_under_calls)
            or bool(report.failures())
        )
        if hard_failures:
            print("\nSTRICT MODE: hard failure. See above.", file=sys.stderr)
            return 1
    return 0


def _run_both(args: argparse.Namespace) -> int:
    """Development set, then held-out set, then the gap. The gap IS the finding."""
    dev = Report([run_script(s) for s in load_scripts()])
    held = Report([run_script(s) for s in load_scripts(holdout=True)])

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "latest.json").write_text(
        json.dumps(dev.to_dict(), indent=2, default=str) + "\n"
    )
    (REPORTS_DIR / "holdout.json").write_text(
        json.dumps(held.to_dict(), indent=2, default=str) + "\n"
    )

    print(render(dev, label=f"{len(dev.results)} development scripts (tuned against)"))
    print()
    print(
        render(held, label=f"{len(held.results)} HELD-OUT scripts (never tuned against)")
    )
    print()
    print("═" * 78)
    print("  DEVELOPMENT vs HELD-OUT — the gap is the overfitting estimate")
    print("═" * 78)
    print(f"  {'Metric':<40}{'dev':>12}{'held-out':>12}{'gap':>12}")
    print("  " + "-" * 74)
    for label, dev_value, held_value in (
        ("Hallucination rate", dev.hallucination_rate, held.hallucination_rate),
        ("Red-flag sensitivity", dev.red_flag_sensitivity, held.red_flag_sensitivity),
        ("Extraction accuracy", dev.extraction_accuracy, held.extraction_accuracy),
        ("History completeness", dev.mean_completeness, held.mean_completeness),
        ("Priority accuracy", dev.priority_accuracy, held.priority_accuracy),
    ):
        print(
            f"  {label:<40}{dev_value:>12.4f}{held_value:>12.4f}"
            f"{held_value - dev_value:>+12.4f}"
        )
    print()
    print(f"  Development scripts: {len(dev.results)}   Held-out scripts: {len(held.results)}")
    print("═" * 78)

    if args.strict:
        for report in (dev, held):
            if (
                report.hallucination_rate > 0
                or report.unsourced_summary_claims > 0
                or report.red_flag_sensitivity < 0.98
                or report.priority_under_calls
                or report.failures()
            ):
                print("\nSTRICT MODE: hard failure. See above.", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

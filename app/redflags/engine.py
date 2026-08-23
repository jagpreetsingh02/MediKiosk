"""⛔ INVARIANT 3 — red flags escalate, never de-escalate.

The rules are in `data/ontology/redflags.yaml`. This module evaluates them and nothing else.
Three structural guarantees, each enforced here rather than remembered:

1. **There is no de-escalation.** `Priority` has three members and `raise_priority()` is the
   only mutator; it takes the max and refuses to go down, raising `DeEscalationAttempt` if
   asked. There is no `lower_priority`, no `clear_flags`, and no "low priority" level — the
   *absence* of a flag is not a statement about the patient.

2. **The LLM may propose; only the rules decide.** `evaluate()` takes an optional list of LLM
   candidates. Each is matched against a real rule id and re-evaluated by that rule's own
   deterministic conditions. A candidate naming an unknown rule, or one whose rule does not
   actually fire on the recorded facts, is logged and discarded. A model cannot invent an
   emergency, and — more importantly — cannot suppress one.

3. **Every proposal is logged, fired or not.** Missed escalations are the only unacceptable
   error, so the record of what was considered and rejected is the thing that makes a miss
   investigable afterwards.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.contracts.history import RedFlag, api_dump
from app.contracts.record import FactLedger
from app.core.config import settings
from app.core.errors import DeEscalationAttempt, ValidationError
from app.core.logging import get_logger
from app.modules.dialogue.ontology import Condition, evaluate_condition

log = get_logger(__name__)


class Priority(IntEnum):
    """Ordered so `max()` is the escalation operator. There is deliberately no level below
    ROUTINE: MediKiosk never asserts that a patient is low-priority."""

    ROUTINE = 0
    URGENT = 1
    IMMEDIATE = 2

    @property
    def label(self) -> str:
        return self.name.casefold()

    @classmethod
    def parse(cls, value: str | None) -> Priority:
        if not value:
            return cls.ROUTINE
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            raise ValidationError(f"{value!r} is not a priority level.") from exc


def raise_priority(current: Priority | str, proposed: Priority | str) -> Priority:
    """The ONLY way a session's priority changes. Monotonically non-decreasing, by construction."""
    now = current if isinstance(current, Priority) else Priority.parse(current)
    want = proposed if isinstance(proposed, Priority) else Priority.parse(proposed)
    if want < now:
        raise DeEscalationAttempt(
            f"Refusing to move priority from {now.label} down to {want.label}. Red-flag "
            "detection is additive: it can move a patient up the queue and can never move "
            "one down."
        )
    return max(now, want)


class RuleClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: list[Condition] | None = None


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    #: Only two values exist. There is no schema slot for a de-escalating rule.
    level: str = Field(pattern="^(urgent|immediate)$")
    rationale: str
    all: list[Condition] | None = None
    any: list[RuleClause] | None = None

    def priority(self) -> Priority:
        return Priority.parse(self.level)

    def fires(self, values: dict[str, Any]) -> bool:
        if self.all is not None:
            return all(evaluate_condition(c, values) for c in self.all)
        if self.any is not None:
            for clause in self.any:
                conditions = clause.all
                if conditions and all(evaluate_condition(c, values) for c in conditions):
                    return True
        return False

    def matching_paths(self, values: dict[str, Any]) -> list[str]:
        """Which recorded facts caused this to fire. Drives the triggering_fact_ids list."""
        clauses: list[Condition] = list(self.all or [])
        for clause in self.any or []:
            clauses.extend(clause.all or [])  # type: ignore[arg-type]
        return sorted({c.path for c in clauses if evaluate_condition(c, values)})


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    rules: list[Rule]

    def by_id(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)


@functools.lru_cache(maxsize=1)
def load_rules() -> RuleSet:
    path = settings.path(settings.ontology_dir) / "redflags.yaml"
    ruleset = RuleSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    _assert_additive_only(ruleset)
    return ruleset


def _assert_additive_only(ruleset: RuleSet) -> None:
    """Loaded at startup. A de-escalating rule cannot enter the system at runtime."""
    for rule in ruleset.rules:
        if rule.level not in ("urgent", "immediate"):
            raise ValidationError(
                f"Rule {rule.id} has level {rule.level!r}. Red-flag rules are additive: the "
                "only levels are 'urgent' and 'immediate'."
            )


@dataclass(slots=True)
class Proposal:
    """Every candidate considered, fired or not. Invariant 3's audit requirement."""

    rule_id: str
    proposed_by: str  # "rules" | "llm"
    fired: bool
    level: str | None
    rationale: str | None
    triggering_paths: list[str] = field(default_factory=list)
    triggering_fact_ids: list[str] = field(default_factory=list)
    #: Why an LLM candidate was discarded, when it was.
    discarded_because: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "proposedBy": self.proposed_by,
            "fired": self.fired,
            "level": self.level,
            "rationale": self.rationale,
            "triggeringPaths": self.triggering_paths,
            "triggeringFactIds": self.triggering_fact_ids,
            "discardedBecause": self.discarded_because,
        }


@dataclass(slots=True)
class Escalation:
    priority: Priority
    flags: list[RedFlag] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority.label,
            "flags": [api_dump(f) for f in self.flags],
            "proposals": [p.to_dict() for p in self.proposals],
            "immediateCount": sum(1 for f in self.flags if f.level == "immediate"),
            "urgentCount": sum(1 for f in self.flags if f.level == "urgent"),
        }


def evaluate(
    ledger: FactLedger,
    *,
    current_priority: Priority | str = Priority.ROUTINE,
    llm_candidates: list[dict[str, Any]] | None = None,
    extra_values: dict[str, Any] | None = None,
) -> Escalation:
    """Run every rule over the recorded facts. Deterministic, total, and additive only."""
    values: dict[str, Any] = dict(extra_values or {})
    fact_ids_by_path: dict[str, list[str]] = {}
    for fact in ledger.active_facts():
        values[fact.path] = fact.value
        fact_ids_by_path.setdefault(fact.path, []).append(fact.fact_id)

    ruleset = load_rules()
    priority = (
        current_priority
        if isinstance(current_priority, Priority)
        else Priority.parse(current_priority)
    )
    flags: list[RedFlag] = []
    proposals: list[Proposal] = []
    #: Accumulated separately from `priority`. Rules fire in file order, so an `urgent` rule
    #: after an `immediate` one would otherwise look like a de-escalation to raise_priority()
    #: and abort the whole evaluation. Take the max of what fired, then make ONE guarded
    #: transition below — the guard protects the state change, not the arithmetic.
    highest_fired = Priority.ROUTINE

    for rule in ruleset.rules:
        fired = rule.fires(values)
        paths = rule.matching_paths(values) if fired else []
        fact_ids = [fid for path in paths for fid in fact_ids_by_path.get(path, [])]
        proposals.append(
            Proposal(
                rule_id=rule.id,
                proposed_by="rules",
                fired=fired,
                level=rule.level if fired else None,
                rationale=rule.rationale if fired else None,
                triggering_paths=paths,
                triggering_fact_ids=fact_ids,
            )
        )
        if not fired:
            continue
        highest_fired = max(highest_fired, rule.priority())
        flags.append(
            RedFlag(
                rule_id=rule.id,
                label=rule.label,
                level=rule.level,  # type: ignore[arg-type]
                rationale=rule.rationale,
                triggering_fact_ids=fact_ids,
                fired_at=datetime.now(UTC),
            )
        )

    # `max` over Priority is monotone by construction and there is no level below ROUTINE,
    # so this cannot lower a session that already reached `immediate` in an earlier turn —
    # even when nothing fires this round. `raise_priority()` remains the guarded setter for
    # the triage API, where a caller could genuinely attempt a downgrade.
    priority = max(priority, highest_fired)

    # ---- LLM candidates: matched to a real rule, then re-decided by that rule ----
    for candidate in llm_candidates or []:
        rule_id = str(candidate.get("rule_id", ""))
        candidate_rule = ruleset.by_id(rule_id)
        if candidate_rule is None:
            proposals.append(
                Proposal(
                    rule_id=rule_id or "<unnamed>",
                    proposed_by="llm",
                    fired=False,
                    level=None,
                    rationale=str(candidate.get("reason", ""))[:200],
                    discarded_because=(
                        "No rule with this id exists. A model cannot invent an escalation."
                    ),
                )
            )
            log.warning("redflag.llm_unknown_rule", rule_id=rule_id)
            continue

        if any(p.rule_id == rule_id and p.fired for p in proposals):
            proposals.append(
                Proposal(
                    rule_id=rule_id,
                    proposed_by="llm",
                    fired=True,
                    level=candidate_rule.level,
                    rationale=str(candidate.get("reason", ""))[:200],
                    discarded_because="Already fired deterministically; the model agreed.",
                )
            )
            continue

        # The model spotted something the rules did not. The rules still decide.
        proposals.append(
            Proposal(
                rule_id=rule_id,
                proposed_by="llm",
                fired=False,
                level=None,
                rationale=str(candidate.get("reason", ""))[:200],
                discarded_because=(
                    "The rule's own conditions do not hold against the recorded facts. "
                    "Logged for review: a repeatedly-correct model proposal here is evidence "
                    "the RULE needs widening, which is a change a clinician makes to "
                    "redflags.yaml — not one a model makes at runtime."
                ),
            )
        )
        log.info("redflag.llm_proposal_not_fired", rule_id=rule_id)

    return Escalation(priority=priority, flags=flags, proposals=proposals)

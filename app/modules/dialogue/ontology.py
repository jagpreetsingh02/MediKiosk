"""Loads and types the clinical history ontology. The ontology itself is YAML under
`data/ontology/` — see that directory for the interview content.

This module contains **no clinical content**. It contains the loader, the typed models, and
the condition evaluator. A clinician changing the interview edits YAML; nobody edits Python.
"""

from __future__ import annotations

import functools
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings
from app.core.errors import ValidationError

QuestionKind = Literal[
    "open_text", "single_choice", "multi_choice", "boolean", "scale", "duration", "derived"
]


class Option(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: str
    label_en: str
    label_hi: str | None = None
    icon: str | None = None
    #: Choosing this option clears every other selection ("None of these").
    exclusive: bool = False
    #: Terminology term to attempt to code, for problem-list options. Never a code itself.
    term: str | None = None
    #: A Dashavidha code NAMED here and RETRIEVED by the sidecar (Invariant 5).
    code: str | None = None
    days: int | None = None

    def label(self, language: str) -> str:
        return getattr(self, f"label_{language}", None) or self.label_en


class Scale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: int = 0
    max: int = 10
    faces: bool = True
    anchors_en: list[str] = Field(default_factory=list)
    anchors_hi: list[str] = Field(default_factory=list)


class Condition(BaseModel):
    """One clause of the `ask_if` DSL. Exactly one operator per clause."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: str
    eq: Any = None
    ne: Any = None
    in_: list[Any] | None = Field(default=None, alias="in")
    not_in: list[Any] | None = None
    gt: float | None = None
    lt: float | None = None
    gte: float | None = None
    lte: float | None = None
    contains: str | None = None
    recorded: bool | None = None
    not_recorded: bool | None = None


class AnyOf(BaseModel):
    """A nested disjunction, usable as one clause of an `all`.

    One level of nesting, deliberately. It is the minimum needed to express "this AND (that
    OR the other)", which is what recall-biased branching requires — and a fully general
    boolean tree in YAML is a language a clinician cannot read.
    """

    model_config = ConfigDict(extra="forbid")

    any: list[Condition]


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: list[Condition | AnyOf] | None = None
    any: list[Condition] | None = None

    @model_validator(mode="after")
    def _one_of(self) -> ConditionGroup:
        if (self.all is None) == (self.any is None):
            raise ValueError("ask_if must specify exactly one of `all` or `any`")
        return self


class DeriveRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lt: float | None = None
    gte: float | None = None
    lte: float | None = None
    gt: float | None = None
    value: str
    code: str | None = None


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    kind: QuestionKind
    #: What the PATIENT hears. Written for a first-time, possibly non-literate user.
    prompt: dict[str, str]
    #: What the PHYSICIAN reads on the summary. Two audiences, two registers: "What is
    #: troubling you today?" is right for a kiosk and useless in a dense clinical summary.
    #: Defaults to the prettified path leaf, which is right for most fields.
    label: str | None = None
    help: dict[str, str] = Field(default_factory=dict)
    options: list[Option] = Field(default_factory=list)
    scale: Scale | None = None
    required: bool = False
    ask_if: ConditionGroup | None = None
    repeatable: bool = False
    entry_of: str | None = None
    #: Answers to this question are fed to the red-flag rule engine (Invariant 3).
    red_flag_scan: bool = False
    #: A wrong answer here is dangerous, so an UNMEASURED speech confidence is not good
    #: enough: the question degrades to touch rather than recording a value nobody scored.
    #: Set on allergies, medications and the red-flag screens — the three the build brief
    #: singles out. Elsewhere an unmeasured answer is recorded and flagged for verification,
    #: because losing it would be worse than reviewing it.
    confidence_critical: bool = False
    socrates: str | None = None
    system: str | None = None
    parameter: str | None = None
    parameter_code: str | None = None
    derive_from: str | None = None
    derive_rules: list[DeriveRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _shape(self) -> Question:
        if self.kind in ("single_choice", "multi_choice") and not self.options:
            raise ValueError(f"{self.id}: a choice question needs options")
        if self.kind == "scale" and self.scale is None:
            raise ValueError(f"{self.id}: a scale question needs a `scale` block")
        if self.kind == "derived" and not (self.derive_from and self.derive_rules):
            raise ValueError(f"{self.id}: a derived question needs derive_from and derive_rules")
        if "en" not in self.prompt:
            raise ValueError(f"{self.id}: every question needs an English prompt")
        return self

    def text(self, language: str) -> tuple[str, bool]:
        """Return (prompt, translation_missing). English is the honest fallback."""
        if language in self.prompt:
            return self.prompt[language], False
        return self.prompt["en"], language != "en"

    def physician_label(self) -> str:
        if self.label:
            return self.label
        return self.path.rsplit(".", 1)[-1].replace("_", " ").capitalize()

    def option(self, value: str) -> Option | None:
        return next((o for o in self.options if o.value == value), None)

    def valid_values(self) -> set[str]:
        return {o.value for o in self.options}


class OntologySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    title_hi: str | None = None
    intro: dict[str, str] = Field(default_factory=dict)
    questions: list[Question]


class Ontology(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    title: str
    sections: list[OntologySection]

    @functools.cached_property
    def by_id(self) -> dict[str, Question]:
        return {q.id: q for s in self.sections for q in s.questions}

    @functools.cached_property
    def by_path(self) -> dict[str, Question]:
        return {q.path: q for s in self.sections for q in s.questions}

    @functools.cached_property
    def known_paths(self) -> set[str]:
        """Every path `record_fact()` will accept. A typo cannot invent a clinical field."""
        paths = set(self.by_path)
        # Repeatable entries index into a list: medications[0].name and so on.
        for question in self.by_id.values():
            if question.entry_of:
                for index in range(24):
                    paths.add(f"{question.entry_of}[{index}].{question.path.rsplit('.', 1)[-1]}")
        paths.update(_ENTRY_PATHS)
        return paths

    def section(self, section_id: str) -> OntologySection | None:
        return next((s for s in self.sections if s.id == section_id), None)


#: Paths written by Module B (documents) and by the entry builders, which have no question.
_ENTRY_PATHS: set[str] = {
    f"{group}[{i}].{field}"
    for group, fields in {
        "medications": ("name", "dose", "frequency", "route", "started", "ongoing"),
        "allergies": ("substance", "reaction", "severity"),
        "problems": ("reported_term", "reported_year"),
        "investigations": ("analyte", "value", "observed_on"),
        "procedures": ("name", "performed_on"),
    }.items()
    for i in range(48)
    for field in fields
}


def _merge(ontologies: list[Ontology], version: str, title: str) -> Ontology:
    return Ontology(
        version=version,
        title=title,
        sections=[s for o in ontologies for s in o.sections],
    )


def _load_file(name: str) -> Ontology:
    path = settings.path(settings.ontology_dir) / name
    if not path.exists():
        raise ValidationError(f"Ontology file {path} is missing.")
    return Ontology.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@functools.lru_cache(maxsize=4)
def load_ontology(*, ayush: bool = False) -> Ontology:
    """Core + ROS always; the AYUSH extension only in AYUSH mode. Cached per mode."""
    parts = [_load_file("core.yaml"), _load_file("ros.yaml")]
    if ayush:
        parts.append(_load_file("ayush.yaml"))
    merged = _merge(parts, version=parts[0].version, title="Swastra clinical history")
    _assert_unique(merged)
    return merged


def _assert_unique(ontology: Ontology) -> None:
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for section in ontology.sections:
        for question in section.questions:
            if question.id in seen_ids:
                raise ValidationError(f"Duplicate question id {question.id!r} in the ontology.")
            if question.path in seen_paths:
                raise ValidationError(f"Duplicate path {question.path!r} in the ontology.")
            seen_ids.add(question.id)
            seen_paths.add(question.path)


# ---------------------------------------------------------------- condition evaluation


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def evaluate_condition(clause: Condition, values: dict[str, Any]) -> bool:
    """Total function: an unrecorded path makes every operator false except `not_recorded`.

    That asymmetry is deliberate. A branch guarded by "the patient said yes" must not open
    merely because we have not asked yet.
    """
    present = clause.path in values
    if clause.recorded is not None:
        return present is clause.recorded
    if clause.not_recorded is not None:
        return present is not clause.not_recorded
    if not present:
        return False

    actual = values[clause.path]

    if clause.eq is not None:
        return clause.eq in _as_list(actual)
    if clause.ne is not None:
        return clause.ne not in _as_list(actual)
    if clause.in_ is not None:
        return any(item in clause.in_ for item in _as_list(actual))
    if clause.not_in is not None:
        return all(item not in clause.not_in for item in _as_list(actual))
    if clause.contains is not None:
        return any(clause.contains.casefold() in str(i).casefold() for i in _as_list(actual))

    numeric = _numeric(actual)
    if numeric is None:
        return False
    if clause.gt is not None:
        return numeric > clause.gt
    if clause.lt is not None:
        return numeric < clause.lt
    if clause.gte is not None:
        return numeric >= clause.gte
    if clause.lte is not None:
        return numeric <= clause.lte
    return False


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def evaluate_clause(clause: Condition | AnyOf, values: dict[str, Any]) -> bool:
    if isinstance(clause, AnyOf):
        return any(evaluate_condition(c, values) for c in clause.any)
    return evaluate_condition(clause, values)


def should_ask(question: Question, values: dict[str, Any]) -> bool:
    """Deterministic. Same values in, same answer out, every time, with no model involved."""
    if question.ask_if is None:
        return True
    group = question.ask_if
    if group.all is not None:
        return all(evaluate_clause(c, values) for c in group.all)
    assert group.any is not None
    return any(evaluate_condition(c, values) for c in group.any)


def derive_value(question: Question, values: dict[str, Any]) -> tuple[str, str | None] | None:
    """Evaluate a `derived` question. Returns (value, code) or None if the input is missing."""
    source = values.get(question.derive_from or "")
    numeric = _numeric(source)
    if numeric is None:
        return None
    for rule in question.derive_rules:
        if rule.lt is not None and not numeric < rule.lt:
            continue
        if rule.lte is not None and not numeric <= rule.lte:
            continue
        if rule.gt is not None and not numeric > rule.gt:
            continue
        if rule.gte is not None and not numeric >= rule.gte:
            continue
        return rule.value, rule.code
    return None

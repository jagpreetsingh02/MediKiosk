"""Module A — the deterministic dialogue state machine.

**The LLM never decides what to ask next.** This file decides, by walking the ontology in
order and evaluating `ask_if` conditions against facts already recorded. Given the same
ledger it produces the same next question every single time, and it keeps working with the
network unplugged, the Groq key revoked, and the model deprecated.

The LLM has exactly two jobs elsewhere in Module A:

* `app/llm/extraction.py` — pull slot values out of a free-text utterance (Phase 2);
* `app/llm/phrasing.py`   — say this question's fixed intent in more natural words (Phase 2).

Neither can change the question order, skip a question, add a question, or end the interview.
`tests/test_machine_is_deterministic.py` runs the whole interview with the LLM stubbed to
raise, and asserts an identical transcript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.contracts.provenance import AbsenceReason
from app.contracts.record import FactLedger
from app.core.logging import get_logger
from app.modules.dialogue.ontology import (
    Ontology,
    Question,
    derive_value,
    load_ontology,
    should_ask,
)

log = get_logger(__name__)

#: The machine never asks the same question twice, but a patient may revisit one. This caps
#: how many times a single question can be re-presented before the machine moves on, so a
#: stuck client cannot loop the kiosk forever.
MAX_VISITS_PER_QUESTION = 4


@dataclass(slots=True)
class Turn:
    """One question put to the patient, and what came back."""

    turn_id: str
    question_id: str
    prompt: str
    language: str
    translation_missing: bool
    answered: bool = False
    raw_answer: Any = None
    modality: str | None = None
    skipped_reason: str | None = None


@dataclass(slots=True)
class DialogueState:
    """Everything the machine needs. Serialised into `intake_session.state_json`."""

    session_id: str
    language: str = "en"
    ayush_mode: bool = False
    cursor: int = 0
    turns: list[Turn] = field(default_factory=list)
    visits: dict[str, int] = field(default_factory=dict)
    #: Slot values in condition-DSL space: path -> value. Rebuilt from the ledger, plus
    #: demographics, which are not facts (they came from the token, not from the patient).
    values: dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    #: Questions the patient explicitly skipped. Recorded as `declined`, never as a value.
    declined: list[str] = field(default_factory=list)
    #: Set when a question must fall back to touch because ASR confidence was too low.
    forced_touch: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "language": self.language,
            "ayush_mode": self.ayush_mode,
            "cursor": self.cursor,
            "visits": self.visits,
            "values": self.values,
            "completed": self.completed,
            "declined": self.declined,
            "forced_touch": self.forced_touch,
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "question_id": t.question_id,
                    "prompt": t.prompt,
                    "language": t.language,
                    "translation_missing": t.translation_missing,
                    "answered": t.answered,
                    "raw_answer": t.raw_answer,
                    "modality": t.modality,
                    "skipped_reason": t.skipped_reason,
                }
                for t in self.turns
            ],
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> DialogueState:
        state = cls(
            session_id=payload["session_id"],
            language=payload.get("language", "en"),
            ayush_mode=payload.get("ayush_mode", False),
            cursor=payload.get("cursor", 0),
            visits=payload.get("visits", {}),
            values=payload.get("values", {}),
            completed=payload.get("completed", False),
            declined=payload.get("declined", []),
            forced_touch=payload.get("forced_touch", []),
        )
        state.turns = [Turn(**t) for t in payload.get("turns", [])]
        return state


@dataclass(frozen=True, slots=True)
class NextQuestion:
    """What the kiosk should render. Every field the UI needs, nothing it does not."""

    turn_id: str
    question_id: str
    path: str
    kind: str
    prompt: str
    help: str | None
    language: str
    translation_missing: bool
    section_id: str
    section_title: str
    socrates: str | None
    options: list[dict[str, Any]]
    scale: dict[str, Any] | None
    required: bool
    #: True when ASR failed on this question and the patient must tap. Speech stays offered
    #: for the *next* question — degradation is per-question, never sticky for the session.
    touch_only: bool
    progress: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "turnId": self.turn_id,
            "questionId": self.question_id,
            "path": self.path,
            "kind": self.kind,
            "prompt": self.prompt,
            "help": self.help,
            "language": self.language,
            "translationMissing": self.translation_missing,
            "sectionId": self.section_id,
            "sectionTitle": self.section_title,
            "socrates": self.socrates,
            "options": self.options,
            "scale": self.scale,
            "required": self.required,
            "touchOnly": self.touch_only,
            "progress": self.progress,
        }


class DialogueMachine:
    """Walks the ontology. Holds no clinical content and makes no clinical judgement."""

    def __init__(self, state: DialogueState, ledger: FactLedger) -> None:
        self.state = state
        self.ledger = ledger
        self.ontology: Ontology = load_ontology(ayush=state.ayush_mode)
        self._flat: list[tuple[str, str, Question]] = [
            (section.id, section.title, question)
            for section in self.ontology.sections
            for question in section.questions
        ]

    # -------------------------------------------------------------- navigation

    def _answered_paths(self) -> set[str]:
        return self.ledger.paths() | {
            q.path for q in self._questions() if q.id in self.state.declined
        }

    def _questions(self) -> list[Question]:
        return [q for _, _, q in self._flat]

    def _condition_values(self) -> dict[str, Any]:
        """Ledger facts plus demographics, in the flat path space the condition DSL uses."""
        values = dict(self.state.values)
        for fact in self.ledger.active_facts():
            values[fact.path] = fact.value
        return values

    def next_question(self) -> NextQuestion | None:
        """The single decision point of Module A. Pure: no I/O, no model, no randomness."""
        values = self._condition_values()
        answered = self._answered_paths()

        while self.state.cursor < len(self._flat):
            section_id, section_title, question = self._flat[self.state.cursor]

            if question.path in answered:
                self.state.cursor += 1
                continue
            if self.state.visits.get(question.id, 0) >= MAX_VISITS_PER_QUESTION:
                self.state.cursor += 1
                continue
            if not should_ask(question, values):
                # Not asked because the branch is closed. That is an absence with a reason,
                # not a silent gap — the physician sees "not asked" and knows why.
                self.ledger.record_absence(
                    question.path, AbsenceReason.NOT_ASKED, question_id=question.id
                )
                self.state.cursor += 1
                continue
            if question.kind == "derived":
                # Answered by the machine from data we already hold. Recorded by the caller
                # (routes) through record_fact with a synthetic span; see dialogue router.
                self.state.cursor += 1
                continue

            return self._present(section_id, section_title, question)

        self.state.completed = True
        return None

    def _present(self, section_id: str, section_title: str, question: Question) -> NextQuestion:
        prompt, missing = question.text(self.state.language)
        help_text = question.help.get(self.state.language) or question.help.get("en")
        turn_id = f"turn_{len(self.state.turns) + 1:03d}"

        self.state.visits[question.id] = self.state.visits.get(question.id, 0) + 1
        self.state.turns.append(
            Turn(
                turn_id=turn_id,
                question_id=question.id,
                prompt=prompt,
                language=self.state.language,
                translation_missing=missing,
            )
        )
        return NextQuestion(
            turn_id=turn_id,
            question_id=question.id,
            path=question.path,
            kind=question.kind,
            prompt=prompt,
            help=help_text,
            language=self.state.language,
            translation_missing=missing,
            section_id=section_id,
            section_title=section_title,
            socrates=question.socrates,
            options=[
                {
                    "value": o.value,
                    "label": o.label(self.state.language),
                    "labelEn": o.label_en,
                    "icon": o.icon,
                    "exclusive": o.exclusive,
                }
                for o in question.options
            ],
            scale=question.scale.model_dump() if question.scale else None,
            required=question.required,
            touch_only=question.id in self.state.forced_touch,
            progress=self.progress(),
        )

    # -------------------------------------------------------------- bookkeeping

    def current_turn(self, turn_id: str) -> Turn | None:
        return next((t for t in self.state.turns if t.turn_id == turn_id), None)

    def mark_answered(self, turn_id: str, raw_answer: Any, modality: str) -> None:
        turn = self.current_turn(turn_id)
        if turn is not None:
            turn.answered = True
            turn.raw_answer = raw_answer
            turn.modality = modality

    def decline(self, question_id: str) -> None:
        """The patient chose not to answer. Recorded as `declined`, never guessed at."""
        question = self.ontology.by_id.get(question_id)
        if question is None:
            return
        if question_id not in self.state.declined:
            self.state.declined.append(question_id)
        self.ledger.record_absence(question.path, AbsenceReason.DECLINED, question_id=question_id)

    def force_touch(self, question_id: str) -> None:
        """ASR confidence fell below threshold. This question degrades to touch (Phase 3)."""
        if question_id not in self.state.forced_touch:
            self.state.forced_touch.append(question_id)
        # Re-present the same question rather than moving on: a low-confidence transcript is
        # not an answer, and guessing at it is exactly the failure mode we refuse.
        self.state.cursor = min(
            self.state.cursor,
            next(
                (i for i, (_, _, q) in enumerate(self._flat) if q.id == question_id),
                self.state.cursor,
            ),
        )

    def derived_questions(self) -> list[tuple[Question, str, str | None]]:
        """Every `derived` question whose input is available. Evaluated deterministically."""
        values = self._condition_values()
        out: list[tuple[Question, str, str | None]] = []
        for question in self._questions():
            if question.kind != "derived" or question.path in self.ledger.paths():
                continue
            derived = derive_value(question, values)
            if derived is not None:
                out.append((question, derived[0], derived[1]))
        return out

    # -------------------------------------------------------------- progress

    def askable(self) -> list[Question]:
        """Questions whose branch is currently open. The denominator for progress."""
        values = self._condition_values()
        return [q for q in self._questions() if q.kind != "derived" and should_ask(q, values)]

    def progress(self) -> dict[str, int]:
        askable = self.askable()
        answered = self.ledger.paths()
        done = sum(1 for q in askable if q.path in answered or q.id in self.state.declined)
        return {
            "answered": done,
            "askable": len(askable),
            "percent": int(round(100 * done / len(askable))) if askable else 100,
            "sections": len(self.ontology.sections),
        }

    def section_progress(self) -> list[dict[str, Any]]:
        """Per-section progress for the kiosk's progress rail."""
        values = self._condition_values()
        answered = self.ledger.paths()
        out: list[dict[str, Any]] = []
        for section in self.ontology.sections:
            open_qs = [
                q for q in section.questions if q.kind != "derived" and should_ask(q, values)
            ]
            done = sum(1 for q in open_qs if q.path in answered or q.id in self.state.declined)
            out.append(
                {
                    "sectionId": section.id,
                    "title": section.title,
                    "answered": done,
                    "total": len(open_qs),
                    "complete": bool(open_qs) and done == len(open_qs),
                }
            )
        return out

"""The gold-script contract.

A script is a synthetic patient and everything we expect the system to get right about them.
It is deliberately verbose: `expected` names the exact slot values, and `expected_red_flags`
names the exact rule ids. A script that says "should detect an emergency" is not scoreable.

Written by hand, not generated. A generated gold set measures how well the system reproduces
the generator, which is a number that always looks good and means nothing.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Difficulty = Literal["plain", "rambling", "low_literacy", "contradictory", "emergency", "mixed"]


class Turn(BaseModel):
    """One answer, in the patient's own words or as a tap."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    #: What the patient SAYS. Extraction runs over this.
    utterance: str | None = None
    #: What the patient TAPS, when they use the buttons instead.
    tap: Any = None
    #: Simulated ASR confidence. Below the threshold this must degrade to touch.
    asr_confidence: float = 0.92
    #: Explicitly declining. Must record an absence, never a value.
    decline: bool = False


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    language: str = "en"
    difficulty: Difficulty
    ayush_mode: bool = False
    demographics: dict[str, Any] = Field(default_factory=dict)
    turns: list[Turn]
    #: path -> expected value. The completeness and precision/recall denominators.
    expected: dict[str, Any] = Field(default_factory=dict)
    #: Rule ids that MUST fire. A missing one is a false negative — the only unacceptable error.
    expected_red_flags: list[str] = Field(default_factory=list)
    #: Rule ids that must NOT fire. Guards against a rule that fires on everything.
    forbidden_red_flags: list[str] = Field(default_factory=list)
    expected_priority: Literal["routine", "urgent", "immediate"] = "routine"
    #: Paths the patient declined. Must be absences, never values.
    expected_declined: list[str] = Field(default_factory=list)
    notes: str = ""

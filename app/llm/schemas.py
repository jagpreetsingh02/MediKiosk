"""Pydantic contracts for every LLM output. The model has no unstructured surface.

Note what the extraction schema demands: a `quote` for every extracted value, which must be a
**verbatim substring of the utterance**. The model is not asked to be honest about its sources;
it is asked to produce a string that `record_fact()` will then independently verify against the
transcript. A model that invents a quote fails the check and its extraction is dropped.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Must be a path the ontology defines. Anything else is rejected downstream.
    path: str
    #: For a choice question, one of the rendered option values. For open text, the text.
    #: A boolean question yields a bool and a scale yields an int — modelling those as
    #: strings would push "is the patient on medication?" through a str("False") round-trip,
    #: which is exactly where a falsy answer turns into a truthy one.
    value: str | bool | int | list[str]
    #: A verbatim substring of the patient's utterance. Checked, not trusted.
    quote: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: list[ExtractedSlot] = Field(default_factory=list)
    #: Anything the model could not place. Surfaced to the physician as unstructured
    #: narrative, never dropped and never forced into a slot.
    unplaced: list[str] = Field(default_factory=list)


class RedFlagCandidate(BaseModel):
    """A *proposal*, never a decision. The rule engine decides (Invariant 3)."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    quote: str = Field(min_length=1)
    reason: str


class RedFlagProposalSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[RedFlagCandidate] = Field(default_factory=list)


class PhrasedQuestion(BaseModel):
    """The LLM's second job: say a fixed question more naturally. It cannot change the intent."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=280)


class SmoothedSection(BaseModel):
    """Module C prose smoothing. Every content token is checked against the fact ledger."""

    model_config = ConfigDict(extra="forbid")

    prose: str = Field(min_length=1)


class DocumentEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["diagnosis", "medication", "investigation", "procedure"]
    text: str
    quote: str = Field(min_length=1)
    #: Medication only.
    dose: str | None = None
    frequency: str | None = None
    #: Investigation only.
    value: str | None = None
    unit: str | None = None
    reference_range: str | None = None
    date_text: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class DocumentEntitySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[DocumentEntity] = Field(default_factory=list)

"""``ClinicalHistory`` — the core contract.

The history is a **projection over a fact ledger**, not a mutable document. That ordering
matters: if the history were the primary store, "write a field without provenance" would be a
single careless assignment away. Here the ledger of :class:`~app.contracts.provenance.Fact` is
the truth, every entry of it went through ``record_fact()``, and the history is rebuilt from
it. A field that no fact backs cannot appear with a value — there is nowhere for that value to
have come from.

Note what is absent from this module: there is no ``assessment``, ``differential``,
``impression``, ``probability`` or ``diagnosis`` field anywhere in the contract, and
``tests/test_invariant_no_diagnosis.py`` fails the build if one appears. Invariant 1 is
enforced by the *shape* of the record, not by remembering not to fill something in.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.contracts.provenance import AbsenceReason, Fact, SourceTier

#: Field names that would turn a history into an assessment. Checked by the contract test
#: and by `app/contracts/no_diagnosis.py` at runtime on every serialised payload.
FORBIDDEN_CLINICAL_FIELDS = frozenset(
    {
        "diagnosis",
        "diagnoses",
        "differential",
        "differential_diagnosis",
        "assessment",
        "impression",
        "probability",
        "likelihood",
        "suspected_condition",
        "provisional",
        "icd_suggestion",
        "disease_probability",
        "prognosis",
        "treatment",
        "prescription",
        "plan",
        "recommendation",
        "advice",
        "therapy",
        "management",
        "specialty_referral",
    }
)


#: Every model in this module serialises camelCase on the wire (`by_alias=True`, applied at
#: the API boundary by `api_dump`) and is constructed by field name internally. One casing
#: convention on the wire matters more than which one it is.


class SlotStatus(StrEnum):
    RECORDED = "recorded"
    NOT_ASKED = "not_asked"
    DECLINED = "declined"


class Slot(BaseModel):
    """One leaf of the history. Either it carries a value *and* its provenance, or it is empty.

    ``fact_ids`` is never empty when ``status == recorded``: the projection refuses to build a
    recorded slot without at least one backing fact.
    """

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    path: str
    label: str = ""
    value: Any = None
    status: SlotStatus = SlotStatus.NOT_ASKED
    tier: SourceTier | None = None
    confidence: float | None = None
    fact_ids: list[str] = Field(default_factory=list)
    #: Verbatim source text, surfaced directly so the physician UI never has to join tables
    #: to render click-to-source.
    verbatim: str | None = None
    #: Earlier values the patient later contradicted, newest last. Kept, never deleted:
    #: a contradiction is clinically interesting.
    superseded: list[dict[str, Any]] = Field(default_factory=list)
    unit: str | None = None

    @property
    def recorded(self) -> bool:
        return self.status is SlotStatus.RECORDED


class Section(BaseModel):
    """An ordered group of slots, as the physician expects to read them."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    section_id: str
    title: str
    slots: dict[str, Slot] = Field(default_factory=dict)
    #: 0.0–1.0. Recorded slots over askable slots. Drives the completeness metric.
    completeness: float = 0.0

    def get(self, key: str) -> Slot | None:
        return self.slots.get(key)


# ---------------------------------------------------------------- repeating structures


class Medication(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    entry_id: str
    name: Slot
    dose: Slot
    frequency: Slot
    route: Slot
    started: Slot
    ongoing: Slot
    #: Populated only through the terminology sidecar. `None` means unmapped, which is a
    #: first-class valid result (Invariant 5), not a failure and not a guess.
    coding: dict[str, Any] | None = None


class Allergy(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    entry_id: str
    substance: Slot
    reaction: Slot
    severity: Slot


class ProblemEntry(BaseModel):
    """A problem the patient or a document *reports*. Not an assessment: reported history only."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    entry_id: str
    reported_term: Slot
    reported_year: Slot
    coding: dict[str, Any] | None = None
    #: True when the terminology sidecar found nothing. Rendered as "unmapped", never guessed.
    unmapped: bool = True


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    entry_id: str
    analyte: Slot
    value: Slot
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    #: "low" | "high" | "in_range" | "unknown" — a range comparison, never an interpretation.
    range_flag: Literal["low", "high", "in_range", "unknown"] = "unknown"
    observed_on: date | None = None
    coding: dict[str, Any] | None = None


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    event_id: str
    occurred_on: date | None
    #: Where on the certainty scale the date sits: exact | month | year | relative | unknown
    date_precision: Literal["exact", "month", "year", "relative", "unknown"] = "unknown"
    kind: Literal["diagnosis", "medication", "investigation", "procedure", "note"]
    label: str
    detail: str | None = None
    document_id: str | None = None
    fact_ids: list[str] = Field(default_factory=list)
    low_confidence: bool = False


class RedFlag(BaseModel):
    """Fired by the deterministic rule engine only. Additive: it can never lower a priority."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    rule_id: str
    label: str
    #: The only two levels the system emits. There is no "low" and no "routine": the absence
    #: of a flag is not a statement about the patient (Invariant 3).
    level: Literal["urgent", "immediate"]
    rationale: str
    triggering_fact_ids: list[str] = Field(default_factory=list)
    fired_at: datetime | None = None


class DocumentRef(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    document_id: str
    filename: str
    pages: int
    ocr_backend: str
    mean_confidence: float
    #: Pages that landed in the handwriting lane; always surfaced for human verification.
    low_confidence_pages: list[int] = Field(default_factory=list)
    uploaded_at: datetime


class Demographics(BaseModel):
    """From the ABHA token only. The kiosk never asks the patient to re-type these."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    abha_ref: str | None = None
    display_name: str | None = None
    age_years: int | None = None
    gender: str | None = None
    #: Preferred language of the session, ISO 639-1.
    language: str = "en"


# ---------------------------------------------------------------- the contract


class ClinicalHistory(BaseModel):
    """The physician-facing structured record. Rebuilt from the ledger; never hand-edited."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    session_id: str
    schema_version: str = "1.0.0"
    generated_at: datetime
    demographics: Demographics = Field(default_factory=Demographics)

    chief_complaint: Section
    hpi: Section
    past_medical: Section
    past_surgical: Section
    drug_allergy: Section
    family_history: Section
    personal_history: Section
    review_of_systems: Section
    #: Dashavidha Pariksha + Ahara-Vihara. Empty unless the session ran in AYUSH mode.
    ayush: Section | None = None

    medications: list[Medication] = Field(default_factory=list)
    allergies: list[Allergy] = Field(default_factory=list)
    problems: list[ProblemEntry] = Field(default_factory=list)
    investigations: list[InvestigationResult] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    documents: list[DocumentRef] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)

    #: Two sources that disagree. Neither is discarded and neither wins; the physician
    #: resolves it. Populated by app/contracts/contradictions.py.
    contradictions: list[dict[str, Any]] = Field(default_factory=list)

    #: Slots the patient explicitly declined, kept visible so the physician knows the gap is
    #: a refusal and not an oversight.
    declined: list[str] = Field(default_factory=list)
    not_asked: list[str] = Field(default_factory=list)
    overall_completeness: float = 0.0

    def sections(self) -> list[Section]:
        ordered = [
            self.chief_complaint,
            self.hpi,
            self.past_medical,
            self.past_surgical,
            self.drug_allergy,
            self.family_history,
            self.personal_history,
            self.review_of_systems,
        ]
        if self.ayush is not None:
            ordered.append(self.ayush)
        return ordered

    def all_slots(self) -> dict[str, Slot]:
        out: dict[str, Slot] = {}
        for section in self.sections():
            out.update(section.slots)
        return out

    def recorded_fact_ids(self) -> set[str]:
        ids: set[str] = set()
        for slot in self.all_slots().values():
            ids.update(slot.fact_ids)
        for group in (self.medications, self.allergies, self.problems, self.investigations):
            for entry in group:
                for field_name in type(entry).model_fields:
                    member = getattr(entry, field_name)
                    if isinstance(member, Slot):
                        ids.update(member.fact_ids)
        for event in self.timeline:
            ids.update(event.fact_ids)
        return ids


class LedgerSnapshot(BaseModel):
    """Everything the projection was built from. Shipped alongside the history for audit."""

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

    session_id: str
    facts: list[Fact]
    absences: list[dict[str, Any]]

    def by_id(self) -> dict[str, Fact]:
        return {f.fact_id: f for f in self.facts}


def absence_status(reason: AbsenceReason) -> SlotStatus:
    return SlotStatus.DECLINED if reason is AbsenceReason.DECLINED else SlotStatus.NOT_ASKED


def api_dump(model: BaseModel) -> dict[str, Any]:
    """Serialise for the wire: camelCase, JSON-safe, nulls dropped."""
    return model.model_dump(mode="json", by_alias=True, exclude_none=False)

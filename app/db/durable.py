"""Durable clinical records — the longitudinal half of the schema.

`app/db/models.py` holds the **capture** side: `IntakeSession` and its facts, documents and
proposals, all of which are purged when the visit ends (Invariant 6). This module holds what
*survives*: the patient, their confirmed encounters, and the clinical events promoted out of a
capture session when a physician confirmed it.

The split is the point, and it is why `IntakeSession` was not simply renamed `Encounter`:

    CaptureSession  ──physician confirms──▶  Encounter (durable)
         │                                        │
         └────────── purged ◀───────── only after promotion succeeds

Nothing reaches these tables except through `app/modules/encounter/promote.py`, in one
transaction. A half-promoted encounter would be worse than a lost one, because it would look
complete.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, ts_column

# ---------------------------------------------------------------- patient


class Patient(Base):
    """A person with a history in MediKiosk.

    EVERY patient in this repository is synthetic today (see docs/CURRENT_STATE.md), but
    `is_synthetic` is not a comment about that — it is a boundary the query layer enforces.
    Guest mode creates real rows in the real schema, and the moment a genuine record exists
    beside them, "which of these two identical-looking stomach complaints may I retrieve
    against?" becomes a question with a wrong answer.

    See `app/modules/encounter/cohort.py`. The rule is symmetric: a demo patient must never
    retrieve against a real one, AND a real patient must never retrieve against a demo one.
    The second direction is the one that would actually harm someone — a clinician shown a
    "similar previous visit" that was invented for a conference stand.
    """

    __tablename__ = "patient"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    #: True for guest/demo records. Indexed because it is a WHERE clause on every
    #: cross-patient retrieval, not an occasional filter.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    #: Pseudonymous ABHA reference (a hash, never the address). The join key across visits.
    abha_ref: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    year_of_birth: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(32))
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = ts_column()

    identifiers: Mapped[list[PatientIdentifier]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    encounters: Mapped[list[Encounter]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="Encounter.occurred_at"
    )

    @property
    def age_years(self) -> int | None:
        if self.year_of_birth is None:
            return None
        return datetime.now().year - self.year_of_birth


class PatientIdentifier(Base):
    """A second way of naming the same person — a hospital MRN, an ABHA address hash."""

    __tablename__ = "patient_identifier"
    __table_args__ = (UniqueConstraint("system", "value", name="uq_identifier_system_value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id", ondelete="CASCADE"))
    system: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(128), index=True)
    assigner: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = ts_column()

    patient: Mapped[Patient] = relationship(back_populates="identifiers")


# ---------------------------------------------------------------- encounter


class Encounter(Base):
    """One confirmed visit. Created only by promotion, never by the capture flow."""

    __tablename__ = "encounter"
    __table_args__ = (Index("ix_encounter_patient_time", "patient_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    encounter_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id", ondelete="CASCADE"))
    #: The capture session this came from. Kept for audit; that session's rows are gone.
    source_session_ref: Mapped[str | None] = mapped_column(String(64))
    #: The consent under which this encounter was captured.
    #:
    #: `ConsentRecord` already existed, already durable, already versioned and scoped — but it
    #: is keyed by `session_ref`, and the session is purged on submit. So a committed encounter
    #: had no way to answer "what was this patient's consent when we captured it?" without
    #: joining on a string whose owning row had been deliberately destroyed. Retention and
    #: purge decisions reference consent, so the encounter has to be able to reach it directly.
    #: Not a foreign key: consent_record lives on the capture side and its lifecycle is not
    #: this table's to constrain.
    consent_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = ts_column()
    kind: Mapped[str] = mapped_column(String(32), default="intake")
    language: Mapped[str] = mapped_column(String(8), default="en")
    ayush_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Highest priority the red-flag engine reached during capture.
    priority: Mapped[str] = mapped_column(String(16), default="routine")
    #: A short human label for the timeline — the patient's own complaint words.
    headline: Mapped[str | None] = mapped_column(String(255))
    confirmed_by: Mapped[str] = mapped_column(String(255))
    confirmed_at: Mapped[datetime] = ts_column()
    #: The physician-confirmed summary, exactly as it was confirmed. Immutable.
    summary_json: Mapped[dict | None] = mapped_column(JSON)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)

    patient: Mapped[Patient] = relationship(back_populates="encounters")
    facts: Mapped[list[ClinicalFactRecord]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    documents: Mapped[list[DocumentRecord]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    medications: Mapped[list[MedicationEvent]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    observations: Mapped[list[ObservationEvent]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    timeline: Mapped[list[TimelineEventRecord]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    red_flags: Mapped[list[RedFlagEventRecord]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    decisions: Mapped[list[PhysicianDecision]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[ReportSnapshot]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------- facts and evidence


#: What a fact's `state` may be. THREE OF THESE MIRROR `tier`, AND THREE DO NOT, which is the
#: whole reason the column exists separately.
#:
#: `tier` answers "how good is this evidence" — stated, confirmed, document — and is bound by
#: Invariant 2 to a span that exists. It therefore has no way to express an ABSENCE, and the
#: brief needs three kinds of absence told apart:
#:
#:     not_asked   the dialogue never reached the question. No patient action, no span.
#:     declined    the patient was asked and refused. A REAL action, with a real span.
#:     unknown     the patient was asked and does not know. Also a real action and span.
#:
#: "We did not ask" and "she chose not to say" are different clinical facts, and flattening
#: both to a blank line on the report is how a physician comes to believe a question was
#: answered in the negative when it was never put. `declined` and `unknown` carry provenance
#: like any other fact; `not_asked` is the only one that may exist without a span, because
#: nothing happened to have a span of.
FACT_STATES = ("stated", "confirmed", "document", "unknown", "not_asked", "declined")


class ClinicalFactRecord(Base):
    """A promoted fact. Same shape as `SessionFact`, but it outlives the session.

    FACTS ARE NEVER DELETED AND NEVER OVERWRITTEN. A patient who changes an answer, and a
    branch of the interview that turns out not to apply, both leave their original rows in
    place — superseded or invalidated, but still readable and still carrying their evidence.

    That is not tidiness, it is the difference between a record and a rumour. If changing an
    answer edited the row, the report could show "no chest pain" with a source span where the
    patient said the opposite an hour earlier, and nothing on the screen would be wrong
    exactly — the evidence would simply have been quietly replaced. Click-to-source only means
    something if the thing it opens is the thing that was actually said at the time.
    """

    __tablename__ = "clinical_fact"
    __table_args__ = (
        Index("ix_clinical_fact_path", "encounter_id", "path"),
        # The brief's assembly reads live facts constantly and superseded ones rarely; without
        # this every section pays a full scan of an append-only table that only ever grows.
        Index("ix_clinical_fact_live", "encounter_id", "superseded_by_id", "invalidated_reason"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    fact_ref: Mapped[str] = mapped_column(String(32), index=True)
    path: Mapped[str] = mapped_column(String(128))
    value_json: Mapped[dict | None] = mapped_column(JSON)
    display_value: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(String(16))
    #: One of `FACT_STATES`. Defaults to mirroring `tier` for anything promoted before this
    #: column existed — see the migration, which backfills rather than guessing at render time.
    state: Mapped[str] = mapped_column(String(16), default="stated")
    confidence: Mapped[float | None] = mapped_column(Float)
    #: "measured" | "unavailable" — see ADR-0011. Never fabricated.
    confidence_status: Mapped[str] = mapped_column(String(16), default="measured")
    recorded_at: Mapped[datetime] = ts_column()

    #: The fact that REPLACED this one. Null means this row is the live answer.
    #:
    #: Self-referential and `ondelete="SET NULL"`: if a superseding row is ever removed the
    #: older one must become live again rather than vanish behind a dangling pointer. Nothing
    #: in the app deletes facts, but a foreign key is not the place to assume that.
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("clinical_fact.id", ondelete="SET NULL"), index=True
    )
    #: When this fact became the live answer. Distinct from `recorded_at`, which is when the
    #: row was written: a fact promoted from a capture session was TRUE from the moment the
    #: patient said it, not from the moment a physician committed the encounter.
    valid_from: Mapped[datetime] = ts_column()
    #: Why this fact stopped applying WITHOUT being replaced — the dead-branch case. "Asked
    #: about pregnancy, patient is male" has no superseding value; the question simply should
    #: not have been on the path. Null for live facts and for superseded ones alike.
    invalidated_reason: Mapped[str | None] = mapped_column(Text)

    #: True once a physician explicitly confirmed this individual fact.
    confirmed_by_physician: Mapped[bool] = mapped_column(Boolean, default=False)

    encounter: Mapped[Encounter] = relationship(back_populates="facts")
    evidence: Mapped[list[SourceEvidence]] = relationship(
        back_populates="fact", cascade="all, delete-orphan"
    )

    @property
    def is_live(self) -> bool:
        """The answer that currently stands. What every report section reads."""
        return self.superseded_by_id is None and self.invalidated_reason is None


class SourceEvidence(Base):
    """Where a durable fact came from, in enough detail to render click-to-source later."""

    __tablename__ = "source_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("clinical_fact.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(16))  # utterance | document
    verbatim: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")
    modality: Mapped[str | None] = mapped_column(String(16))
    question_id: Mapped[str | None] = mapped_column(String(64))
    turn_id: Mapped[str | None] = mapped_column(String(32))
    asr_confidence: Mapped[float | None] = mapped_column(Float)
    #: Set for document evidence, so the physician can open the page it came from.
    document_ref: Mapped[str | None] = mapped_column(String(32), index=True)
    page: Mapped[int | None] = mapped_column(Integer)
    bbox_json: Mapped[dict | None] = mapped_column(JSON)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    handwritten: Mapped[bool] = mapped_column(Boolean, default=False)
    #: What a named human read the scrawl as, when OCR got it wrong, and who read it. The
    #: capture-side `DocumentSpan` carries both; without these columns a physician's
    #: correction lost its attribution the moment it became durable, which would leave the
    #: record holding a value whose only evidence is an OCR line that disagrees with it.
    human_reading: Mapped[str | None] = mapped_column(Text)
    read_by: Mapped[str | None] = mapped_column(String(255))

    fact: Mapped[ClinicalFactRecord] = relationship(back_populates="evidence")


# ---------------------------------------------------------------- documents


class DocumentRecord(Base):
    """A promoted document, with the bytes kept so the evidence drawer can show the page.

    Storing the file is a deliberate exception to "session data is purged": a physician who
    cannot see the prescription an extracted dose came from has provenance in name only. It
    is only ever a **synthetic** document in this repo, and it is stored against a confirmed
    encounter that the physician chose to commit.
    """

    __tablename__ = "document_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    document_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(64))
    document_kind: Mapped[str] = mapped_column(String(32), default="other")
    pages: Mapped[int] = mapped_column(Integer, default=1)
    ocr_backend: Mapped[str] = mapped_column(String(32))
    mean_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    document_date: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[str | None] = mapped_column(String(255))
    #: The file itself. Synthetic fixtures only.
    content: Mapped[bytes | None] = mapped_column(LargeBinary)
    uploaded_at: Mapped[datetime] = ts_column()

    encounter: Mapped[Encounter] = relationship(back_populates="documents")
    entities: Mapped[list[ExtractedDocumentEntity]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ExtractedDocumentEntity(Base):
    """One thing OCR read, with the region it read it from and whether a human accepted it."""

    __tablename__ = "extracted_entity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document_record.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text)
    detail_json: Mapped[dict | None] = mapped_column(JSON)
    page: Mapped[int] = mapped_column(Integer, default=1)
    bbox_json: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    handwritten: Mapped[bool] = mapped_column(Boolean, default=False)
    observed_on: Mapped[date | None] = mapped_column(Date)
    #: "accepted" | "corrected" | "rejected" — a human decided. Never auto-accepted when low.
    verification: Mapped[str] = mapped_column(String(16), default="accepted")
    verified_by: Mapped[str | None] = mapped_column(String(255))

    document: Mapped[DocumentRecord] = relationship(back_populates="entities")


# ---------------------------------------------------------------- clinical events


class MedicationEvent(Base):
    """A medicine, at a point in time, with **how we know** rather than an assumed state.

    `status` is the load-bearing column. A prescription from last year does not mean the
    patient is taking it today, and inferring that is exactly the kind of quiet clinical
    conclusion this system does not make.
    """

    __tablename__ = "medication_event"
    __table_args__ = (Index("ix_medication_patient", "patient_id", "normalized_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id", ondelete="CASCADE"))
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    dose: Mapped[str | None] = mapped_column(String(64))
    frequency: Mapped[str | None] = mapped_column(String(64))
    duration: Mapped[str | None] = mapped_column(String(64))
    route: Mapped[str | None] = mapped_column(String(32))
    #: documented | patient-reported-current | historical | stopped-reported | uncertain
    status: Mapped[str] = mapped_column(String(32), default="uncertain")
    observed_on: Mapped[date | None] = mapped_column(Date)
    source_document_ref: Mapped[str | None] = mapped_column(String(32))
    source_fact_ref: Mapped[str | None] = mapped_column(String(32))
    coding_json: Mapped[dict | None] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = ts_column()

    encounter: Mapped[Encounter] = relationship(back_populates="medications")


class ObservationEvent(Base):
    """A measured value from a document. `range_flag` is a comparison, never a judgement."""

    __tablename__ = "observation_event"
    __table_args__ = (Index("ix_observation_patient", "patient_id", "analyte_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id", ondelete="CASCADE"))
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    analyte_key: Mapped[str | None] = mapped_column(String(64), index=True)
    display: Mapped[str] = mapped_column(String(255))
    value: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(String(64))
    unit: Mapped[str | None] = mapped_column(String(32))
    reference_low: Mapped[float | None] = mapped_column(Float)
    reference_high: Mapped[float | None] = mapped_column(Float)
    range_flag: Mapped[str] = mapped_column(String(16), default="unknown")
    range_source: Mapped[str] = mapped_column(String(32), default="none")
    observed_on: Mapped[date | None] = mapped_column(Date)
    source_document_ref: Mapped[str | None] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = ts_column()

    encounter: Mapped[Encounter] = relationship(back_populates="observations")


class TimelineEventRecord(Base):
    """One row on the patient's longitudinal timeline, across every encounter."""

    __tablename__ = "timeline_event"
    __table_args__ = (Index("ix_timeline_patient_time", "patient_id", "occurred_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id", ondelete="CASCADE"))
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    event_ref: Mapped[str] = mapped_column(String(32), index=True)
    occurred_on: Mapped[date | None] = mapped_column(Date)
    date_precision: Mapped[str] = mapped_column(String(16), default="unknown")
    #: encounter | prescription | medication | investigation | procedure | diagnosis | alert
    kind: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    source_document_ref: Mapped[str | None] = mapped_column(String(32))
    source_fact_ref: Mapped[str | None] = mapped_column(String(32))
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)

    encounter: Mapped[Encounter] = relationship(back_populates="timeline")


class ContradictionRecord(Base):
    """A disagreement that survived the visit — including one spanning two encounters."""

    __tablename__ = "contradiction_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id", ondelete="CASCADE"))
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounter.id", ondelete="CASCADE")
    )
    contradiction_ref: Mapped[str] = mapped_column(String(32), index=True)
    rule_id: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(Text)
    side_a_json: Mapped[dict | None] = mapped_column(JSON)
    side_b_json: Mapped[dict | None] = mapped_column(JSON)
    clarifying_question: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open")
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    recorded_at: Mapped[datetime] = ts_column()


class RedFlagEventRecord(Base):
    """Every rule evaluation, fired or not, kept so a miss stays investigable."""

    __tablename__ = "red_flag_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    fired: Mapped[bool] = mapped_column(Boolean, default=False)
    level: Mapped[str | None] = mapped_column(String(16))
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[list | None] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = ts_column()

    encounter: Mapped[Encounter] = relationship(back_populates="red_flags")


class PhysicianDecision(Base):
    """What the physician actually did, and when. Invariant 4's receipt."""

    __tablename__ = "physician_decision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    #: confirmed_summary | edited_fact | verified_entity | rejected_entity
    decision: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(255))
    detail_json: Mapped[dict | None] = mapped_column(JSON)
    decided_at: Mapped[datetime] = ts_column()

    encounter: Mapped[Encounter] = relationship(back_populates="decisions")


# ---------------------------------------------------------------- report snapshots


class ReportSnapshot(Base):
    """A clinical brief exactly as it was rendered, kept.

    WHY STORE WHAT A PURE FUNCTION CAN REBUILD. `app/modules/report/` assembles the brief
    deterministically from stored rows, so re-running it on the same data gives the same bytes
    — that is what makes click-to-source trustworthy. But "the same data" is the assumption
    that breaks: facts get superseded, a physician corrects an entity, the reference ranges
    behind an observation are edited in a later release. Re-rendering last month's brief then
    produces something the physician never saw and never signed.

    So the payload is frozen at generation. `report_version` records which assembler wrote it,
    because a change to the assembler is exactly the kind of change that makes an old snapshot
    unreproducible — and the honest response to that is to say which version rendered it, not
    to pretend the difference does not exist.

    This is a record of what was SHOWN, not a cache. Nothing reads it to save work.
    """

    __tablename__ = "report_snapshot"
    __table_args__ = (Index("ix_report_snapshot_encounter", "encounter_id", "generated_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounter.id", ondelete="CASCADE"))
    #: Which assembler produced this. Bumped whenever the output shape or content changes.
    report_version: Mapped[str] = mapped_column(String(16))
    #: "clinician" | "patient" — the same facts, grouped and worded for different readers.
    audience: Mapped[str] = mapped_column(String(16), default="clinician")
    generated_at: Mapped[datetime] = ts_column()
    #: The rendered brief, whole. Serialized payload, not a pointer to one.
    payload_json: Mapped[dict | None] = mapped_column(JSON)

    encounter: Mapped[Encounter] = relationship(back_populates="snapshots")

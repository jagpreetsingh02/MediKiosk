"""Data model.

Two families of table live here and they have very different lifetimes:

* **Durable** — ``code_system``, ``concept``, ``audit_event``, ``consent_record``,
  ``submitted_bundle``. These outlive the patient's visit. None of them holds clinical content:
  the audit log stores references and summaries, never a symptom.
* **Session-scoped** — ``intake_session``, ``session_fact``, ``session_document``,
  ``red_flag_proposal``. Every one of these is deleted by ``purge_session()`` on submit and on
  TTL expiry (Invariant 6). The ``ON DELETE CASCADE`` from ``intake_session`` is what makes
  the purge a single statement that cannot half-succeed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
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

# ---------------------------------------------------------------- terminology (durable)


class CodeSystem(Base):
    """Ported from SIH 25026. Terminology content is *data*, never code."""

    __tablename__ = "code_system"
    __table_args__ = (UniqueConstraint("url", "version", name="uq_code_system_url_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(64))
    publisher: Mapped[str | None] = mapped_column(String(255))
    content_mode: Mapped[str] = mapped_column(String(32), default="complete")
    module: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    checksum: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts_column()

    concepts: Mapped[list[Concept]] = relationship(
        back_populates="code_system", cascade="all, delete-orphan"
    )


class Concept(Base):
    __tablename__ = "concept"
    __table_args__ = (
        UniqueConstraint("code_system_id", "code", name="uq_concept_system_code"),
        Index("ix_concept_normalized", "code_system_id", "display_normalized"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_system_id: Mapped[int] = mapped_column(ForeignKey("code_system.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64), index=True)
    display: Mapped[str] = mapped_column(Text)
    display_normalized: Mapped[str | None] = mapped_column(Text, index=True)
    class_kind: Mapped[str] = mapped_column(String(32), default="category")
    is_selectable: Mapped[bool] = mapped_column(Boolean, default=True)
    module: Mapped[str | None] = mapped_column(String(32))
    definition: Mapped[str | None] = mapped_column(Text)
    foundation_uri: Mapped[str | None] = mapped_column(String(512))
    synonyms: Mapped[list | None] = mapped_column(JSON)

    code_system: Mapped[CodeSystem] = relationship(back_populates="concepts")


# ---------------------------------------------------------------- compliance (durable)


class AuditEvent(Base):
    """Ported verbatim in structure from SIH 25026 so the chain code ports unchanged."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = ts_column()
    actor: Mapped[str] = mapped_column(String(255))
    actor_role: Mapped[str] = mapped_column(String(64))
    purpose_of_use: Mapped[str] = mapped_column(String(32))
    abha_ref: Mapped[str | None] = mapped_column(String(128))
    consent_ref: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    request_summary: Mapped[dict | None] = mapped_column(JSON)
    response_summary: Mapped[dict | None] = mapped_column(JSON)
    versions_used: Mapped[dict | None] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(32), default="success")
    #: MediKiosk addition: every AI call is auditable by model, version and prompt hash.
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))


class ConsentRecord(Base):
    """Survives the session on purpose: proving consent was given is a legal requirement."""

    __tablename__ = "consent_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consent_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    abha_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    session_ref: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    scopes_granted: Mapped[list | None] = mapped_column(JSON)
    scopes_refused: Mapped[list | None] = mapped_column(JSON)
    audio_explained: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    granted_at: Mapped[datetime] = ts_column()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubmittedBundle(Base):
    """What the physician committed. The only clinical content that outlives the session."""

    __tablename__ = "submitted_bundle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bundle_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    session_ref: Mapped[str] = mapped_column(String(64), index=True)
    abha_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    consent_ref: Mapped[str] = mapped_column(String(64))
    committed_by: Mapped[str] = mapped_column(String(255))
    committed_at: Mapped[datetime] = ts_column()
    fhir_version: Mapped[str] = mapped_column(String(16), default="4.0.1")
    bundle_json: Mapped[dict | None] = mapped_column(JSON)
    his_status: Mapped[str] = mapped_column(String(32), default="pending")
    his_detail: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- session-scoped (purged)


class IntakeSession(Base):
    __tablename__ = "intake_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    abha_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    consent_ref: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="en")
    ayush_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="consenting", index=True)
    #: Highest priority ever reached. Written only by an increase — see triage.raise_priority.
    priority: Mapped[str] = mapped_column(String(16), default="routine")
    created_at: Mapped[datetime] = ts_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state_json: Mapped[dict | None] = mapped_column(JSON)

    facts: Mapped[list[SessionFact]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list[SessionDocument]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    proposals: Mapped[list[RedFlagProposal]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class SessionFact(Base):
    """Persisted ledger row. Purged with the session; never migrated into a durable table."""

    __tablename__ = "session_fact"
    __table_args__ = (Index("ix_session_fact_path", "session_id", "path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("intake_session.id", ondelete="CASCADE"), index=True
    )
    fact_id: Mapped[str] = mapped_column(String(32), index=True)
    path: Mapped[str] = mapped_column(String(128))
    value_json: Mapped[dict | None] = mapped_column(JSON)
    tier: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    source_json: Mapped[dict | None] = mapped_column(JSON)
    superseded_by: Mapped[str | None] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = ts_column()

    session: Mapped[IntakeSession] = relationship(back_populates="facts")


class SessionDocument(Base):
    __tablename__ = "session_document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("intake_session.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(String(32), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(64))
    pages: Mapped[int] = mapped_column(Integer, default=1)
    ocr_backend: Mapped[str] = mapped_column(String(32))
    mean_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    #: The handwriting lane. Always surfaced for human verification, never auto-merged.
    needs_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[str | None] = mapped_column(String(255))
    pages_json: Mapped[list | None] = mapped_column(JSON)
    entities_json: Mapped[list | None] = mapped_column(JSON)
    #: The prescription read twice: the raw OCR transcription and the structured
    #: interpretation of it, stored together. Stored rather than recomputed on read because
    #: it is a record of what the patient was actually shown and confirmed — re-deriving it
    #: later against an edited drug dictionary would silently rewrite history. Null for a
    #: document with no medicines on it, which is most lab reports.
    reading_json: Mapped[dict | None] = mapped_column(JSON)
    #: The uploaded file. Held for the life of the capture session so that, if the physician
    #: confirms, promotion can carry it into durable evidence — a physician who cannot see the
    #: prescription a dose came from has provenance in name only. Purged with the session
    #: otherwise. Synthetic documents only.
    content: Mapped[bytes | None] = mapped_column(LargeBinary)
    uploaded_at: Mapped[datetime] = ts_column()

    session: Mapped[IntakeSession] = relationship(back_populates="documents")


class RedFlagProposal(Base):
    """Every proposal, fired or not (Invariant 3). The LLM proposes; the rules decide."""

    __tablename__ = "red_flag_proposal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("intake_session.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    proposed_by: Mapped[str] = mapped_column(String(32))  # "rules" | "llm"
    fired: Mapped[bool] = mapped_column(Boolean, default=False)
    level: Mapped[str | None] = mapped_column(String(16))
    rationale: Mapped[str | None] = mapped_column(Text)
    triggering_fact_ids: Mapped[list | None] = mapped_column(JSON)
    decided_at: Mapped[datetime] = ts_column()

    session: Mapped[IntakeSession] = relationship(back_populates="proposals")

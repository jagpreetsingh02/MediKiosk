"""The durable longitudinal schema — patient memory, in migrations at last.

The thirteen tables in `app/db/durable.py` had no migration. They existed at runtime only
because `create_all()` runs at startup, which works on the SQLite dev file and produces
nothing at all on a real Postgres: `alembic/env.py` imported `app.db.models` and never
`app.db.durable`, so `Base.metadata` held the capture half of the schema and no more.

That is why this revision is large. It is not new design — every table here is already
modelled, written by `app/modules/encounter/promote.py` and read by the patient-memory API.
This revision only makes the schema reproducible on a database that was not built by
`create_all()`, which is the precondition for Supabase being the durable store.

Two columns are here for the same drift reason: `session_document.content`, added with
document evidence, and `source_evidence.human_reading` / `read_by`, which carry a named
human\'s correction of an OCR line into the durable record.

Revision ID: f207e01b6812
Revises: 9b8e1f47140d
Create Date: 2026-08-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'f207e01b6812'
down_revision: str | None = '9b8e1f47140d'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('patient',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_ref', sa.String(length=64), nullable=False),
    sa.Column('abha_ref', sa.String(length=128), nullable=True),
    sa.Column('display_name', sa.String(length=255), nullable=True),
    sa.Column('year_of_birth', sa.Integer(), nullable=True),
    sa.Column('gender', sa.String(length=32), nullable=True),
    sa.Column('preferred_language', sa.String(length=8), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patient_abha_ref'), 'patient', ['abha_ref'], unique=True)
    op.create_index(op.f('ix_patient_patient_ref'), 'patient', ['patient_ref'], unique=True)
    op.create_table('encounter',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('encounter_ref', sa.String(length=64), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('source_session_ref', sa.String(length=64), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('ayush_mode', sa.Boolean(), nullable=False),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('headline', sa.String(length=255), nullable=True),
    sa.Column('confirmed_by', sa.String(length=255), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('summary_json', sa.JSON(), nullable=True),
    sa.Column('completeness', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['patient.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_encounter_encounter_ref'), 'encounter', ['encounter_ref'], unique=True)
    op.create_index('ix_encounter_patient_time', 'encounter', ['patient_id', 'occurred_at'], unique=False)
    op.create_table('patient_identifier',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('system', sa.String(length=128), nullable=False),
    sa.Column('value', sa.String(length=128), nullable=False),
    sa.Column('assigner', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['patient.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('system', 'value', name='uq_identifier_system_value')
    )
    op.create_index(op.f('ix_patient_identifier_value'), 'patient_identifier', ['value'], unique=False)
    op.create_table('clinical_fact',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=False),
    sa.Column('fact_ref', sa.String(length=32), nullable=False),
    sa.Column('path', sa.String(length=128), nullable=False),
    sa.Column('value_json', sa.JSON(), nullable=True),
    sa.Column('display_value', sa.Text(), nullable=True),
    sa.Column('tier', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('confidence_status', sa.String(length=16), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('confirmed_by_physician', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clinical_fact_fact_ref'), 'clinical_fact', ['fact_ref'], unique=False)
    op.create_index('ix_clinical_fact_path', 'clinical_fact', ['encounter_id', 'path'], unique=False)
    op.create_table('contradiction_record',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=True),
    sa.Column('contradiction_ref', sa.String(length=32), nullable=False),
    sa.Column('rule_id', sa.String(length=32), nullable=False),
    sa.Column('label', sa.Text(), nullable=False),
    sa.Column('side_a_json', sa.JSON(), nullable=True),
    sa.Column('side_b_json', sa.JSON(), nullable=True),
    sa.Column('clarifying_question', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('resolved_by', sa.String(length=255), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patient.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contradiction_record_contradiction_ref'), 'contradiction_record', ['contradiction_ref'], unique=False)
    op.create_table('document_record',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=False),
    sa.Column('document_ref', sa.String(length=32), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=64), nullable=False),
    sa.Column('document_kind', sa.String(length=32), nullable=False),
    sa.Column('pages', sa.Integer(), nullable=False),
    sa.Column('ocr_backend', sa.String(length=32), nullable=False),
    sa.Column('mean_confidence', sa.Float(), nullable=False),
    sa.Column('document_date', sa.Date(), nullable=True),
    sa.Column('verified_by', sa.String(length=255), nullable=True),
    sa.Column('content', sa.LargeBinary(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_record_document_ref'), 'document_record', ['document_ref'], unique=True)
    op.create_table('medication_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('normalized_name', sa.String(length=255), nullable=False),
    sa.Column('dose', sa.String(length=64), nullable=True),
    sa.Column('frequency', sa.String(length=64), nullable=True),
    sa.Column('duration', sa.String(length=64), nullable=True),
    sa.Column('route', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=True),
    sa.Column('source_document_ref', sa.String(length=32), nullable=True),
    sa.Column('source_fact_ref', sa.String(length=32), nullable=True),
    sa.Column('coding_json', sa.JSON(), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patient.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medication_event_normalized_name'), 'medication_event', ['normalized_name'], unique=False)
    op.create_index('ix_medication_patient', 'medication_event', ['patient_id', 'normalized_name'], unique=False)
    op.create_table('observation_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=False),
    sa.Column('analyte_key', sa.String(length=64), nullable=True),
    sa.Column('display', sa.String(length=255), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('value_text', sa.String(length=64), nullable=True),
    sa.Column('unit', sa.String(length=32), nullable=True),
    sa.Column('reference_low', sa.Float(), nullable=True),
    sa.Column('reference_high', sa.Float(), nullable=True),
    sa.Column('range_flag', sa.String(length=16), nullable=False),
    sa.Column('range_source', sa.String(length=32), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=True),
    sa.Column('source_document_ref', sa.String(length=32), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patient.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_observation_event_analyte_key'), 'observation_event', ['analyte_key'], unique=False)
    op.create_index('ix_observation_patient', 'observation_event', ['patient_id', 'analyte_key'], unique=False)
    op.create_table('physician_decision',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=False),
    sa.Column('decision', sa.String(length=32), nullable=False),
    sa.Column('actor', sa.String(length=255), nullable=False),
    sa.Column('detail_json', sa.JSON(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('red_flag_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.String(length=64), nullable=False),
    sa.Column('fired', sa.Boolean(), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=True),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('evidence_json', sa.JSON(), nullable=True),
    sa.Column('evaluated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_red_flag_event_rule_id'), 'red_flag_event', ['rule_id'], unique=False)
    op.create_table('timeline_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('encounter_id', sa.Integer(), nullable=False),
    sa.Column('event_ref', sa.String(length=32), nullable=False),
    sa.Column('occurred_on', sa.Date(), nullable=True),
    sa.Column('date_precision', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('label', sa.Text(), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('source_document_ref', sa.String(length=32), nullable=True),
    sa.Column('source_fact_ref', sa.String(length=32), nullable=True),
    sa.Column('low_confidence', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['encounter_id'], ['encounter.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patient.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_timeline_event_event_ref'), 'timeline_event', ['event_ref'], unique=False)
    op.create_index(op.f('ix_timeline_event_kind'), 'timeline_event', ['kind'], unique=False)
    op.create_index('ix_timeline_patient_time', 'timeline_event', ['patient_id', 'occurred_on'], unique=False)
    op.create_table('extracted_entity',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('source_text', sa.Text(), nullable=False),
    sa.Column('detail_json', sa.JSON(), nullable=True),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('bbox_json', sa.JSON(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('handwritten', sa.Boolean(), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=True),
    sa.Column('verification', sa.String(length=16), nullable=False),
    sa.Column('verified_by', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['document_record.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('source_evidence',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fact_id', sa.Integer(), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('verbatim', sa.Text(), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('modality', sa.String(length=16), nullable=True),
    sa.Column('question_id', sa.String(length=64), nullable=True),
    sa.Column('turn_id', sa.String(length=32), nullable=True),
    sa.Column('asr_confidence', sa.Float(), nullable=True),
    sa.Column('document_ref', sa.String(length=32), nullable=True),
    sa.Column('page', sa.Integer(), nullable=True),
    sa.Column('bbox_json', sa.JSON(), nullable=True),
    sa.Column('ocr_confidence', sa.Float(), nullable=True),
    sa.Column('handwritten', sa.Boolean(), nullable=False),
    sa.Column('human_reading', sa.Text(), nullable=True),
    sa.Column('read_by', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['fact_id'], ['clinical_fact.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_source_evidence_document_ref'), 'source_evidence', ['document_ref'], unique=False)
    op.add_column('session_document', sa.Column('content', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column('session_document', 'content')
    op.drop_index(op.f('ix_source_evidence_document_ref'), table_name='source_evidence')
    op.drop_table('source_evidence')
    op.drop_table('extracted_entity')
    op.drop_index('ix_timeline_patient_time', table_name='timeline_event')
    op.drop_index(op.f('ix_timeline_event_kind'), table_name='timeline_event')
    op.drop_index(op.f('ix_timeline_event_event_ref'), table_name='timeline_event')
    op.drop_table('timeline_event')
    op.drop_index(op.f('ix_red_flag_event_rule_id'), table_name='red_flag_event')
    op.drop_table('red_flag_event')
    op.drop_table('physician_decision')
    op.drop_index('ix_observation_patient', table_name='observation_event')
    op.drop_index(op.f('ix_observation_event_analyte_key'), table_name='observation_event')
    op.drop_table('observation_event')
    op.drop_index('ix_medication_patient', table_name='medication_event')
    op.drop_index(op.f('ix_medication_event_normalized_name'), table_name='medication_event')
    op.drop_table('medication_event')
    op.drop_index(op.f('ix_document_record_document_ref'), table_name='document_record')
    op.drop_table('document_record')
    op.drop_index(op.f('ix_contradiction_record_contradiction_ref'), table_name='contradiction_record')
    op.drop_table('contradiction_record')
    op.drop_index('ix_clinical_fact_path', table_name='clinical_fact')
    op.drop_index(op.f('ix_clinical_fact_fact_ref'), table_name='clinical_fact')
    op.drop_table('clinical_fact')
    op.drop_index(op.f('ix_patient_identifier_value'), table_name='patient_identifier')
    op.drop_table('patient_identifier')
    op.drop_index('ix_encounter_patient_time', table_name='encounter')
    op.drop_index(op.f('ix_encounter_encounter_ref'), table_name='encounter')
    op.drop_table('encounter')
    op.drop_index(op.f('ix_patient_patient_ref'), table_name='patient')
    op.drop_index(op.f('ix_patient_abha_ref'), table_name='patient')
    op.drop_table('patient')

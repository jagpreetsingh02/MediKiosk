"""Fact lifecycle, the encounter's consent link, and frozen report snapshots.

Session 3A. Three changes, each of which the clinical brief needs before it can be assembled
honestly rather than plausibly.

═══ 1. FACTS GET A LIFECYCLE ═══

`clinical_fact` could previously only say what is true now. Add:

    state               stated|confirmed|document|unknown|not_asked|declined
    superseded_by_id    the fact that replaced this one; NULL means live
    valid_from          when this became true — NOT when the row was written
    invalidated_reason  why this stopped applying with nothing replacing it

`state` is not a duplicate of `tier`. `tier` grades evidence and, under Invariant 2, requires
a span that exists — so it cannot express an absence at all. The brief has to tell "we never
asked" apart from "she was asked and declined": both render as no value, and treating them
alike is how a physician comes to read an unasked question as a negative answer.

`superseded_by_id` makes changing an answer append rather than overwrite. That is what keeps
click-to-source honest: if an edit replaced the row, the report could show a corrected value
still pointing at the span of the original statement, and nothing on screen would look wrong.

BACKFILL. `state` is NOT NULL and the table has rows, so a bare ADD COLUMN would abort. Every
existing row is backfilled from its own `tier`, which is the only truthful answer available —
those facts were all recorded from real spans, so their state genuinely is their tier. No row
is guessed into `unknown`.

═══ 2. THE ENCOUNTER REACHES ITS CONSENT ═══

`consent_record` already existed — durable, versioned, scoped, timestamped. What it lacked was
a way back: it is keyed by `session_ref`, and the capture session is purged on submit
(Invariant 6). A committed encounter therefore could not answer "under what consent was this
captured?" without joining through a row that was deliberately destroyed.

`encounter.consent_ref` closes that. Deliberately NOT a foreign key: `consent_record` is a
capture-side table with its own lifecycle, and constraining it from the durable side would
make purging a session depend on what the durable half happens to reference.

BACKFILLED FROM AN EXACT JOIN, NOT A GUESS. An earlier draft of this migration left every
existing encounter NULL, on the reasoning that filling it in would invent consent provenance.
That reasoning was wrong, and checking production is what showed it: the link IS recorded,
just indirectly — `encounter.source_session_ref` and `consent_record.session_ref` are the same
string, written by the same request. Recovering it is not inference.

    UPDATE encounter SET consent_ref = (matching consent_record.consent_ref)

Encounters with no `source_session_ref` stay NULL, correctly: those are the seeded
document-only encounters, which never had a capture session and so never had a consent to
reach. An encounter whose consent_record was purged also stays NULL — absent is said, not
filled.

═══ 3. REPORT SNAPSHOTS ═══

The brief is a pure function of stored rows, so it can always be rebuilt — until the rows
change underneath it. Facts get superseded, entities get corrected, reference ranges get
edited in a later release. Re-rendering then produces something the physician never saw.

`report_snapshot` freezes the payload as rendered, with `report_version` recording which
assembler wrote it. It is a record of what was SHOWN, never a cache: nothing reads it to
avoid work.

═══ RLS, WHICH AUTOGENERATE DOES NOT KNOW ABOUT ═══

`fdb61bb8d5ef` locked every table behind deny-by-default RLS because Supabase's PostgREST
publishes the whole `public` schema over HTTPS to a key that ships in browser code. That
migration worked off a fixed list. A NEW table is not on it, so `report_snapshot` would be
served to anyone who has looked at the network tab — a table holding entire clinical briefs.
Enabling it here is not optional, and it is why this migration is hand-written.

BACKWARD COMPATIBILITY WITH DATA ALREADY IN SUPABASE (this has not been run there yet):
additive only. Three nullable columns, one NOT NULL column with a full backfill, one new
table. No column is dropped, renamed or retyped; no existing row is rewritten except to fill
`state` from `tier`. Code running the previous revision keeps working against this schema,
because everything it reads is untouched.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "e42b36db0938"
down_revision: str | None = "fdb61bb8d5ef"
branch_labels: str | None = None
depends_on: str | None = None

#: Named explicitly so `downgrade()` can drop it. Autogenerate emitted `None` here, which
#: raises on the way back down — a downgrade that cannot run is not a downgrade.
FK_SUPERSEDED = "fk_clinical_fact_superseded_by_id"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ---- 3. report snapshots -------------------------------------------------
    op.create_table(
        "report_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_ref", sa.String(length=32), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("report_version", sa.String(length=16), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounter.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_snapshot_encounter", "report_snapshot", ["encounter_id", "generated_at"]
    )
    op.create_index(
        op.f("ix_report_snapshot_snapshot_ref"), "report_snapshot", ["snapshot_ref"], unique=True
    )

    # A new table is NOT covered by fdb61bb8d5ef's fixed list. Without this it is published
    # by PostgREST to the public anon key. See the module docstring.
    if _is_postgres():
        op.execute("ALTER TABLE public.report_snapshot ENABLE ROW LEVEL SECURITY")
        for role in ("anon", "authenticated"):
            if op.get_bind().exec_driver_sql(
                f"SELECT 1 FROM pg_roles WHERE rolname = '{role}'"  # noqa: S608 — literal above
            ).first():
                op.execute(f"REVOKE ALL ON public.report_snapshot FROM {role}")

    # ---- 1. fact lifecycle ---------------------------------------------------
    # ADDED NULLABLE, BACKFILLED, THEN MADE NOT NULL. A single NOT NULL ADD COLUMN aborts on a
    # populated table, and `server_default` would leave a default sitting on the column
    # forever — every future insert silently acquiring a state nobody chose.
    op.add_column("clinical_fact", sa.Column("state", sa.String(length=16), nullable=True))
    op.execute("UPDATE clinical_fact SET state = tier WHERE state IS NULL")
    op.alter_column("clinical_fact", "state", nullable=False)

    op.add_column("clinical_fact", sa.Column("superseded_by_id", sa.Integer(), nullable=True))
    op.add_column(
        "clinical_fact",
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column("clinical_fact", sa.Column("invalidated_reason", sa.Text(), nullable=True))

    # Existing rows: the fact was true from when it was recorded. `now()` above would date
    # every historical fact to the moment of this migration, which is simply false.
    op.execute("UPDATE clinical_fact SET valid_from = recorded_at")

    op.create_index(
        "ix_clinical_fact_live",
        "clinical_fact",
        ["encounter_id", "superseded_by_id", "invalidated_reason"],
    )
    op.create_index(
        op.f("ix_clinical_fact_superseded_by_id"), "clinical_fact", ["superseded_by_id"]
    )
    # BATCH MODE, because SQLite cannot ALTER a constraint onto an existing table and the test
    # suite builds this whole schema on SQLite. Batch does copy-and-move there and a plain
    # ALTER on PostgreSQL, so both dialects end up with the same constraint rather than the
    # schema quietly differing between what the tests check and what production runs.
    with op.batch_alter_table("clinical_fact") as batch:
        batch.create_foreign_key(
            FK_SUPERSEDED,
            "clinical_fact",
            ["superseded_by_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ---- 2. encounter -> consent --------------------------------------------
    op.add_column("encounter", sa.Column("consent_ref", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_encounter_consent_ref"), "encounter", ["consent_ref"])

    # Recover the link that was already recorded, via the exact session ref both rows carry.
    # Nullable throughout: an encounter with no capture session, or whose consent_record has
    # been purged, keeps NULL rather than acquiring a nearby-looking value.
    # A CORRELATED SUBQUERY, not `UPDATE ... FROM`. The latter is PostgreSQL-only syntax and
    # the test suite builds this whole schema on SQLite, where it fails with a bare syntax
    # error — the tested schema would then differ from the one production runs.
    #
    # `ORDER BY granted_at DESC LIMIT 1` is defensive: `consent_record.session_ref` is indexed
    # but not unique, and a scalar subquery that returns two rows ABORTS the migration on
    # PostgreSQL. There are no duplicates today; a migration should not depend on that staying
    # true. Re-granting narrows consent, so the most recent record is also the correct one.
    op.execute(
        """
        UPDATE encounter
           SET consent_ref = (
                 SELECT c.consent_ref
                   FROM consent_record c
                  WHERE c.session_ref = encounter.source_session_ref
                  ORDER BY c.granted_at DESC
                  LIMIT 1
               )
         WHERE source_session_ref IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_encounter_consent_ref"), table_name="encounter")
    op.drop_column("encounter", "consent_ref")

    with op.batch_alter_table("clinical_fact") as batch:
        batch.drop_constraint(FK_SUPERSEDED, type_="foreignkey")
    op.drop_index(op.f("ix_clinical_fact_superseded_by_id"), table_name="clinical_fact")
    op.drop_index("ix_clinical_fact_live", table_name="clinical_fact")
    op.drop_column("clinical_fact", "invalidated_reason")
    op.drop_column("clinical_fact", "valid_from")
    op.drop_column("clinical_fact", "superseded_by_id")
    op.drop_column("clinical_fact", "state")

    op.drop_index(op.f("ix_report_snapshot_snapshot_ref"), table_name="report_snapshot")
    op.drop_index("ix_report_snapshot_encounter", table_name="report_snapshot")
    op.drop_table("report_snapshot")

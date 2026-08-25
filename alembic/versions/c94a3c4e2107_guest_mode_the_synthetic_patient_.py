"""Guest mode: the synthetic-patient boundary.

One boolean on `patient`, and a query-layer rule built on it — see
`app/modules/encounter/cohort.py`.

WHY A COLUMN RATHER THAN A SEPARATE TABLE OR DATABASE. Guest mode writes real rows into the
real schema on purpose: a demo backed by a parallel fake code path proves nothing about the
product, and every shortcut of that kind in this repo has had to be undone later. The price
is that demo and clinical records share tables, so the boundary has to be explicit and
enforced rather than structural and assumed.

BACKFILL, AND WHAT `false` ACTUALLY CLAIMS. Existing rows get `false`, which means exactly
one thing: *this record was not created by guest mode*. It is NOT a claim that the data is
clinically real. Every patient in this repository is synthetic — docs/CURRENT_STATE.md says
so and that has not changed. The column separates two POPULATIONS so retrieval cannot cross
between them; it does not certify either one.

Added nullable, backfilled, then made NOT NULL. A bare `ADD COLUMN ... NOT NULL` aborts on a
populated table (production has patients), and leaving a `server_default` behind would give
every future insert a value nobody chose — the same trap as `clinical_fact.state` in
e42b36db0938.

REVERSIBLE: dropping the column loses only the population marker. No row is deleted and no
other column is touched, so a downgrade returns the previous revision's exact schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c94a3c4e2107"
down_revision: str | None = "e42b36db0938"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("is_synthetic", sa.Boolean(), nullable=True))
    op.execute("UPDATE patient SET is_synthetic = false WHERE is_synthetic IS NULL")
    op.alter_column("patient", "is_synthetic", nullable=False)
    op.create_index(op.f("ix_patient_is_synthetic"), "patient", ["is_synthetic"])


def downgrade() -> None:
    op.drop_index(op.f("ix_patient_is_synthetic"), table_name="patient")
    op.drop_column("patient", "is_synthetic")

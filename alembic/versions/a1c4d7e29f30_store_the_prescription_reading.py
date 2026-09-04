"""Store the prescription reading beside the entities it was derived from.

The handwriting lane produces two things a physician needs together: the raw OCR
transcription of the page, and the structured interpretation of it. The entities table
already holds the second in pieces, but the raw transcription had nowhere to live — it was
returned once in the upload response and then lost, so the physician's screen could show what
MediKiosk *thought* the prescription said and never what it appeared to say.

Stored rather than recomputed. The reading is a record of what the patient was shown and
confirmed; re-deriving it later against an edited `medications.json` would quietly rewrite
what happened.

Revision ID: a1c4d7e29f30
Revises: fdb61bb8d5ef
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4d7e29f30"
down_revision: str | None = "fdb61bb8d5ef"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Nullable, with no backfill: documents uploaded before this migration genuinely have no
    # stored reading, and a default of `{}` would claim they were interpreted and found empty.
    op.add_column("session_document", sa.Column("reading_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("session_document", "reading_json")

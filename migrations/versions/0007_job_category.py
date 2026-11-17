"""job category: SWE, ML / AI, Data, … (app/core/categories.py)

Set by Gemini when it reads a job, or from the title before then. Empty until either.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=20), nullable=True))
        batch_op.create_index("ix_jobs_category", ["category"])


def downgrade() -> None:
    # SQLite drops a column in place; batch mode would rebuild "jobs", which other tables
    # point at, and fail on their foreign keys.
    op.drop_index("ix_jobs_category", table_name="jobs")
    op.execute("ALTER TABLE jobs DROP COLUMN category")

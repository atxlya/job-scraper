"""dashboard: search index, degree flag, source origin

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.pipeline.derived import FTS_DDL

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("degree_only", sa.String(length=40), nullable=True))
        batch_op.create_index("ix_jobs_kind", ["is_tech", "is_internship", "state"])
        batch_op.create_index("ix_jobs_posted", ["posted_at"])
    with op.batch_alter_table("sources", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("origin", sa.String(length=20), nullable=False, server_default="registry")
        )
    op.execute(FTS_DDL)  # filled by `python -m app.cli reindex`


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS jobs_fts")
    with op.batch_alter_table("sources", schema=None) as batch_op:
        batch_op.drop_column("origin")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_jobs_posted")
        batch_op.drop_index("ix_jobs_kind")
        batch_op.drop_column("degree_only")

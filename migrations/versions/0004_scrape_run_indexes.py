"""scrape_runs indexes for the Sources page

Each source's newest runs, and the nightly full runs across all sources.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scrape_runs", schema=None) as batch_op:
        batch_op.create_index("ix_scrape_runs_source_started", ["source_id", "started_at"])
        batch_op.create_index("ix_scrape_runs_kind_started", ["kind", "started_at"])


def downgrade() -> None:
    with op.batch_alter_table("scrape_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_scrape_runs_kind_started")
        batch_op.drop_index("ix_scrape_runs_source_started")

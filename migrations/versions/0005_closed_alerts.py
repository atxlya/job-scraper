"""closed_alerts: one "🔒 Closed" message per liked or applied job

Jobs that are already closed and tagged liked/applied are recorded as handled, so the
first run after the upgrade doesn't report closures from before it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "closed_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.execute(
        "INSERT INTO closed_alerts (job_id, message_id, sent_at) "
        "SELECT j.id, NULL, COALESCE(j.closed_at, j.last_seen_at) FROM jobs j "
        "JOIN job_user_state u ON u.job_id = j.id "
        "WHERE j.state = 'closed' AND u.tag IN ('liked', 'applied')"
    )


def downgrade() -> None:
    op.drop_table("closed_alerts")

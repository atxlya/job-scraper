"""application stages: OA, interview, offer, rejected after Applied

A stage sits next to the tag (job_user_state.stage), so an applied job keeps the tag
"applied" whatever its stage. Each step is a tag_history row with from/to stage.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("job_user_state", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stage", sa.String(length=20), nullable=True))
    with op.batch_alter_table("tag_history", schema=None) as batch_op:
        batch_op.add_column(sa.Column("from_stage", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("to_stage", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tag_history", schema=None) as batch_op:
        batch_op.drop_column("to_stage")
        batch_op.drop_column("from_stage")
    with op.batch_alter_table("job_user_state", schema=None) as batch_op:
        batch_op.drop_column("stage")

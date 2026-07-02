"""add plan_notice column to users

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One-shot dashboard notice written by the downgrade sweep
    # (app/shared/plans.enforce_plan_limits) when a plan change cancelled
    # or slowed the user's recurring searches. Cleared after display.
    op.add_column("users", sa.Column("plan_notice", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "plan_notice")

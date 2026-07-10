"""Drop the quiet-hours columns from users.

The quiet-hours feature is removed entirely: it silently suppressed all
notifications (phantom 22:00-08:00 window written without user intent, no
enable toggle, UTC-vs-local mismatch). See issue #184.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "quiet_end")
    op.drop_column("users", "quiet_start")


def downgrade() -> None:
    op.add_column("users", sa.Column("quiet_start", sa.String(length=5), nullable=True))
    op.add_column("users", sa.Column("quiet_end", sa.String(length=5), nullable=True))

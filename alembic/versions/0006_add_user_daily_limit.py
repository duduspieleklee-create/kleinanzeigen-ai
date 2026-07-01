"""add user daily_limit

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="3"),
    )
    # The admin account is exempt from the daily cap (0 = unlimited).
    op.execute("UPDATE users SET daily_limit = 0 WHERE username = 'admin'")


def downgrade() -> None:
    op.drop_column("users", "daily_limit")

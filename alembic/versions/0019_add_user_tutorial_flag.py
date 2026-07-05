"""add users.has_completed_tutorial

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # False until the user has clicked through (or skipped) the first-login
    # guided tutorial. New signups get the default (false) and see it once.
    op.add_column(
        "users",
        sa.Column("has_completed_tutorial", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Existing accounts predate the tutorial — don't show it retroactively.
    op.execute("UPDATE users SET has_completed_tutorial = true")


def downgrade() -> None:
    op.drop_column("users", "has_completed_tutorial")

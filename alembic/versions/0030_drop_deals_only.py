"""Drop the deals-only notification column from users.

The "Nur bei großartigen Angeboten benachrichtigen" (deals-only) feature is
removed entirely: it silently suppressed all notifications for Basic users who
flipped the toggle (deal badges are a Core/Pro-gated feature, so they never saw
a deal highlight and received nothing at all). See issue #185.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "deals_only_enabled")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "deals_only_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

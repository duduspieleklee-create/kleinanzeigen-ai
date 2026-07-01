"""add missing model columns: completed_at, raw_data, is_active

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scrape_tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scrape_results",
        sa.Column("raw_data", sa.JSON(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Integer(), nullable=True, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
    op.drop_column("scrape_results", "raw_data")
    op.drop_column("scrape_tasks", "completed_at")

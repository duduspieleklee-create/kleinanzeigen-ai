"""Add last_run_at to scrape_tasks for the dashboard "zuletzt geprüft" label.

Revision ID: 0028
Revises: 5f17314ef463
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0028"
down_revision: Union[str, None] = "5f17314ef463"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scrape_tasks",
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scrape_tasks", "last_run_at")

"""Add last_summary to scrape_tasks for the Smart Alerts feature.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_tasks", sa.Column("last_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scrape_tasks", "last_summary")

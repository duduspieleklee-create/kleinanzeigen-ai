"""Add error_message to scrape_tasks for user-facing failure detail.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_tasks", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scrape_tasks", "error_message")

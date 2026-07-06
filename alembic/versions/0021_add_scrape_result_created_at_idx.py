"""Add created_at index to scrape_results for ordered query performance.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "scrape_results_created_at_idx",
        "scrape_results",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("scrape_results_created_at_idx", table_name="scrape_results")

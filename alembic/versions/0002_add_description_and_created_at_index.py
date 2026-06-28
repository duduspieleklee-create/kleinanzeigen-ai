"""add description column and created_at index to scrape_results

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add description column for storing raw listing text scraped from the page
    op.add_column(
        "scrape_results",
        sa.Column("description", sa.Text(), nullable=True),
    )

    # Index created_at for efficient time-range queries (e.g. "results from last 24h")
    op.create_index(
        "ix_scrape_results_created_at",
        "scrape_results",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scrape_results_created_at", table_name="scrape_results")
    op.drop_column("scrape_results", "description")

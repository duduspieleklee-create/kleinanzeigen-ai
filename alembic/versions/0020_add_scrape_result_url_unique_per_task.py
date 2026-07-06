"""Enforce unique scrape result URL per task with DB-level protection.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove duplicates first: keep the earliest row per (task_id, url),
    # delete later duplicates so the partial unique index can be created.
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        bind.execute("""
            DELETE FROM scrape_results
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM scrape_results
                WHERE url IS NOT NULL
                GROUP BY task_id, url
            )
        """)
    elif dialect == "postgresql":
        bind.execute("""
            DELETE FROM scrape_results a
            USING scrape_results b
            WHERE a.id > b.id
              AND a.task_id = b.task_id
              AND a.url IS NOT NULL
              AND b.url IS NOT NULL
              AND a.url = b.url
        """)
    else:
        op.execute("""
            DELETE FROM scrape_results
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM scrape_results
                WHERE url IS NOT NULL
                GROUP BY task_id, url
            )
        """)

    op.create_index(
        "scrape_results_task_id_url_idx",
        "scrape_results",
        ["task_id", "url"],
        unique=True,
        postgresql_where=sa.text("url IS NOT NULL"),
        sqlite_where=sa.text("url IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("scrape_results_task_id_url_idx", table_name="scrape_results")

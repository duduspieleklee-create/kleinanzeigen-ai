"""AdminSearch: filter parity with regular search form + rotation support.

Adds ad_type/poster_type/condition/shipping (matching url_builder's filter
set), makes keywords nullable (category-only reference searches), and adds
is_rotation_managed for the automatic category-rotation task.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("admin_searches", "keywords", existing_type=sa.String(255), nullable=True)
    op.add_column("admin_searches", sa.Column("ad_type", sa.String(20), nullable=True))
    op.add_column("admin_searches", sa.Column("poster_type", sa.String(20), nullable=True))
    op.add_column("admin_searches", sa.Column("condition", sa.String(20), nullable=True))
    op.add_column("admin_searches", sa.Column("shipping", sa.String(10), nullable=True))
    op.add_column(
        "admin_searches",
        sa.Column(
            "is_rotation_managed",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("admin_searches", "is_rotation_managed")
    op.drop_column("admin_searches", "shipping")
    op.drop_column("admin_searches", "condition")
    op.drop_column("admin_searches", "poster_type")
    op.drop_column("admin_searches", "ad_type")
    op.alter_column("admin_searches", "keywords", existing_type=sa.String(255), nullable=False)

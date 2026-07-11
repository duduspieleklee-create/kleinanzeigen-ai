"""Add the geocode_cache table for the results map.

The dashboard map resolves each result's free-text location to coordinates.
That is now done server-side and cached here (one row per distinct location)
so Nominatim is queried at most once per place, respecting its usage policy —
see app/shared/geocoding.py. A NULL lat/lon row is a negative cache entry
(looked up, no hit) so unresolvable strings aren't re-queried.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geocode_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_geocode_cache_location",
        "geocode_cache",
        ["location"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_geocode_cache_location", table_name="geocode_cache")
    op.drop_table("geocode_cache")

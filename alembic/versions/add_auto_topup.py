"""Add auto_topup_enabled column to users table

Revision ID: add_auto_topup
Revises: add_payg_credits
Create Date: 2026-07-17

Idempotent: safe to run whether or not the column already exists.
"""
from alembic import op
import sqlalchemy as sa


revision = "add_auto_topup"
down_revision = "add_payg_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}

    if "auto_topup_enabled" not in existing_cols:
        op.add_column(
            "users",
            sa.Column(
                "auto_topup_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "auto_topup_enabled" in existing_cols:
        op.drop_column("users", "auto_topup_enabled")

"""Add PAYG credits: credits_paid column + credit_purchases table

Revision ID: add_payg_credits
Revises: 761ef2bab6ae
Create Date: 2026-07-12

Idempotent: safe to run whether or not the columns/tables already exist
(the VPS DB may already carry them from an earlier PAYG-branch deploy).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_payg_credits"
down_revision = "761ef2bab6ae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    existing_tables = set(inspector.get_table_names())

    # Add credits_paid column to users (default 0, NOT NULL) — skip if present.
    if "credits_paid" not in existing_cols:
        op.add_column(
            "users",
            sa.Column("credits_paid", sa.Integer(), nullable=False, server_default="0"),
        )

    # Create credit_purchases table — skip if present.
    if "credit_purchases" not in existing_tables:
        op.create_table(
            "credit_purchases",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("stripe_payment_intent_id", sa.String(120), index=True),
            sa.Column("package_id", sa.String(50), nullable=False),
            sa.Column("credits_amount", sa.Integer(), nullable=False),
            sa.Column("amount_paid", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="EUR"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "credit_purchases" in existing_tables:
        op.drop_table("credit_purchases")
    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "credits_paid" in existing_cols:
        op.drop_column("users", "credits_paid")

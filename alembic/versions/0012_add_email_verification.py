"""add email verification columns to users

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "users",
        sa.Column("verify_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("verify_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_verify_token", "users", ["verify_token"], unique=False)

    # Grandfather every existing account as verified: they all predate email
    # verification (bootstrap admin, Google allow-list users, early password
    # signups) and must not be locked out of search retroactively.
    op.execute("UPDATE users SET email_verified = true")


def downgrade() -> None:
    op.drop_index("ix_users_verify_token", table_name="users")
    op.drop_column("users", "verify_token_expires_at")
    op.drop_column("users", "verify_token")
    op.drop_column("users", "email_verified")

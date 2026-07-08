"""Enable email notifications by default for new users.

Changes User.email_notifications_enabled server_default from 'false' to 'true'.
Existing users keep their current preference (no data migration).

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision = "0025_enable_email_notifications_by_default"
down_revision: Union[str, None] = "0024_admin_search_parity_and_rotation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change the server default for new users only (existing users unaffected)
    op.alter_column(
        "users",
        "email_notifications_enabled",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default="true",
    )


def downgrade() -> None:
    # Restore original default
    op.alter_column(
        "users",
        "email_notifications_enabled",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default="false",
    )

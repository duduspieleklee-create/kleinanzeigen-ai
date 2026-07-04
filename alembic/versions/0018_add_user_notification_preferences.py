"""Add user notification preference columns.

The settings page has always rendered toggles for push/email notifications,
deals-only mode, and quiet hours, and its JS posted changes to
POST /api/settings/notifications - but that endpoint never existed and the
User model had no columns to store the values, so every toggle silently did
nothing (settings_page() only ever saw getattr() defaults).

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("push_notifications_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("email_notifications_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("deals_only_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("quiet_start", sa.String(5), nullable=True))
    op.add_column("users", sa.Column("quiet_end", sa.String(5), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "quiet_end")
    op.drop_column("users", "quiet_start")
    op.drop_column("users", "deals_only_enabled")
    op.drop_column("users", "email_notifications_enabled")
    op.drop_column("users", "push_notifications_enabled")

"""add notification delivery tracking/retry

Stores per-channel delivery state so senders can retry with backoff and
dashboards/logs can show channel-specific failures instead of only the
current best-effort in-memory summary.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy import text

revision = "0026_add_notification_deliveries"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    row = bind.execute(text("SELECT to_regclass('public.notification_deliveries')"))
    if row.scalar() is not None:
        return
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("scrape_tasks.id", ondelete="SET NULL")),
        sa.Column("channel", sa.String(length=20), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", index=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("retry_after", sa.DateTime(timezone=True)),
        sa.Column("raw_payload", JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("notification_deliveries")

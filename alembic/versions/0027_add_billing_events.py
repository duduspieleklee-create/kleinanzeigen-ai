"""add billing event idempotency/audit table

Stores the raw Stripe event payload and processing outcome so webhook
handlers can deduplicate replays, retain rollback evidence, and avoid
partial plan-state updates when one step after another fails.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0027_add_billing_events"
down_revision = "0026_add_notification_deliveries"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    row = bind.execute(text("SELECT to_regclass('public.billing_events')"))
    if row.scalar() is not None:
        return
    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=120), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=100), nullable=False, index=True),
        sa.Column("stripe_customer_id", sa.String(length=100), index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending", index=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("payload", sa.JSON()),
    )
    op.create_index(
        "billing_events_event_id_idx",
        "billing_events",
        ["event_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("billing_events_event_id_idx", table_name="billing_events")
    op.drop_table("billing_events")

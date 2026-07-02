"""add users.trial_used and scrape_tasks.baseline_done

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # True once the user has ever started a subscription — the 3-day Core
    # trial (billing checkout) is for first-time subscribers only.
    op.add_column(
        "users",
        sa.Column("trial_used", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Anyone already holding a subscription is not a first-time subscriber.
    op.execute(
        "UPDATE users SET trial_used = true WHERE stripe_subscription_id IS NOT NULL"
    )

    # False until a search's first successful (baseline) run completed. The
    # baseline run is free: no credits charged, no push sent.
    op.add_column(
        "scrape_tasks",
        sa.Column("baseline_done", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Existing searches already had their (historically charged) first run —
    # don't retroactively grant them a free baseline pass.
    op.execute("UPDATE scrape_tasks SET baseline_done = true")


def downgrade() -> None:
    op.drop_column("scrape_tasks", "baseline_done")
    op.drop_column("users", "trial_used")

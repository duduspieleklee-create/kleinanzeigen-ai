"""expand_models_for_dashboard_updates

Revision ID: 03e00e3fe015
Revises: 0014
Create Date: 2026-07-02 19:37:38.636752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Favoriten-System: Tabelle für favorisierte Ergebnisse
    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["result_id"], ["scrape_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "result_id", name="unique_user_favorite")
    )

    # 2. Token-Usage Tracking: Tabelle für täglichen Verbrauch pro Suche
    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.ForeignKeyConstraint(["task_id"], ["scrape_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "date", name="unique_task_daily_usage")
    )

    # 3. Trust Score & Verkäuferdaten in scrape_results erweitern
    op.add_column("scrape_results", sa.Column("seller_id", sa.String(length=50), nullable=True))
    op.add_column("scrape_results", sa.Column("seller_name", sa.String(length=100), nullable=True))
    op.add_column("scrape_results", sa.Column("seller_rating", sa.String(length=50), nullable=True)) # e.g. "TOP"
    op.add_column("scrape_results", sa.Column("seller_badges", sa.String(length=255), nullable=True)) # e.g. "Freundlich,Zuverlässig"
    op.add_column("scrape_results", sa.Column("trust_score", sa.Integer(), nullable=True))

    # 4. E-Mail Notification Option in scrape_tasks
    op.add_column("scrape_tasks", sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default="false"))

def downgrade() -> None:
    op.drop_column("scrape_tasks", "email_notifications")
    op.drop_column("scrape_results", "trust_score")
    op.drop_column("scrape_results", "seller_badges")
    op.drop_column("scrape_results", "seller_rating")
    op.drop_column("scrape_results", "seller_name")
    op.drop_column("scrape_results", "seller_id")
    op.drop_table("token_usage")
    op.drop_table("favorites")

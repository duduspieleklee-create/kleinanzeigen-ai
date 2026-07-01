"""add premium fields and welcome_tasks table

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("premium_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users", sa.Column("welcome_completed_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "welcome_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_key", sa.String(length=50), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "task_key", name="uq_welcome_user_task"),
    )
    op.create_index(op.f("ix_welcome_tasks_id"), "welcome_tasks", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_welcome_tasks_id"), table_name="welcome_tasks")
    op.drop_table("welcome_tasks")
    op.drop_column("users", "welcome_completed_at")
    op.drop_column("users", "premium_until")

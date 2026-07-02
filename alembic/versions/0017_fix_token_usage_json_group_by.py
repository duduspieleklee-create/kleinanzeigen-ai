"""Fix PostgreSQL json GROUP BY error in token tracking.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-02 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration documents the fix to get_token_usage_by_task() query.
    # The fix was in app/shared/token_tracking.py, not in the database schema.
    # We removed GROUP BY on the JSON column (ScrapeTask.parameters) which caused:
    # "could not identify an equality operator for type json"
    # Now we only group by task_id, which is deterministic.
    pass


def downgrade() -> None:
    # No schema changes to revert
    pass

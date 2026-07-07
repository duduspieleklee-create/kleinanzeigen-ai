"""fix_push_notifications_default_to_false

Revision ID: 52ad6a85a96f
Revises: 0025
Create Date: 2026-07-07 12:40:43.230476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52ad6a85a96f'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change the server_default from "true" to "false" for new users
    op.alter_column('users', 'push_notifications_enabled',
                    existing_type=sa.Boolean(),
                    server_default='false',
                    existing_nullable=False)
    
    # Note: We intentionally do NOT update existing users' values.
    # Users who already have push_notifications_enabled=true made that choice
    # (either explicitly or by accepting the previous default), so we respect it.
    # Only new registrations from this point forward will default to false.


def downgrade() -> None:
    # Revert server_default back to "true"
    op.alter_column('users', 'push_notifications_enabled',
                    existing_type=sa.Boolean(),
                    server_default='true',
                    existing_nullable=False)
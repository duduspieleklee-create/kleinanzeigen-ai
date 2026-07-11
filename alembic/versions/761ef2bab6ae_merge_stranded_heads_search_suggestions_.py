"""merge stranded heads (search_suggestions + fraud_alerts + 0031)

Revision ID: 761ef2bab6ae
Revises: 0031, add_search_suggestions_table, add_fraud_alerts_table
Create Date: 2026-07-11 18:21:48.336165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '761ef2bab6ae'
down_revision: Union[str, None] = ('0031', 'add_search_suggestions_table', 'add_fraud_alerts_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

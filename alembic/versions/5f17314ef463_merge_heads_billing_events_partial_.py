"""merge heads: billing_events + partial_failed/parse_error

Revision ID: 5f17314ef463
Revises: 0027_add_billing_events, a43ba04bf415
Create Date: 2026-07-10 20:47:27.776014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f17314ef463'
down_revision: Union[str, None] = ('0027_add_billing_events', 'a43ba04bf415')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

"""Add account age and listings count for enhanced trust score calculation.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to scrape_results table
    op.add_column('scrape_results', sa.Column('seller_active_since', sa.Integer(), nullable=True))
    op.add_column('scrape_results', sa.Column('seller_listings_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove the columns
    op.drop_column('scrape_results', 'seller_listings_count')
    op.drop_column('scrape_results', 'seller_active_since')

"""
Migration für die Suchvorschläge-Tabelle.
Tabelle: search_suggestions
- Speichert Suchvorschläge und deren Nutzungshäufigkeit.
"""

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = 'add_search_suggestions_table'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Tabelle für Suchvorschläge erstellen
    op.create_table(
        'search_suggestions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('keyword', sa.String(length=255), nullable=False, index=True),
        sa.Column('suggestion', sa.String(length=255), nullable=False),
        sa.Column('suggestion_type', sa.String(length=50), nullable=False),
        sa.Column('usage_count', sa.Integer(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index(op.f('ix_search_suggestions_keyword'), 'search_suggestions', ['keyword'], unique=False)


def downgrade():
    # Tabelle für Suchvorschläge löschen
    op.drop_table('search_suggestions')
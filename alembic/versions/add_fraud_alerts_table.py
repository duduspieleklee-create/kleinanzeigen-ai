"""
Migration für die Betrugsalarm-Tabelle.

Tabelle: fraud_alerts
- Speichert Warnungen für betrügerische Anzeigen.
- Wird automatisch bei der Betrugserkennung aktualisiert.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Revision identifiers, used by Alembic.
revision = 'add_fraud_alerts_table'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Tabelle für Betrugsalarm erstellen
    op.create_table(
        'fraud_alerts',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('ad_id', sa.Integer(), nullable=False, index=True),
        sa.Column('fraud_level', sa.String(length=20), nullable=False),
        sa.Column('warnings', postgresql.JSONB(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index(op.f('ix_fraud_alerts_ad_id'), 'fraud_alerts', ['ad_id'], unique=False)


def downgrade():
    # Tabelle für Betrugsalarm löschen
    op.drop_table('fraud_alerts')
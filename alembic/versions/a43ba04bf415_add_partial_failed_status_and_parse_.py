"""add_partial_failed_status_and_parse_error

Revision ID: a43ba04bf415
Revises: 52ad6a85a96f
Create Date: 2026-07-07 12:55:09.093791

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a43ba04bf415'
down_revision: Union[str, None] = '52ad6a85a96f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_column(table: str, column: str) -> bool:
    insp = _inspector()
    return column in [c["name"] for c in insp.get_columns(table)]


def _has_index(table: str, index: str) -> bool:
    insp = _inspector()
    return index in [i["name"] for i in insp.get_indexes(table)]


def _has_constraint(table: str, constraint: str) -> bool:
    insp = _inspector()
    return constraint in [c["name"] for c in insp.get_unique_constraints(table)]


def upgrade() -> None:
    # Idempotent: this migration was orphaned as a second head for a while and
    # may already be partially applied on some databases, so guard every step.
    if _has_constraint('favorites', 'unique_user_favorite'):
        op.drop_constraint('unique_user_favorite', 'favorites', type_='unique')
    if not _has_index('favorites', 'ix_favorites_id'):
        op.create_index(op.f('ix_favorites_id'), 'favorites', ['id'], unique=False)
    if _has_index('push_subscriptions', 'ix_push_subscriptions_user_id'):
        op.drop_index('ix_push_subscriptions_user_id', table_name='push_subscriptions')
    # task_id is NOT NULL in the models; only tighten if it is currently nullable.
    op.alter_column('scrape_results', 'task_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    # Add parse_error column to track per-listing validation/parse errors
    if not _has_column('scrape_results', 'parse_error'):
        op.add_column('scrape_results', sa.Column('parse_error', sa.Text(), nullable=True))
    for idx in ('ix_scrape_results_created_at', 'ix_scrape_results_task_id',
                'scrape_results_created_at_idx', 'scrape_results_task_id_url_idx'):
        if _has_index('scrape_results', idx):
            op.drop_index(idx, table_name='scrape_results')
    op.alter_column('scrape_tasks', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    if _has_index('scrape_tasks', 'ix_scrape_tasks_status'):
        op.drop_index('ix_scrape_tasks_status', table_name='scrape_tasks')
    if _has_constraint('token_usage', 'unique_task_daily_usage'):
        op.drop_constraint('unique_task_daily_usage', 'token_usage', type_='unique')
    if not _has_index('token_usage', 'ix_token_usage_id'):
        op.create_index(op.f('ix_token_usage_id'), 'token_usage', ['id'], unique=False)


def downgrade() -> None:
    if _has_index('token_usage', 'ix_token_usage_id'):
        op.drop_index(op.f('ix_token_usage_id'), table_name='token_usage')
    if not _has_constraint('token_usage', 'unique_task_daily_usage'):
        op.create_unique_constraint('unique_task_daily_usage', 'token_usage', ['task_id', 'date'])
    if not _has_index('scrape_tasks', 'ix_scrape_tasks_status'):
        op.create_index('ix_scrape_tasks_status', 'scrape_tasks', ['status'], unique=False)
    op.alter_column('scrape_tasks', 'user_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    if not _has_index('scrape_results_task_id_url_idx'):
        op.create_index('scrape_results_task_id_url_idx', 'scrape_results', ['task_id', 'url'], unique=True, postgresql_where='(url IS NOT NULL)')
    if not _has_index('scrape_results_created_at_idx'):
        op.create_index('scrape_results_created_at_idx', 'scrape_results', ['created_at'], unique=False)
    if not _has_index('ix_scrape_results_task_id'):
        op.create_index('ix_scrape_results_task_id', 'scrape_results', ['task_id'], unique=False)
    if not _has_index('ix_scrape_results_created_at'):
        op.create_index('ix_scrape_results_created_at', 'scrape_results', ['created_at'], unique=False)
    if _has_column('scrape_results', 'parse_error'):
        op.drop_column('scrape_results', 'parse_error')
    op.alter_column('scrape_results', 'task_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    if not _has_index('push_subscriptions', 'ix_push_subscriptions_user_id'):
        op.create_index('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id'], unique=False)
    if not _has_index('favorites', 'ix_favorites_id'):
        op.drop_index(op.f('ix_favorites_id'), table_name='favorites')
    if not _has_constraint('favorites', 'unique_user_favorite'):
        op.create_unique_constraint('unique_user_favorite', 'favorites', ['user_id', 'result_id'])

"""research tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('research_tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('motorcycle_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('spec', 'insight', name='researchkind', native_enum=False, length=10), nullable=False),
    sa.Column('fact_key', sa.String(length=50), nullable=False),
    sa.Column('state', sa.Enum('queued', 'searching', 'found', 'not_found', 'failed', name='researchtaskstate', native_enum=False, length=10), server_default='queued', nullable=False),
    sa.Column('failure_reason', sa.Enum('not_released_yet', 'no_reliable_source', 'unresolved_conflict', 'not_applicable', 'retries_exhausted', name='failurereason', native_enum=False, length=20), nullable=True),
    sa.Column('recheck_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result_spec_value_id', sa.Integer(), nullable=True),
    sa.Column('result_insight_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['motorcycle_id'], ['motorcycles.id'], name=op.f('fk_research_tasks_motorcycle_id_motorcycles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['result_insight_id'], ['insights.id'], name=op.f('fk_research_tasks_result_insight_id_insights'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['result_spec_value_id'], ['spec_values.id'], name=op.f('fk_research_tasks_result_spec_value_id_spec_values'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_research_tasks')),
    sa.UniqueConstraint('motorcycle_id', 'kind', 'fact_key', name=op.f('uq_research_tasks_motorcycle_id_kind_fact_key'))
    )


def downgrade() -> None:
    op.drop_table('research_tasks')

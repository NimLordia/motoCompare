"""profile tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_table('profiles',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('unit_system', sa.Enum('metric', 'imperial', 'mixed', name='unitsystempreference', native_enum=False, length=10), server_default='metric', nullable=False),
    sa.Column('market', sa.String(length=20), nullable=True),
    sa.Column('riding_style', sa.String(length=50), nullable=True),
    sa.Column('priority_factors', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_profiles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_profiles'))
    )
    op.create_table('garage_bikes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('motorcycle_id', sa.Integer(), nullable=False),
    sa.Column('is_current', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('nickname', sa.String(length=50), nullable=True),
    sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['motorcycle_id'], ['motorcycles.id'], name=op.f('fk_garage_bikes_motorcycle_id_motorcycles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_garage_bikes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_garage_bikes')),
    sa.UniqueConstraint('user_id', 'motorcycle_id', name=op.f('uq_garage_bikes_user_id_motorcycle_id'))
    )
    op.create_index('uq_garage_bikes_one_current_per_user', 'garage_bikes', ['user_id'], unique=True, postgresql_where=sa.text('is_current'))
    op.create_table('dream_bikes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('motorcycle_id', sa.Integer(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['motorcycle_id'], ['motorcycles.id'], name=op.f('fk_dream_bikes_motorcycle_id_motorcycles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_dream_bikes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dream_bikes')),
    sa.UniqueConstraint('user_id', 'motorcycle_id', name=op.f('uq_dream_bikes_user_id_motorcycle_id'))
    )


def downgrade() -> None:
    op.drop_table('dream_bikes')
    op.drop_index('uq_garage_bikes_one_current_per_user', table_name='garage_bikes')
    op.drop_table('garage_bikes')
    op.drop_table('profiles')
    op.drop_table('users')

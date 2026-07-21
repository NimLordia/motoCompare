"""initial catalog schema

Revision ID: 0001
Revises: 
Create Date: 2026-07-21 15:29:21.827942

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('manufacturers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_manufacturers')),
    sa.UniqueConstraint('name', name=op.f('uq_manufacturers_name'))
    )
    op.create_table('spec_definitions',
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('canonical_unit', sa.String(length=20), nullable=False),
    sa.Column('value_type', sa.Enum('number', 'text', name='valuetype', native_enum=False, length=10), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('is_core', sa.Boolean(), server_default='false', nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_spec_definitions'))
    )
    op.create_table('models',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('manufacturer_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturers.id'], name=op.f('fk_models_manufacturer_id_manufacturers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_models')),
    sa.UniqueConstraint('manufacturer_id', 'name', name=op.f('uq_models_manufacturer_id_name'))
    )
    op.create_table('motorcycles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('model_id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('trim', sa.String(length=50), server_default='', nullable=False),
    sa.Column('market', sa.String(length=20), server_default='', nullable=False),
    sa.ForeignKeyConstraint(['model_id'], ['models.id'], name=op.f('fk_motorcycles_model_id_models')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_motorcycles')),
    sa.UniqueConstraint('model_id', 'year', 'trim', 'market', name=op.f('uq_motorcycles_model_id_year_trim_market'))
    )
    op.create_table('insights',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('motorcycle_id', sa.Integer(), nullable=False),
    sa.Column('topic', sa.String(length=40), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('source_type', sa.Enum('official', 'tested', 'community', 'estimated', name='sourcetype', native_enum=False, length=10), nullable=False),
    sa.Column('source_urls', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['motorcycle_id'], ['motorcycles.id'], name=op.f('fk_insights_motorcycle_id_motorcycles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_insights')),
    sa.UniqueConstraint('motorcycle_id', 'topic', name=op.f('uq_insights_motorcycle_id_topic'))
    )
    op.create_table('spec_values',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('motorcycle_id', sa.Integer(), nullable=False),
    sa.Column('spec_key', sa.String(length=50), nullable=False),
    sa.Column('value_num', sa.Float(), nullable=True),
    sa.Column('value_text', sa.String(length=200), nullable=True),
    sa.Column('source_type', sa.Enum('official', 'tested', 'community', 'estimated', name='sourcetype', native_enum=False, length=10), nullable=False),
    sa.Column('source_url', sa.String(length=500), nullable=True),
    sa.Column('source_note', sa.String(length=500), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['motorcycle_id'], ['motorcycles.id'], name=op.f('fk_spec_values_motorcycle_id_motorcycles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['spec_key'], ['spec_definitions.key'], name=op.f('fk_spec_values_spec_key_spec_definitions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_spec_values')),
    sa.UniqueConstraint('motorcycle_id', 'spec_key', 'source_type', name=op.f('uq_spec_values_motorcycle_id_spec_key_source_type'))
    )


def downgrade() -> None:
    op.drop_table('spec_values')
    op.drop_table('insights')
    op.drop_table('motorcycles')
    op.drop_table('models')
    op.drop_table('spec_definitions')
    op.drop_table('manufacturers')

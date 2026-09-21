"""slice 5: species_analytics, plot_analytics, variance_components

Cache de lectura de los modelos mixtos (lme4::glmer binomial) ya ajustados
sobre el dataset de referencia. Lo llena `scripts/load_analytics.py` desde
`backend/data/processed/efectos_aleatorios*.csv`; la API solo lee.

No hay FK hacia `projects` a proposito (ver models.SpeciesAnalytics): los
efectos se estimaron sobre el dataset completo del programa, no sobre un
proyecto concreto. Cuando exista multi-proyecto real, eso pide un ADR.

Revision ID: b1c4a7f20e51
Revises: a8888efd3ae8
Create Date: 2026-09-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1c4a7f20e51'
down_revision: str | None = 'a8888efd3ae8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'species_analytics',
        sa.Column('species_name', sa.String(length=300), nullable=False),
        # Estancamiento: efecto en log-odds, OR = exp(efecto), IC ya exponenciado
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('or_stall_lo', sa.Float(), nullable=True),
        sa.Column('or_stall_hi', sa.Float(), nullable=True),
        sa.Column('sig_stall', sa.Boolean(), nullable=True),
        # Mortalidad
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('or_mort_lo', sa.Float(), nullable=True),
        sa.Column('or_mort_hi', sa.Float(), nullable=True),
        sa.Column('sig_mort', sa.Boolean(), nullable=True),
        # Metadatos
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('gremio', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('species_name'),
    )
    # Los dos rankings de la UI ordenan por OR; el filtro por gremio es el
    # unico facet del dashboard. Indices intencionales (AGENTS.md).
    op.create_index('ix_species_analytics_or_stall', 'species_analytics', ['or_stall'])
    op.create_index('ix_species_analytics_or_mort', 'species_analytics', ['or_mort'])
    op.create_index('ix_species_analytics_gremio', 'species_analytics', ['gremio'])

    op.create_table(
        'plot_analytics',
        sa.Column('plot_code', sa.String(length=100), nullable=False),
        sa.Column('localidad', sa.String(length=200), nullable=True),
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('plot_code'),
    )
    op.create_index('ix_plot_analytics_localidad', 'plot_analytics', ['localidad'])

    op.create_table(
        'variance_components',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=20), nullable=False),
        sa.Column('grouping', sa.String(length=20), nullable=False),
        sa.Column('variance', sa.Float(), nullable=False),
        sa.Column('sd', sa.Float(), nullable=False),
        sa.Column('icc', sa.Float(), nullable=False),
        sa.Column('n_levels', sa.Integer(), nullable=True),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('n_events', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model', 'grouping', name='uq_variance_model_grouping'),
    )


def downgrade() -> None:
    op.drop_table('variance_components')
    op.drop_index('ix_plot_analytics_localidad', table_name='plot_analytics')
    op.drop_table('plot_analytics')
    op.drop_index('ix_species_analytics_gremio', table_name='species_analytics')
    op.drop_index('ix_species_analytics_or_mort', table_name='species_analytics')
    op.drop_index('ix_species_analytics_or_stall', table_name='species_analytics')
    op.drop_table('species_analytics')

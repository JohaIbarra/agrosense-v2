"""E5: referente cientifico versionado (reference_models + efectos por version)

docs/superpowers/plans/2026-09-27-e5-referente-cientifico.md, docs/04-vision-producto.md §6.7.

Reemplaza `species_analytics` / `plot_analytics` (Slice 5, sin version) por
`reference_species_effects` / `reference_plot_effects`, y anade
`reference_model_id` a `variance_components`. Las tres tablas de efectos
ahora cuelgan de `reference_models`, que registra CADA corrida de los
modelos mixtos con su `is_active`.

Se dropean y recrean en vez de ALTER: no hay datos de produccion que
preservar (deploy bloqueado, ver Roadmap) y la PK cambia de columna simple a
compuesta (version, nivel) porque ahora conviven varias versiones.

Revision ID: c7e9f2a4b6d8
Revises: a2c4e6f8b1d3
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7e9f2a4b6d8'
down_revision: str | None = 'a2c4e6f8b1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reference_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('source_dataset', sa.String(length=300), nullable=False),
        sa.Column('method', sa.String(length=100), nullable=False),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.drop_table('species_analytics')
    op.drop_table('plot_analytics')
    op.drop_table('variance_components')

    op.create_table(
        'reference_species_effects',
        sa.Column('reference_model_id', sa.Integer(), nullable=False),
        sa.Column('species_name', sa.String(length=300), nullable=False),
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('or_stall_lo', sa.Float(), nullable=True),
        sa.Column('or_stall_hi', sa.Float(), nullable=True),
        sa.Column('sig_stall', sa.Boolean(), nullable=True),
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('or_mort_lo', sa.Float(), nullable=True),
        sa.Column('or_mort_hi', sa.Float(), nullable=True),
        sa.Column('sig_mort', sa.Boolean(), nullable=True),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('gremio', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('reference_model_id', 'species_name'),
        sa.ForeignKeyConstraint(
            ['reference_model_id'], ['reference_models.id'], ondelete='CASCADE'
        ),
    )
    op.create_index(
        'ix_reference_species_effects_or_stall', 'reference_species_effects', ['or_stall']
    )
    op.create_index(
        'ix_reference_species_effects_or_mort', 'reference_species_effects', ['or_mort']
    )
    op.create_index(
        'ix_reference_species_effects_gremio', 'reference_species_effects', ['gremio']
    )

    op.create_table(
        'reference_plot_effects',
        sa.Column('reference_model_id', sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint('reference_model_id', 'plot_code'),
        sa.ForeignKeyConstraint(
            ['reference_model_id'], ['reference_models.id'], ondelete='CASCADE'
        ),
    )
    op.create_index(
        'ix_reference_plot_effects_localidad', 'reference_plot_effects', ['localidad']
    )

    op.create_table(
        'variance_components',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference_model_id', sa.Integer(), nullable=False),
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
        sa.UniqueConstraint(
            'reference_model_id', 'model', 'grouping', name='uq_variance_model_grouping'
        ),
        sa.ForeignKeyConstraint(
            ['reference_model_id'], ['reference_models.id'], ondelete='CASCADE'
        ),
    )
    op.create_index(
        'ix_variance_components_reference_model_id', 'variance_components', ['reference_model_id']
    )


def downgrade() -> None:
    op.drop_index(
        'ix_variance_components_reference_model_id', table_name='variance_components'
    )
    op.drop_table('variance_components')
    op.drop_index(
        'ix_reference_plot_effects_localidad', table_name='reference_plot_effects'
    )
    op.drop_table('reference_plot_effects')
    op.drop_index(
        'ix_reference_species_effects_gremio', table_name='reference_species_effects'
    )
    op.drop_index(
        'ix_reference_species_effects_or_mort', table_name='reference_species_effects'
    )
    op.drop_index(
        'ix_reference_species_effects_or_stall', table_name='reference_species_effects'
    )
    op.drop_table('reference_species_effects')
    op.drop_table('reference_models')

    # Recrea las tablas del Slice 5 tal como las dejo b1c4a7f20e51, para que
    # el downgrade sea simetrico de verdad (incluye variance_components en su
    # forma vieja, sin reference_model_id, y los indices originales).
    op.create_table(
        'species_analytics',
        sa.Column('species_name', sa.String(length=300), nullable=False),
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('or_stall_lo', sa.Float(), nullable=True),
        sa.Column('or_stall_hi', sa.Float(), nullable=True),
        sa.Column('sig_stall', sa.Boolean(), nullable=True),
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('or_mort_lo', sa.Float(), nullable=True),
        sa.Column('or_mort_hi', sa.Float(), nullable=True),
        sa.Column('sig_mort', sa.Boolean(), nullable=True),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('gremio', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('species_name'),
    )
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

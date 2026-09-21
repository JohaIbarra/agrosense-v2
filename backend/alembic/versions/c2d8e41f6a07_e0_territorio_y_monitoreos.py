"""E0: territorio (predios, parcelas) y monitoreos como entidades

docs/superpowers/plans/2026-09-21-e0-fundacion-datos.md, tarea T5.

- `properties` (predios) y `plots` (unidades de muestreo) normalizan lo que
  hasta ahora se repetia en cada arbol (`trees.locality`, `trees.plot_id`) y
  guardan las dimensiones que la ingesta descartaba: diseno floristico,
  coberturas, unidad de monitoreo y codigo de unidad de muestreo.
- `monitorings` convierte el numero de monitoreo en entidad, con fecha.
  `observations.campaign` pasa a `observations.monitoring_id`.
- `campaign_file_monitorings`: un archivo acumulado trae varios monitoreos.

Orden: crear tablas -> BACKFILL desde las columnas viejas -> restricciones ->
borrar las columnas viejas. El backfill se escribe aunque las tablas del
slice 2 esten vacias en produccion (verificado el 2026-09-21): cualquier base
con datos debe migrar sin perdida, y `downgrade` la devuelve a su estado.

Los archivos ya cargados NO se enlazan a monitoreos en el backfill: hasta E0
no se registraba que monitoreos traia cada archivo, y enlazarlos a todos
seria inventar provenance.

Revision ID: c2d8e41f6a07
Revises: b1c4a7f20e51
Create Date: 2026-09-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2d8e41f6a07'
down_revision: str | None = 'b1c4a7f20e51'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Clave de parcela para los datos que llegaron antes de E0 (sin codigo de
# unidad): la misma regla que domain.rules.plot_key, escrita en SQL.
_LEGACY_PLOT_KEY = (
    "CASE WHEN {t}.locality IS NULL THEN {t}.plot_id "
    "ELSE {t}.locality || '/' || {t}.plot_id END"
)


def upgrade() -> None:
    # ── 1. Tablas nuevas ────────────────────────────────────────────────────
    op.create_table(
        'properties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('vereda', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'name', name='uq_property_project_name'),
    )
    op.create_index('ix_properties_project_id', 'properties', ['project_id'])

    op.create_table(
        'plots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=True),
        sa.Column('code', sa.String(length=300), nullable=False),
        sa.Column('sampling_unit_code', sa.String(length=200), nullable=True),
        sa.Column('plot_label', sa.String(length=100), nullable=True),
        sa.Column('monitoring_unit', sa.String(length=200), nullable=True),
        sa.Column('floristic_design', sa.String(length=300), nullable=True),
        sa.Column('associated_cover', sa.String(length=300), nullable=True),
        sa.Column('establishment_cover', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'code', name='uq_plot_project_code'),
    )
    op.create_index('ix_plots_project_id', 'plots', ['project_id'])
    op.create_index('ix_plots_property_id', 'plots', ['property_id'])

    op.create_table(
        'monitorings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('monitoring_date', sa.Date(), nullable=True),
        sa.Column('field_crew', sa.String(length=500), nullable=True),
        sa.Column('recorder', sa.String(length=300), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.CheckConstraint('number >= 1', name='ck_monitoring_number_positive'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'number', name='uq_monitoring_project_number'),
    )
    op.create_index('ix_monitorings_project_id', 'monitorings', ['project_id'])

    op.create_table(
        'campaign_file_monitorings',
        sa.Column('campaign_file_id', sa.Integer(), nullable=False),
        sa.Column('monitoring_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['campaign_file_id'], ['campaign_files.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['monitoring_id'], ['monitorings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('campaign_file_id', 'monitoring_id'),
    )

    # ── 2. Columnas nuevas (todavia nullable, para poder rellenarlas) ───────
    with op.batch_alter_table('campaign_files') as batch:
        batch.add_column(sa.Column('source_project_label', sa.String(500), nullable=True))
        batch.add_column(sa.Column('source_event', sa.String(200), nullable=True))
        batch.add_column(sa.Column('source_field_crew', sa.String(500), nullable=True))
        batch.add_column(sa.Column('source_recorder', sa.String(300), nullable=True))

    with op.batch_alter_table('trees') as batch:
        batch.add_column(sa.Column('plot_row_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('observations') as batch:
        batch.add_column(sa.Column('monitoring_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('field_notes', sa.Text(), nullable=True))

    # ── 3. Backfill desde las columnas viejas ───────────────────────────────
    op.execute(
        "INSERT INTO properties (project_id, name) "
        "SELECT DISTINCT project_id, locality FROM trees WHERE locality IS NOT NULL"
    )
    op.execute(
        "INSERT INTO plots (project_id, property_id, code, plot_label) "
        f"SELECT DISTINCT t.project_id, p.id, {_LEGACY_PLOT_KEY.format(t='t')}, t.plot_id "
        "FROM trees t "
        "LEFT JOIN properties p ON p.project_id = t.project_id AND p.name = t.locality "
        "WHERE t.plot_id IS NOT NULL"
    )
    op.execute(
        "UPDATE trees SET plot_row_id = ("
        "  SELECT pl.id FROM plots pl"
        "  WHERE pl.project_id = trees.project_id"
        f"   AND pl.code = {_LEGACY_PLOT_KEY.format(t='trees')}"
        ") WHERE plot_id IS NOT NULL"
    )
    op.execute(
        "INSERT INTO monitorings (project_id, number) "
        "SELECT DISTINCT t.project_id, o.campaign "
        "FROM observations o JOIN trees t ON t.id = o.tree_row_id"
    )
    op.execute(
        "UPDATE observations SET monitoring_id = ("
        "  SELECT m.id FROM monitorings m JOIN trees t ON t.project_id = m.project_id"
        "  WHERE t.id = observations.tree_row_id AND m.number = observations.campaign"
        ")"
    )

    # ── 4. Restricciones y limpieza ─────────────────────────────────────────
    with op.batch_alter_table('observations') as batch:
        batch.drop_constraint('uq_observation_tree_campaign', type_='unique')
        batch.drop_column('campaign')
        batch.alter_column('monitoring_id', existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            'fk_observations_monitoring_id', 'monitorings',
            ['monitoring_id'], ['id'], ondelete='CASCADE',
        )
        batch.create_unique_constraint(
            'uq_observation_tree_monitoring', ['tree_row_id', 'monitoring_id']
        )
        batch.create_index('ix_observations_monitoring_id', ['monitoring_id'])

    with op.batch_alter_table('trees') as batch:
        batch.drop_column('plot_id')
        batch.drop_column('locality')
        batch.create_foreign_key(
            'fk_trees_plot_row_id', 'plots', ['plot_row_id'], ['id'], ondelete='SET NULL'
        )
        batch.create_index('ix_trees_plot_row_id', ['plot_row_id'])


def downgrade() -> None:
    # Devolver las columnas viejas y rellenarlas antes de borrar lo nuevo
    with op.batch_alter_table('trees') as batch:
        batch.add_column(sa.Column('plot_id', sa.String(100), nullable=True))
        batch.add_column(sa.Column('locality', sa.String(200), nullable=True))

    op.execute(
        "UPDATE trees SET "
        "  plot_id = (SELECT pl.plot_label FROM plots pl WHERE pl.id = trees.plot_row_id),"
        "  locality = (SELECT p.name FROM plots pl JOIN properties p ON p.id = pl.property_id"
        "              WHERE pl.id = trees.plot_row_id)"
    )

    with op.batch_alter_table('trees') as batch:
        batch.drop_index('ix_trees_plot_row_id')
        batch.drop_constraint('fk_trees_plot_row_id', type_='foreignkey')
        batch.drop_column('plot_row_id')

    with op.batch_alter_table('observations') as batch:
        batch.add_column(sa.Column('campaign', sa.Integer(), nullable=True))

    op.execute(
        "UPDATE observations SET campaign = ("
        "  SELECT m.number FROM monitorings m WHERE m.id = observations.monitoring_id)"
    )

    with op.batch_alter_table('observations') as batch:
        batch.drop_index('ix_observations_monitoring_id')
        batch.drop_constraint('uq_observation_tree_monitoring', type_='unique')
        batch.drop_constraint('fk_observations_monitoring_id', type_='foreignkey')
        batch.drop_column('monitoring_id')
        batch.drop_column('field_notes')
        batch.alter_column('campaign', existing_type=sa.Integer(), nullable=False)
        batch.create_unique_constraint(
            'uq_observation_tree_campaign', ['tree_row_id', 'campaign']
        )

    with op.batch_alter_table('campaign_files') as batch:
        batch.drop_column('source_recorder')
        batch.drop_column('source_field_crew')
        batch.drop_column('source_event')
        batch.drop_column('source_project_label')

    op.drop_table('campaign_file_monitorings')
    op.drop_index('ix_monitorings_project_id', table_name='monitorings')
    op.drop_table('monitorings')
    op.drop_index('ix_plots_property_id', table_name='plots')
    op.drop_index('ix_plots_project_id', table_name='plots')
    op.drop_table('plots')
    op.drop_index('ix_properties_project_id', table_name='properties')
    op.drop_table('properties')

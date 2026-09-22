"""E10a: indices espectrales (NDVI) por predio y fecha

docs/adr/011-indices-espectrales.md.

`satellite_index_values`: una lectura por (proyecto, predio, indice, escena).
A diferencia del mapa —que se deriva en 20 ms y no se guarda— esta cifra
viene de un tercero, cuesta una peticion de red y no se puede reproducir si
el proveedor deja de servir la escena: por eso se guarda con su procedencia.

Tabla nueva: no toca datos existentes y el downgrade solo la elimina (las
lecturas se vuelven a pedir).

Revision ID: a2c4e6f8b1d3
Revises: f1b2c3d4e5a7
Create Date: 2026-09-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2c4e6f8b1d3'
down_revision: str | None = 'f1b2c3d4e5a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'satellite_index_values',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('property_name', sa.String(200), nullable=False),
        sa.Column('index_name', sa.String(20), nullable=False),
        sa.Column('scene_id', sa.String(200), nullable=False),
        sa.Column('acquired_at', sa.Date(), nullable=False),
        sa.Column('cloud_cover', sa.Float(), nullable=True),
        sa.Column('mean_value', sa.Float(), nullable=False),
        sa.Column('median_value', sa.Float(), nullable=True),
        sa.Column('min_value', sa.Float(), nullable=True),
        sa.Column('max_value', sa.Float(), nullable=True),
        sa.Column('std_value', sa.Float(), nullable=True),
        sa.Column('valid_pixels', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(120), nullable=False),
        sa.Column('polygon_hash', sa.String(64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'project_id', 'property_name', 'index_name', 'scene_id',
            name='uq_index_value_scene',
        ),
        sa.CheckConstraint('valid_pixels >= 0', name='ck_index_value_pixels'),
    )
    op.create_index(
        'ix_satellite_index_values_project',
        'satellite_index_values',
        ['project_id', 'index_name', 'acquired_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_satellite_index_values_project', table_name='satellite_index_values')
    op.drop_table('satellite_index_values')

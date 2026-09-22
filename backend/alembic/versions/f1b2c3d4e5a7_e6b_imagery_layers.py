"""E6b: capas de imagen (ortofoto) por proyecto

docs/superpowers/plans/2026-09-22-e6-mapa-del-predio.md, ADR-009.

`imagery_layers`: una plantilla de teselas por capa, no el archivo. Tabla
nueva: no toca datos existentes y el downgrade solo la elimina (las capas se
vuelven a registrar pegando su dirección).

Revision ID: f1b2c3d4e5a7
Revises: e5f1a2b3c4d6
Create Date: 2026-09-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1b2c3d4e5a7'
down_revision: str | None = 'e5f1a2b3c4d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'imagery_layers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('tile_template', sa.String(1000), nullable=False),
        sa.Column('attribution', sa.String(300), nullable=True),
        sa.Column('min_zoom', sa.Integer(), nullable=True),
        sa.Column('max_zoom', sa.Integer(), nullable=True),
        sa.Column('opacity', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'name', name='uq_imagery_layer_project_name'),
    )
    op.create_index('ix_imagery_layers_project_id', 'imagery_layers', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_imagery_layers_project_id', table_name='imagery_layers')
    op.drop_table('imagery_layers')

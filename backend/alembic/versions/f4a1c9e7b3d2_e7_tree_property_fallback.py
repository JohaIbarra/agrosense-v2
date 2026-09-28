"""E7 fix wave (item 2): trees.property_id, predio independiente de la parcela

docs/superpowers/sdd/2026-09-27-e7-estancados/final-fixes-brief.md, item 2.

Un arbol sin parcela reconocida (`domain.rules.plot_key` = None: sin
`Codigo de unidad muestreo` NI `ID Parcela`) pero CON `LOCALIDAD` perdia su
predio al servir (`TreeRow.locality` solo miraba `plot.property`), aunque la
ruta de entrenamiento (directa desde el Excel) si lo conservaba. Esta
columna guarda el predio del arbol de forma independiente de la parcela.

Revision ID: f4a1c9e7b3d2
Revises: e7c1a3b5d7f9
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f4a1c9e7b3d2'
down_revision: str | None = 'e7c1a3b5d7f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('trees') as batch:
        batch.add_column(sa.Column('property_id', sa.Integer(), nullable=True))
        batch.create_index('ix_trees_property_id', ['property_id'])
        batch.create_foreign_key(
            'fk_trees_property_id_properties',
            'properties',
            ['property_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('trees') as batch:
        batch.drop_constraint('fk_trees_property_id_properties', type_='foreignkey')
        batch.drop_index('ix_trees_property_id')
        batch.drop_column('property_id')

"""E3: snapshot del analisis exploratorio por monitoreo

docs/superpowers/plans/2026-09-22-e2e3-carga-y-analisis.md, ADR-008.

`monitoring_analyses`: un snapshot JSON por monitoreo, con la version del
calculo y la huella de los datos que lo produjeron. Tabla nueva: no toca
datos existentes, y el downgrade solo la elimina (los snapshots se
recalculan desde los datos crudos).

Revision ID: e5f1a2b3c4d6
Revises: d9a3b7c15e24
Create Date: 2026-09-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f1a2b3c4d6'
down_revision: str | None = 'd9a3b7c15e24'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'monitoring_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('monitoring_id', sa.Integer(), nullable=False),
        sa.Column('analysis_version', sa.String(50), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['monitoring_id'], ['monitorings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('monitoring_id', name='uq_monitoring_analysis_monitoring'),
    )
    op.create_index(
        'ix_monitoring_analyses_project_id', 'monitoring_analyses', ['project_id']
    )


def downgrade() -> None:
    op.drop_index('ix_monitoring_analyses_project_id', table_name='monitoring_analyses')
    op.drop_table('monitoring_analyses')

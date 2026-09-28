"""E7: stall_assessments (deteccion de estancados, UC-AN4)

docs/superpowers/plans/2026-09-27-e7-estancados.md, docs/adr/013-modelo-estancamiento-offline.md.

Un snapshot por monitoreo (UNIQUE(monitoring_id)): recalcular REEMPLAZA,
igual que `monitoring_analyses` (ADR-008).

Revision ID: e7c1a3b5d7f9
Revises: d4b8f2a6c9e1
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e7c1a3b5d7f9'
down_revision: str | None = 'd4b8f2a6c9e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'stall_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('monitoring_id', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('artifact_sha256', sa.String(length=64), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['monitoring_id'], ['monitorings.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('monitoring_id', name='uq_stall_assessment_monitoring'),
    )
    op.create_index('ix_stall_assessments_project_id', 'stall_assessments', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_stall_assessments_project_id', table_name='stall_assessments')
    op.drop_table('stall_assessments')

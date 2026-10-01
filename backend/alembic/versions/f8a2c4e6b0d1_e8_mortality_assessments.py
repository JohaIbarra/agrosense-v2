"""E8: mortality_assessments (riesgo de mortalidad)

docs/superpowers/plans/2026-09-30-e8-mortalidad.md, docs/adr/014-mortalidad-modelo-hibrido.md.

Un snapshot por monitoreo (UNIQUE(monitoring_id)): recalcular REEMPLAZA,
igual que `stall_assessments` (ADR-008).

Revision ID: f8a2c4e6b0d1
Revises: b3d5f7a9c1e2
Create Date: 2026-09-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f8a2c4e6b0d1'
down_revision: str | None = 'b3d5f7a9c1e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'mortality_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('monitoring_id', sa.Integer(), nullable=False),
        sa.Column('model_kind', sa.String(length=10), nullable=False),
        sa.Column('model_version', sa.String(length=120), nullable=False),
        sa.Column('artifact_sha256', sa.String(length=64), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.Column('rules_version', sa.String(length=50), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['monitoring_id'], ['monitorings.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('monitoring_id', name='uq_mortality_assessment_monitoring'),
    )
    op.create_index('ix_mortality_assessments_project_id', 'mortality_assessments', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_mortality_assessments_project_id', table_name='mortality_assessments')
    op.drop_table('mortality_assessments')

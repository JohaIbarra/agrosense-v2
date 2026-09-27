"""E9: ai_reports (borrador de informe generado por IA, UC-IA1/2/3)

docs/superpowers/plans/2026-09-27-e9-ia-ollama.md, docs/04-vision-producto.md §6.10.

Un borrador por monitoreo (UNIQUE(monitoring_id)): regenerar REEMPLAZA,
igual que `monitoring_analyses`. Cubre resumen + comparacion porque ambos
viven en el mismo snapshot (ADR-008) -- no hay tabla `comparison_analyses`
aparte.

Revision ID: d4b8f2a6c9e1
Revises: c7e9f2a4b6d8
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4b8f2a6c9e1'
down_revision: str | None = 'c7e9f2a4b6d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('monitoring_id', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('prompt_version', sa.String(length=50), nullable=False),
        sa.Column('input_hash', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('unverified_numbers', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['monitoring_id'], ['monitorings.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('monitoring_id', name='uq_ai_report_monitoring'),
    )
    op.create_index('ix_ai_reports_project_id', 'ai_reports', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_ai_reports_project_id', table_name='ai_reports')
    op.drop_table('ai_reports')

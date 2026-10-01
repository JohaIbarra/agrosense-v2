"""E8 (deuda D): campaign_files.content guarda el Excel crudo

ADR-004 §5 y AGENTS.md (Data provenance) piden poder recomputar una ingesta
desde su archivo original; hasta aqui solo se guardaba el sha256. ADR-014:
el modelo propio de mortalidad se entrena con datos del usuario, y un modelo
cuyo dataset de origen no se puede recuperar no es reproducible.

Nullable: las cargas anteriores a esta migracion no tienen el archivo.

Revision ID: b3d5f7a9c1e2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b3d5f7a9c1e2'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('campaign_files') as batch:
        batch.add_column(sa.Column('content', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('campaign_files') as batch:
        batch.drop_column('content')

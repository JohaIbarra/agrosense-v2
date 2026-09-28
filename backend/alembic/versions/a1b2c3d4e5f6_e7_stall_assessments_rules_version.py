"""E7 fix wave (item 4): stall_assessments.rules_version

docs/superpowers/sdd/2026-09-27-e7-estancados/final-fixes-brief.md, item 4.

ALERT_BUDGET, PERSISTENT_STALL_INTERVALS y la definicion de la etiqueta
(domain/stall_rules.RULES_VERSION) pueden cambiar sin reentrenar el modelo.
Sin esta columna, el snapshot solo se invalidaba por model_version /
artifact_sha256 / input_hash y serviria una regla de negocio desactualizada.

Server default con la version vigente al momento de esta migracion: no hay
filas todavia en ningun entorno desplegado de E7 (rama sin mergear), pero un
default explicito deja la migracion segura igual si las hubiera.

Revision ID: a1b2c3d4e5f6
Revises: f4a1c9e7b3d2
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f4a1c9e7b3d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INITIAL_RULES_VERSION = '2026-09-27-e7.1'


def upgrade() -> None:
    with op.batch_alter_table('stall_assessments') as batch:
        batch.add_column(
            sa.Column(
                'rules_version',
                sa.String(length=50),
                nullable=False,
                server_default=_INITIAL_RULES_VERSION,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('stall_assessments') as batch:
        batch.drop_column('rules_version')

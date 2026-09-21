"""E1: ingenieros y proyectos con propietario

docs/superpowers/plans/2026-09-21-e1-identidad-proyectos.md, ADR-006.

- `engineers`: perfil del ingeniero; `id` = `sub` del token de Supabase Auth.
- `projects`: `owner_id` (obligatorio), `project_code` asignado por AgroSense,
  los campos aprobados en D7 y `coordinate_srid` (9377 por defecto, ADR-005).
- El nombre del proyecto deja de ser unico GLOBAL y pasa a ser unico por
  ingeniero: dos ingenieros pueden tener «Restauracion Guayabal».

`owner_id` es NOT NULL y no hay forma honesta de asignar un propietario a
proyectos que ya existan, asi que la migracion se NIEGA a correr si hay
proyectos (en produccion la tabla esta vacia, verificado antes de aplicar).
Adivinar el propietario seria regalar los datos de un ingeniero a otro.

Revision ID: d9a3b7c15e24
Revises: c2d8e41f6a07
Create Date: 2026-09-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd9a3b7c15e24'
down_revision: str | None = 'c2d8e41f6a07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# La migracion inicial creo UNIQUE(name) SIN nombre. En Postgres se llama
# `projects_name_key`; en SQLite se le da nombre con esta convencion para que
# el modo batch pueda encontrarla.
_SQLITE_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}

_NEW_PROJECT_COLUMNS = [
    sa.Column('contract_code', sa.String(100), nullable=True),
    sa.Column('objective', sa.Text(), nullable=True),
    sa.Column('executing_org', sa.String(200), nullable=True),
    sa.Column('contracting_entity', sa.String(200), nullable=True),
    sa.Column('department', sa.String(100), nullable=True),
    sa.Column('municipality', sa.String(100), nullable=True),
    sa.Column('intervention_type', sa.String(50), nullable=True),
    sa.Column('area_ha', sa.Float(), nullable=True),
    sa.Column('planted_individuals', sa.Integer(), nullable=True),
    sa.Column('planting_density', sa.Float(), nullable=True),
    sa.Column('establishment_date', sa.Date(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('legal_framework', sa.String(50), nullable=True),
    sa.Column('environmental_authority', sa.String(200), nullable=True),
    sa.Column('status', sa.String(20), nullable=False, server_default='activo'),
    sa.Column('coordinate_srid', sa.Integer(), nullable=False, server_default='9377'),
]


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == 'sqlite'


def upgrade() -> None:
    existentes = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM projects")).scalar()
    if existentes:
        raise RuntimeError(
            f"Hay {existentes} proyecto(s) sin propietario. E1 exige que cada proyecto "
            "pertenezca a un ingeniero y esta migracion no puede adivinarlo. Asigne "
            "los proyectos (o eliminelos) antes de migrar."
        )

    op.create_table(
        'engineers',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('email', sa.String(320), nullable=True),
        sa.Column('full_name', sa.String(200), nullable=True),
        sa.Column('professional_license', sa.String(100), nullable=True),
        sa.Column('organization', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    batch_kwargs = {'naming_convention': _SQLITE_NAMING} if _is_sqlite() else {}
    unique_name = 'uq_projects_name' if _is_sqlite() else 'projects_name_key'
    with op.batch_alter_table('projects', **batch_kwargs) as batch:
        batch.drop_constraint(unique_name, type_='unique')
        batch.add_column(sa.Column('project_code', sa.String(40), nullable=False))
        batch.add_column(sa.Column('owner_id', sa.String(36), nullable=False))
        for col in _NEW_PROJECT_COLUMNS:
            batch.add_column(col.copy())
        batch.create_unique_constraint('uq_project_code', ['project_code'])
        batch.create_unique_constraint('uq_project_owner_name', ['owner_id', 'name'])
        batch.create_foreign_key(
            'fk_projects_owner_id', 'engineers', ['owner_id'], ['id'], ondelete='RESTRICT'
        )
        batch.create_index('ix_projects_owner_id', ['owner_id'])


def downgrade() -> None:
    batch_kwargs = {'naming_convention': _SQLITE_NAMING} if _is_sqlite() else {}
    unique_name = 'uq_projects_name' if _is_sqlite() else 'projects_name_key'
    with op.batch_alter_table('projects', **batch_kwargs) as batch:
        batch.drop_index('ix_projects_owner_id')
        batch.drop_constraint('fk_projects_owner_id', type_='foreignkey')
        batch.drop_constraint('uq_project_owner_name', type_='unique')
        batch.drop_constraint('uq_project_code', type_='unique')
        for col in reversed(_NEW_PROJECT_COLUMNS):
            batch.drop_column(col.name)
        batch.drop_column('owner_id')
        batch.drop_column('project_code')
        batch.create_unique_constraint(unique_name, ['name'])
    op.drop_table('engineers')

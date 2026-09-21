"""Smoke contra Supabase REAL. Se pide a proposito:

    pytest -m supabase

Excluido de la corrida por defecto (pyproject: addopts `-m "not supabase"`)
porque el session pooler tiene ~200ms RTT y colgaba cada `pytest`.

Que verifica que SQLite NO puede verificar:
  1. que la migracion de Alembic esta realmente aplicada en Postgres y su
     schema coincide con los models de `adapters/db/models.py`;
  2. que el driver de ADR-002 (psycopg3) conecta de verdad;
  3. que un ciclo escritura/lectura/borrado funciona en el dialecto real.

Deliberadamente NO reingiere las 856 filas del dataset: eso son ~4000
inserts a 200ms = minutos de pooler, y la verificacion de volumen ya corre
local en `tests/db/test_repository.py`. Aqui importa el dialecto, no el tamano.

Cada test limpia lo que crea, incluso si falla (la DB es compartida).
"""
from __future__ import annotations

import os

import pytest

from agrosense.adapters.db.models import Base, ObservationRow, Project, TreeRow
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.application.dtos import CampaignData
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from tests.auth.keys import ENGINEER_A as OWNER

pytestmark = [
    pytest.mark.supabase,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL ausente (backend/.env)",
    ),
]

SMOKE_PROJECT = "smoke-supabase-agrosense"


@pytest.fixture()
def session():
    from agrosense.adapters.db.session import get_session_factory

    factory = get_session_factory()
    s = factory()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def clean_smoke_project(session):
    """Borra el proyecto de smoke antes y despues (idempotente ante cortes)."""

    def _drop():
        proj = session.query(Project).filter_by(name=SMOKE_PROJECT).first()
        if proj:
            session.delete(proj)  # cascade: trees + observations + campaigns
            session.commit()

    _drop()
    yield SMOKE_PROJECT
    _drop()


def smoke_campaign() -> CampaignData:
    return CampaignData(
        trees=[Tree(tree_id="SMOKE-1", species="Cedrela odorata", locality="Guayabal")],
        observations=[
            Observation(
                tree_id="SMOKE-1",
                campaign=1,
                height_m=1.25,
                crown_diameter_m=0.8,
                dap_cm=None,
                dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
                phytosanitary="Sano",
                alive=True,
                colonization=None,
            )
        ],
        warnings=[],
        mapping_version="smoke",
    )


def test_connects_with_psycopg3_driver(session):
    """ADR-002: un solo driver, y es el que llega a la DB real."""
    assert session.get_bind().dialect.driver == "psycopg"


def test_migration_schema_matches_models(session):
    """La migracion aplicada en Supabase no se desvio de los models.

    Es la verificacion que justifica que este test exista: si alguien cambia
    un model y olvida `alembic revision`, los tests locales (create_all
    desde metadata) siguen verdes y solo esto lo detecta.
    """
    from sqlalchemy import inspect

    inspector = inspect(session.get_bind())
    real_tables = set(inspector.get_table_names())

    for table_name, table in Base.metadata.tables.items():
        assert table_name in real_tables, (
            f"tabla '{table_name}' no existe en Supabase: falta aplicar la migracion"
        )
        real_cols = {c["name"] for c in inspector.get_columns(table_name)}
        expected_cols = {c.name for c in table.columns}
        assert expected_cols <= real_cols, (
            f"columnas ausentes en '{table_name}': {sorted(expected_cols - real_cols)} "
            "— el model cambio sin migracion"
        )


def test_round_trip_write_read_delete(session, clean_smoke_project):
    """Ciclo completo en el dialecto real, con provenance y cascada."""
    prepo = ProjectRepository(session)
    proj = prepo.create(
        owner_id=OWNER, name=clean_smoke_project, locality="Guayabal", description="smoke"
    )

    stats = CampaignRepository(session).save_ingest(
        project_id=proj.id,
        result=smoke_campaign(),
        filename="smoke.xlsx",
        sha256="5" * 64,
    )
    assert stats["trees"] == 1
    assert stats["observations"] == 1

    assert session.query(TreeRow).filter_by(project_id=proj.id).count() == 1
    campaigns = prepo.get_campaigns(proj.id)
    assert len(campaigns) == 1
    assert campaigns[0].sha256 == "5" * 64

    # cascada real de Postgres
    session.delete(proj)
    session.commit()
    assert session.query(TreeRow).filter_by(project_id=proj.id).count() == 0
    assert (
        session.query(ObservationRow)
        .join(TreeRow)
        .filter(TreeRow.project_id == proj.id)
        .count()
        == 0
    )


def test_duplicate_file_rejected_by_real_constraint(session, clean_smoke_project):
    """El UNIQUE (project_id, sha256) existe en la DB, no solo en el model."""
    prepo = ProjectRepository(session)
    proj = prepo.create(owner_id=OWNER, name=clean_smoke_project)
    crepo = CampaignRepository(session)

    crepo.save_ingest(proj.id, smoke_campaign(), "smoke.xlsx", "6" * 64)
    with pytest.raises(ValueError, match="DUPLICATE_FILE"):
        crepo.save_ingest(proj.id, smoke_campaign(), "smoke.xlsx", "6" * 64)

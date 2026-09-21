"""Smoke de E0 contra Supabase REAL (`pytest -m supabase`).

Verifica en Postgres lo que SQLite no garantiza del todo: las restricciones con
nombre (CHECK de numero de monitoreo, UNIQUE por proyecto), el tipo DATE y las
cascadas reales. Usa una campana pequena a proposito: reingerir los 856
arboles en cada smoke tardaria minutos contra el pooler.

Cada test limpia lo que crea, incluso si falla (la DB es compartida).
"""
from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from agrosense.adapters.db.models import (
    MonitoringRow,
    PlotRow,
    Project,
    PropertyRow,
    TreeRow,
)
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.application.dtos import CampaignData, FileMetadata
from agrosense.domain.entities import Observation, StatusSemantic, Tree

pytestmark = [
    pytest.mark.supabase,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"), reason="DATABASE_URL ausente (backend/.env)"
    ),
]

SMOKE_PROJECT = "smoke-e0-agrosense"


@pytest.fixture()
def session():
    from agrosense.adapters.db.session import get_session_factory

    s = get_session_factory()()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def project(session):
    def _drop():
        p = session.query(Project).filter_by(name=SMOKE_PROJECT).first()
        if p:
            session.delete(p)
            session.commit()

    _drop()
    p = ProjectRepository(session).create(name=SMOKE_PROJECT, locality=None, description=None)
    yield p
    session.rollback()
    _drop()


def _campaign() -> CampaignData:
    trees = [
        Tree(
            tree_id=f"SMOKE-E0-{i}",
            species="Senna viarum",
            plot_id="11",
            locality="Guayabal",
            sampling_unit_code="SMOKE/FR/11",
            floristic_design="Rehabilitación vegetal",
            associated_cover="Bosque de galería",
        )
        for i in (1, 2)
    ]
    obs = [
        Observation(
            tree_id=t.tree_id, campaign=m, height_m=0.3 + m / 10, crown_diameter_m=0.2,
            dap_cm=None, dap_status=StatusSemantic.BAJO_UMBRAL_DAP, phytosanitary="Bueno",
            alive=True, colonization=None, field_notes="Defoliación" if m == 2 else None,
        )
        for t in trees for m in (1, 2)
    ]
    return CampaignData(
        trees=trees,
        observations=obs,
        mapping_version="smoke-e0",
        file_metadata=FileMetadata(project_label="SMOKE", event="Segundo monitoreo",
                                   field_crew="Cuadrilla smoke"),
    )


def test_e0_tables_exist_with_their_constraints(session):
    insp = inspect(session.get_bind())
    tablas = set(insp.get_table_names())
    assert {"properties", "plots", "monitorings", "campaign_file_monitorings"} <= tablas
    uniques = {u["name"] for u in insp.get_unique_constraints("plots")}
    assert "uq_plot_project_code" in uniques
    checks = {c["name"] for c in insp.get_check_constraints("monitorings")}
    assert "ck_monitoring_number_positive" in checks


def test_monitoring_date_is_a_real_date_column(session):
    tipos = {c["name"]: str(c["type"]).upper() for c in inspect(session.get_bind()).get_columns(
        "monitorings"
    )}
    assert tipos["monitoring_date"] == "DATE"


def test_ingest_normalizes_territory_and_monitorings_in_postgres(session, project):
    stats = CampaignRepository(session).save_ingest(project.id, _campaign(), "s.xlsx", "e" * 64)
    assert stats["monitorings"] == [1, 2]

    plot = session.scalar(select(PlotRow).where(PlotRow.project_id == project.id))
    assert plot.code == "SMOKE/FR/11"
    assert plot.floristic_design == "Rehabilitación vegetal"
    assert plot.property.name == "Guayabal"

    arbol = session.scalar(select(TreeRow).where(TreeRow.tree_id == "SMOKE-E0-1"))
    assert arbol.plot_id == "11" and arbol.locality == "Guayabal"

    mons = {m.number: m for m in session.scalars(
        select(MonitoringRow).where(MonitoringRow.project_id == project.id)
    )}
    assert set(mons) == {1, 2}
    assert mons[2].field_crew == "Cuadrilla smoke" and mons[1].field_crew is None


def test_monitoring_date_round_trips(session, project):
    CampaignRepository(session).save_ingest(project.id, _campaign(), "s.xlsx", "e" * 64)
    m = session.scalar(select(MonitoringRow).where(
        MonitoringRow.project_id == project.id, MonitoringRow.number == 2
    ))
    m.monitoring_date = date(2026, 3, 15)
    session.commit()
    session.expire_all()
    releido = session.get(MonitoringRow, m.id)
    assert releido.monitoring_date == date(2026, 3, 15)


def test_postgres_rejects_monitoring_number_zero(session, project):
    """El CHECK vive en la base, no solo en el validador del dominio."""
    session.add(MonitoringRow(project_id=project.id, number=0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_cascade_from_project_reaches_the_new_tables(session, project):
    CampaignRepository(session).save_ingest(project.id, _campaign(), "s.xlsx", "e" * 64)
    pid = project.id
    session.delete(project)
    session.commit()
    for tabla in ("properties", "plots", "monitorings"):
        n = session.execute(
            text(f"SELECT COUNT(*) FROM {tabla} WHERE project_id = :p"), {"p": pid}
        ).scalar()
        assert n == 0, tabla
    assert session.scalar(select(PropertyRow).where(PropertyRow.project_id == pid)) is None


def test_too_long_value_is_an_invalid_file_not_a_500(session, project):
    """Postgres rechaza un valor mas largo que su columna; SQLite no.

    Antes salia como "error interno". Ahora es INVALID_FILE con un mensaje
    accionable, y la transaccion no deja nada a medias.
    """
    from agrosense.application.errors import AppError

    data = _campaign()
    data.trees[0] = data.trees[0].model_copy(update={"floristic_design": "x" * 400})
    with pytest.raises(AppError) as exc:
        CampaignRepository(session).save_ingest(project.id, data, "s.xlsx", "f" * 64)
    assert exc.value.code == "INVALID_FILE"
    n = session.execute(
        text("SELECT COUNT(*) FROM plots WHERE project_id = :p"), {"p": project.id}
    ).scalar()
    assert n == 0, "la carga fallida no debe dejar parcelas a medias"


def test_long_joined_metadata_is_trimmed_to_fit(session, project):
    """Varias cuadrillas unidas por AgroSense se recortan: es un dato derivado."""
    data = _campaign()
    data.file_metadata = FileMetadata(field_crew="; ".join(f"Cuadrilla {i}" for i in range(80)))
    CampaignRepository(session).save_ingest(project.id, data, "s.xlsx", "g" * 64)
    m = session.scalar(select(MonitoringRow).where(
        MonitoringRow.project_id == project.id, MonitoringRow.number == 2
    ))
    assert len(m.field_crew) <= 500 and m.field_crew.endswith("…")

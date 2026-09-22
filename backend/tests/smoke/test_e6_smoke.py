"""Smoke de E6 contra Supabase REAL (`pytest -m supabase`).

El mapa se construye desde la base, no desde el Excel: lo que aqui se prueba
es que `load_dataset` devuelve las coordenadas y que el payload sale bien del
viaje completo (Postgres -> entidades -> proyeccion -> grados).

Campana pequena con coordenadas reales del sitio (EPSG:9377). Cada test limpia
lo que crea.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from agrosense.adapters.db.models import Project
from agrosense.adapters.db.repository import (
    CampaignRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
)
from agrosense.adapters.geo import MapBuilder
from agrosense.application.dtos import CampaignData
from agrosense.application.use_cases.project_map import get_project_map
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from tests.auth.keys import ENGINEER_A as OWNER

pytestmark = [
    pytest.mark.supabase,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"), reason="DATABASE_URL ausente (backend/.env)"
    ),
]

SMOKE_PROJECT = "smoke-e6-agrosense"
X0, Y0 = 4735700.0, 2199400.0


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
            session.execute(text("DELETE FROM projects WHERE id = :i"), {"i": p.id})
            session.commit()

    _drop()
    p = ProjectRepository(session).create(owner_id=OWNER, name=SMOKE_PROJECT)
    yield p
    session.rollback()
    _drop()


def _campaign() -> CampaignData:
    trees = [
        Tree(
            tree_id=f"SMOKE-E6-{i}",
            species="Senna viarum",
            locality="Guayabal",
            plot_id="11",
            sampling_unit_code="SMOKE/FR/11",
            floristic_design="Rehabilitación vegetal",
            associated_cover="Bosque de galería",
            coord_x=X0 + 10 * i if i < 5 else None,
            coord_y=Y0 + 10 * (i % 3) if i < 5 else None,
            elevation_m=2746.0 if i < 5 else None,
        )
        for i in range(6)
    ]
    obs = [
        Observation(
            tree_id=t.tree_id,
            campaign=m,
            height_m=None if (m == 2 and t.tree_id.endswith("0")) else 0.3 + 0.2 * m,
            crown_diameter_m=None,
            dap_cm=None,
            dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
            phytosanitary=None if (m == 2 and t.tree_id.endswith("0")) else "Bueno",
            alive=not (m == 2 and t.tree_id.endswith("0")),
            colonization=None,
        )
        for t in trees
        for m in (1, 2)
    ]
    return CampaignData(trees=trees, observations=obs, mapping_version="smoke-e6")


def _mapa(session, project):
    return get_project_map(
        project.id,
        OWNER,
        ProjectRepository(session),
        ProjectAnalysisRepository(session),
        MapBuilder(),
    ).payload


def test_las_coordenadas_sobreviven_al_viaje_por_postgres(session, project):
    """De `Coord_X` en el archivo a grados en la respuesta, pasando por la DB."""
    CampaignRepository(session).save_ingest(project.id, _campaign(), "s.xlsx", "a" * 64)
    mapa = _mapa(session, project)

    assert len(mapa["trees"]) == 5 and mapa["without_coordinates"] == 1
    primero = next(t for t in mapa["trees"] if t["id"] == "SMOKE-E6-0")
    assert 5.79 < primero["lat"] < 5.81, primero["lat"]
    assert -75.39 < primero["lon"] < -75.38, primero["lon"]
    assert primero["elevation_m"] == 2746.0
    assert primero["states"] == {"1": "bueno", "2": "muerto"}


def test_la_parcela_trae_su_contorno_y_su_supervivencia(session, project):
    CampaignRepository(session).save_ingest(project.id, _campaign(), "s.xlsx", "b" * 64)
    mapa = _mapa(session, project)

    assert len(mapa["plots"]) == 1
    parcela = mapa["plots"][0]
    assert parcela["n"] == 5 and parcela["low_sample"] is False
    assert parcela["metrics"]["1"]["survival"] == 100.0
    assert parcela["metrics"]["2"]["survival"] == 80.0
    assert len(parcela["hull"]) >= 2


def test_un_proyecto_de_otro_ingeniero_no_tiene_mapa(session, project):
    from agrosense.application.errors import AppError

    with pytest.raises(AppError) as exc:
        get_project_map(
            project.id,
            "00000000-0000-0000-0000-000000000999",
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            MapBuilder(),
        )
    assert exc.value.code == "PROJECT_NOT_FOUND"


def test_la_capa_de_imagen_vive_y_muere_con_su_proyecto(session, project):
    """UNIQUE(project_id, name) en Postgres y cascada real al borrar."""
    from sqlalchemy.exc import IntegrityError

    from agrosense.adapters.db.repository import ImageryRepository

    repo = ImageryRepository(session)
    repo.create(
        project.id,
        name="Ortofoto 2024",
        tile_template="https://tiles.openaerialmap.org/abc/0/def/{z}/{x}/{y}.png",
        attribution="OpenAerialMap, CC-BY 4.0",
        min_zoom=None,
        max_zoom=21,
        opacity=0.8,
    )
    with pytest.raises(IntegrityError):
        repo.create(
            project.id,
            name="Ortofoto 2024",
            tile_template="https://otro.example.org/{z}/{x}/{y}.png",
            attribution=None,
            min_zoom=None,
            max_zoom=None,
            opacity=1.0,
        )
    session.rollback()
    assert len(repo.list_for_project(project.id)) == 1

    pid = project.id
    session.execute(text("DELETE FROM projects WHERE id = :i"), {"i": pid})
    session.commit()
    n = session.execute(
        text("SELECT COUNT(*) FROM imagery_layers WHERE project_id = :p"), {"p": pid}
    ).scalar()
    assert n == 0

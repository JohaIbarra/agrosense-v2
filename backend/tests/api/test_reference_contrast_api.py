"""Contraste de especies del proyecto con el referente (E5, UC-AN3)."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.auth.keys import ENGINEER_B, bearer, fake_verifier

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
X0, Y0 = 4735700.0, 2199400.0

HEADERS = [
    "LOCALIDAD", "Codigo de unidad muestreo", "ID Parcela", "Diseño floristico",
    "Cobertura vegetal asociada", "ID_MUEST", "Especie_M1", "Familia",
    "Coord_X", "Coord_Y", "Altura total (m)_M1", "Sobrevivencia M1",
    "Estado Fitosanitario_M1",
]


def _excel(especies: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    ws.append(HEADERS)
    for i, especie in enumerate(especies):
        ws.append([
            "Guayabal", "U1", 1, "Rehabilitación vegetal", "Bosque de galería",
            f"G_{i}", especie, "Fabaceae", X0 + 30 * i, Y0, 0.5, "Vivo", "Bueno",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def client_and_session():
    """Como `tests/api/conftest.py::client`, pero expone la sesion para poder
    sembrar el referente directamente (no hay endpoint HTTP para publicarlo:
    UC-R2 lo hace `scripts/load_analytics.py`)."""
    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session, get_token_verifier
    from agrosense.adapters.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    app = create_app()

    def _override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_token_verifier] = fake_verifier

    with TestClient(app, headers=bearer()) as c:
        yield c, Session
    engine.dispose()


def _publish_reference(Session, species_with_effect: dict[str, float]):
    from agrosense.adapters.db.models import ReferenceModel, ReferenceSpeciesEffect
    from agrosense.adapters.db.repository import ReferenceRepository

    s = Session()
    try:
        model = ReferenceModel(
            version="test",
            source_dataset="data/raw/anexo1.xlsx",
            method="lme4::glmer binomial",
        )
        rows = [
            ReferenceSpeciesEffect(
                species_name=name, or_stall=or_stall, sig_stall=True,
                effect_stall=0.1, se_stall=0.1,
                or_stall_lo=or_stall * 0.5, or_stall_hi=or_stall * 1.5,
            )
            for name, or_stall in species_with_effect.items()
        ]
        ReferenceRepository(s).publish_version(model, rows, [], [])
    finally:
        s.close()


def test_project_species_in_the_reference_get_their_risk(client_and_session):
    client, Session = client_and_session
    _publish_reference(Session, {"Lafoensia speciosa": 4.94})

    pid = client.post("/projects", json={"name": "Contraste"}).json()["id"]
    client.post(
        f"/projects/{pid}/campaigns",
        files={"file": ("m.xlsx", _excel(["Lafoensia speciosa"]), XLSX)},
    )

    r = client.get(f"/projects/{pid}/reference-contrast")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["species"] == "Lafoensia speciosa"
    assert body[0]["has_reference"] is True
    assert body[0]["n_trees_in_project"] == 1
    assert body[0]["stall_risk"]["odds_ratio"] == pytest.approx(4.94)


def test_project_species_absent_from_the_reference_is_flagged(client_and_session):
    client, Session = client_and_session
    _publish_reference(Session, {"Lafoensia speciosa": 4.94})

    pid = client.post("/projects", json={"name": "Contraste 2"}).json()["id"]
    client.post(
        f"/projects/{pid}/campaigns",
        files={"file": ("m.xlsx", _excel(["Especie sin referencia"]), XLSX)},
    )

    r = client.get(f"/projects/{pid}/reference-contrast")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["has_reference"] is False
    assert body[0]["stall_risk"] is None


def test_species_with_internal_nbsp_still_matches_the_reference(client_and_session):
    """La ingesta solo hace `.strip()` (`wide_to_long.py`): un NBSP interno o
    un espacio doble sobreviven dentro del nombre. El contraste debe
    normalizar (misma funcion que usa el Referente al publicarse) para que
    esa especie SI case contra `reference_species_effects` (fix round 1,
    hallazgo 1)."""
    client, Session = client_and_session
    _publish_reference(Session, {"Inga punctata": 2.5})

    pid = client.post("/projects", json={"name": "Contraste NBSP"}).json()["id"]
    client.post(
        f"/projects/{pid}/campaigns",
        files={"file": ("m.xlsx", _excel(["Inga\xa0punctata"]), XLSX)},
    )

    r = client.get(f"/projects/{pid}/reference-contrast")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["species"] == "Inga punctata"
    assert body[0]["has_reference"] is True
    assert body[0]["stall_risk"]["odds_ratio"] == pytest.approx(2.5)


def test_a_foreign_project_is_404(client_and_session):
    client, Session = client_and_session
    pid = client.post("/projects", json={"name": "Ajeno"}).json()["id"]

    r = client.get(
        f"/projects/{pid}/reference-contrast", headers=bearer(ENGINEER_B)
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_no_reference_published_is_404(client_and_session):
    """I-1: sin version activa, el contraste no debe fingir «sin referencia»
    especie por especie (eso significa algo distinto: el REFERENTE existe
    pero no cubre esa especie). Aqui el referente entero no esta publicado."""
    client, Session = client_and_session

    pid = client.post("/projects", json={"name": "Sin referente"}).json()["id"]
    client.post(
        f"/projects/{pid}/campaigns",
        files={"file": ("m.xlsx", _excel(["Lafoensia speciosa"]), XLSX)},
    )

    r = client.get(f"/projects/{pid}/reference-contrast")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "REFERENCE_NOT_LOADED"


def test_foreign_project_is_404_even_when_nothing_is_published(client_and_session):
    """I-2: orden explicito del brief — propiedad primero, referente despues."""
    client, Session = client_and_session
    pid = client.post("/projects", json={"name": "Ajeno sin referente"}).json()["id"]

    r = client.get(
        f"/projects/{pid}/reference-contrast", headers=bearer(ENGINEER_B)
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"

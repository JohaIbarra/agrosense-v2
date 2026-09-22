"""Índices espectrales por la API (E10a), con el proveedor sustituido.

Ningún test sale a internet: se reemplaza `PlanetaryComputerIndexSource` en el
módulo de rutas. Lo que se verifica es el contrato —qué devuelve, con qué
código de error— y que leer la serie nunca dependa del proveedor.
"""

import io
from datetime import date

import pytest
from openpyxl import Workbook

from agrosense.adapters.api.routes import indices as rutas
from agrosense.application.dtos import SatelliteScene, SceneStatistics
from agrosense.application.errors import AppError
from tests.auth.keys import ENGINEER_B, bearer

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
X0, Y0 = 4735700.0, 2199400.0

HEADERS = [
    "LOCALIDAD", "Codigo de unidad muestreo", "ID Parcela", "Diseño floristico",
    "Cobertura vegetal asociada", "ID_MUEST", "Especie_M1", "Familia",
    "Coord_X", "Coord_Y", "Altura total (m)_M1", "Sobrevivencia M1",
    "Estado Fitosanitario_M1",
]

ESCENAS = [
    SatelliteScene("S2_2024_12", date(2024, 12, 18), 12.0),
    SatelliteScene("S2_2024_06", date(2024, 6, 10), 30.0),
]
STATS = SceneStatistics(
    mean=0.4858, median=0.4907, minimum=0.2716, maximum=0.6192, std=0.0535, valid_pixels=2952
)


class _FakeSource:
    name = "proveedor-de-prueba"
    escenas = ESCENAS
    stats: SceneStatistics | None = STATS
    error: AppError | None = None

    def search_scenes(self, bbox, start, end, max_cloud, limit):
        if self.error:
            raise self.error
        return list(self.escenas)[:limit]

    def index_statistics(self, scene_id, polygon, index):
        return self.stats


@pytest.fixture(autouse=True)
def proveedor_falso(monkeypatch):
    fuente = _FakeSource()
    monkeypatch.setattr(rutas, "PlanetaryComputerIndexSource", lambda: fuente)
    return fuente


def _excel(n=4) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    ws.append(HEADERS)
    for i in range(n):
        ws.append([
            "Guayabal" if i < 2 else "Tres Jotas", f"U{i // 2}", 1,
            "Rehabilitación vegetal", "Bosque de galería", f"G_{i}",
            "Senna viarum", "Fabaceae", X0 + 30 * i, Y0 + 30 * (i % 2),
            0.5, "Vivo", "Bueno",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def proyecto(client):
    pid = client.post("/projects", json={"name": "NDVI API"}).json()["id"]
    r = client.post(f"/projects/{pid}/campaigns", files={"file": ("m.xlsx", _excel(), XLSX)})
    assert r.status_code == 201, r.text
    return pid


def test_sin_sesion_no_hay_indice(anon_client):
    assert anon_client.get("/projects/1/indices/NDVI").status_code == 401
    assert anon_client.post("/projects/1/indices/NDVI/refresh").status_code == 401


def test_un_proyecto_sin_consultar_devuelve_la_serie_vacia(client, proyecto):
    r = client.get(f"/projects/{proyecto}/indices/NDVI")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["readings"] == [] and cuerpo["properties"] == []
    assert cuerpo["last_refreshed_at"] is None


def test_refrescar_mide_los_predios_y_devuelve_el_resumen(client, proyecto):
    r = client.post(f"/projects/{proyecto}/indices/NDVI/refresh")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["summary"]["scenes_found"] == 2
    assert cuerpo["summary"]["readings_added"] == 4  # 2 escenas x 2 predios
    assert cuerpo["summary"]["interrupted"] is False
    assert sorted(cuerpo["properties"]) == ["Guayabal", "Tres Jotas"]

    lectura = cuerpo["readings"][0]
    assert lectura["mean"] == pytest.approx(0.4858)
    assert lectura["valid_pixels"] == 2952
    assert lectura["reliable"] is True
    assert "moderada" in lectura["reading"]
    assert lectura["source"] == "proveedor-de-prueba"


def test_la_serie_guardada_se_lee_sin_tocar_al_proveedor(client, proyecto, proveedor_falso):
    client.post(f"/projects/{proyecto}/indices/NDVI/refresh")
    proveedor_falso.error = AppError("SATELLITE_UNAVAILABLE", "caído")

    r = client.get(f"/projects/{proyecto}/indices/NDVI")
    assert r.status_code == 200
    assert len(r.json()["readings"]) == 4, "lo guardado se sirve aunque el proveedor no esté"


def test_un_indice_que_no_calculamos_es_422(client, proyecto):
    r = client.get(f"/projects/{proyecto}/indices/EVI")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_INDEX_REQUEST"


def test_una_ventana_imposible_es_422(client, proyecto):
    r = client.post(
        f"/projects/{proyecto}/indices/NDVI/refresh",
        params={"start": "2024-12-31", "end": "2024-01-01"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_INDEX_REQUEST"


def test_el_proveedor_caido_responde_503_no_500(client, proyecto, proveedor_falso):
    """Es un tercero: 503 le dice al ingeniero que reintentar tiene sentido."""
    proveedor_falso.error = AppError("SATELLITE_UNAVAILABLE", "El proveedor no responde.")
    r = client.post(f"/projects/{proyecto}/indices/NDVI/refresh")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "SATELLITE_UNAVAILABLE"


def test_un_proyecto_sin_coordenadas_lo_dice_con_su_codigo(client):
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    ws.append(HEADERS)
    ws.append(["Guayabal", "U1", 1, "Rehabilitación vegetal", "Bosque de galería",
               "G_1", "Senna viarum", "Fabaceae", None, None, 0.5, "Vivo", "Bueno"])
    buf = io.BytesIO()
    wb.save(buf)
    pid = client.post("/projects", json={"name": "NDVI sin coords"}).json()["id"]
    client.post(f"/projects/{pid}/campaigns", files={"file": ("m.xlsx", buf.getvalue(), XLSX)})

    r = client.post(f"/projects/{pid}/indices/NDVI/refresh")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "NO_COORDINATES"


def test_el_proyecto_de_otro_ingeniero_no_existe(client, proyecto):
    ajeno = bearer(ENGINEER_B)
    assert client.get(f"/projects/{proyecto}/indices/NDVI", headers=ajeno).status_code == 404
    r = client.post(f"/projects/{proyecto}/indices/NDVI/refresh", headers=ajeno)
    assert r.status_code == 404


def test_refrescar_dos_veces_no_duplica_lecturas(client, proyecto):
    client.post(f"/projects/{proyecto}/indices/NDVI/refresh")
    r = client.post(f"/projects/{proyecto}/indices/NDVI/refresh")
    assert r.json()["summary"]["readings_added"] == 0
    assert len(r.json()["readings"]) == 4

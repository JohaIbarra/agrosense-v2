"""El mapa del predio por la API (E6).

Un solo endpoint de lectura: todo lo que la pantalla dibuja sale de aqui, y
las coordenadas ya vienen en grados. El Excel de prueba trae Coord_X/Coord_Y
en EPSG:9377, como el archivo real.
"""

import io

import pytest
from openpyxl import Workbook

from tests.auth.keys import ENGINEER_B, bearer

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
X0, Y0 = 4735700.0, 2199400.0

HEADERS = [
    "LOCALIDAD",
    "Codigo de unidad muestreo",
    "ID Parcela",
    "Diseño floristico",
    "Cobertura vegetal asociada",
    "ID_MUEST",
    "Especie_M1",
    "Familia",
    "Coord_X",
    "Coord_Y",
    "Altura",
]


def _excel(monitorings=(1,), n_trees=6) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    per = []
    for n in monitorings:
        per += [f"Altura total (m)_M{n}", f"Sobrevivencia M{n}", f"Estado Fitosanitario_M{n}"]
    ws.append(HEADERS + per)
    for i in range(n_trees):
        fila = [
            "Guayabal", "U1", 1, "Rehabilitación vegetal", "Bosque de galería",
            f"G_{i}", "Senna viarum", "Fabaceae",
            X0 + 10 * i, Y0 + 10 * (i % 3), 2746,
        ]
        for n in monitorings:
            vivo = not (i == 0 and n == 2)
            fila += [0.3 + 0.1 * n if vivo else None, "Vivo" if vivo else "Muerto",
                     "Bueno" if vivo else None]
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _project(client, name="E6 mapa") -> int:
    return client.post("/projects", json={"name": name}).json()["id"]


def _upload(client, pid, content, name="m.xlsx"):
    return client.post(f"/projects/{pid}/campaigns", files={"file": (name, content, XLSX)})


@pytest.fixture()
def proyecto_con_mapa(client):
    pid = _project(client)
    r = _upload(client, pid, _excel(monitorings=(1, 2)))
    assert r.status_code == 201, r.text
    return pid


def test_sin_sesion_el_mapa_no_se_ve(anon_client):
    r = anon_client.get("/projects/1/map")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_el_mapa_de_otro_ingeniero_no_existe(client, proyecto_con_mapa):
    r = client.get(f"/projects/{proyecto_con_mapa}/map", headers=bearer(ENGINEER_B))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_un_proyecto_inexistente_es_404(client):
    assert client.get("/projects/999999/map").status_code == 404


def test_devuelve_los_arboles_en_grados_con_su_estado_por_monitoreo(
    client, proyecto_con_mapa
):
    r = client.get(f"/projects/{proyecto_con_mapa}/map")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_id"] == proyecto_con_mapa
    assert body["srid"] == 9377
    assert body["monitorings"] == [1, 2]
    assert len(body["trees"]) == 6
    primero = next(t for t in body["trees"] if t["id"] == "G_0")
    assert 5.79 < primero["lat"] < 5.81 and -75.39 < primero["lon"] < -75.38
    assert primero["states"] == {"1": "bueno", "2": "muerto"}
    assert primero["heights"]["2"] is None
    assert primero["elevation_m"] == 2746


def test_trae_las_parcelas_con_su_contorno_y_su_supervivencia(client, proyecto_con_mapa):
    body = client.get(f"/projects/{proyecto_con_mapa}/map").json()
    assert len(body["plots"]) == 1
    parcela = body["plots"][0]
    assert parcela["property"] == "Guayabal" and parcela["n"] == 6
    assert parcela["metrics"]["1"]["survival"] == 100.0
    assert parcela["metrics"]["2"]["survival"] == pytest.approx(83.3333, abs=0.001)
    assert len(parcela["hull"]) >= 3
    assert parcela["low_sample"] is False


def test_el_encuadre_y_los_predios_vienen_listos_para_la_pantalla(client, proyecto_con_mapa):
    body = client.get(f"/projects/{proyecto_con_mapa}/map").json()
    b = body["bounds"]
    assert b["south"] < b["north"] and b["west"] < b["east"]
    assert body["properties"] == ["Guayabal"]
    assert body["without_coordinates"] == 0


def test_un_proyecto_sin_cargas_devuelve_un_mapa_vacio_no_un_error(client):
    pid = _project(client, name="E6 vacio")
    r = client.get(f"/projects/{pid}/map")
    assert r.status_code == 200
    body = r.json()
    assert body["trees"] == [] and body["plots"] == [] and body["monitorings"] == []
    assert body["bounds"] is None


def test_los_arboles_sin_coordenada_se_informan(client):
    """El archivo real puede traer filas sin Coord_X: se dicen, no se ocultan."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    ws.append(HEADERS + ["Altura total (m)_M1", "Sobrevivencia M1", "Estado Fitosanitario_M1"])
    ws.append(["Guayabal", "U1", 1, "Rehabilitación vegetal", "Bosque de galería", "G_1",
               "Senna viarum", "Fabaceae", X0, Y0, 2746, 0.4, "Vivo", "Bueno"])
    ws.append(["Guayabal", "U1", 1, "Rehabilitación vegetal", "Bosque de galería", "G_2",
               "Senna viarum", "Fabaceae", None, None, None, 0.5, "Vivo", "Bueno"])
    buf = io.BytesIO()
    wb.save(buf)
    pid = _project(client, name="E6 sin coordenada")
    assert _upload(client, pid, buf.getvalue()).status_code == 201

    body = client.get(f"/projects/{pid}/map").json()
    assert body["without_coordinates"] == 1
    assert [t["id"] for t in body["trees"]] == ["G_1"]

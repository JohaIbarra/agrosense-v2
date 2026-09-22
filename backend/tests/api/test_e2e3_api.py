"""E2/E3 por la API: subir con fecha, fechar monitoreos, leer el analisis y
descargar el reporte. Flujo critico del ingeniero (AGENTS.md: integracion)."""

import io
from datetime import date, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from tests.auth.keys import ENGINEER_B, bearer

DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

HEADERS = [
    "LOCALIDAD",
    "Codigo de unidad muestreo",
    "ID Parcela",
    "Diseño floristico",
    "Cobertura vegetal asociada",
    "ID_MUEST",
    "Especie_M1",
    "Familia",
]


def _excel(monitorings: list[int], sheet="Monitoreo_1") -> bytes:
    """Excel de campo minimo con las columnas de los monitoreos pedidos."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    per = []
    for n in monitorings:
        per += [f"Altura total (m)_M{n}", f"Sobrevivencia M{n}", f"Estado Fitosanitario_M{n}"]
    ws.append(HEADERS + per)
    for i, (species, h) in enumerate([("Senna viarum", 0.3), ("Inga punctata", 0.4)], start=1):
        row = ["Guayabal", "U1", 1, "Rehabilitación vegetal", "Bosque de galería", f"G_{i}",
               species, "Fabaceae"]
        for n in monitorings:
            row += [h + 0.1 * n, "Vivo", "Bueno"]
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _project(client, name="E2 API") -> int:
    return client.post("/projects", json={"name": name}).json()["id"]


def _upload(client, pid, content, monitoring_date=None, name="m.xlsx"):
    data = {"monitoring_date": monitoring_date} if monitoring_date else None
    return client.post(
        f"/projects/{pid}/campaigns", files={"file": (name, content, XLSX)}, data=data
    )


def test_upload_with_date_dates_the_monitoring_and_analyzes_it(client):
    pid = _project(client)
    r = _upload(client, pid, _excel([1]), monitoring_date="2025-03-01")
    assert r.status_code == 201, r.text
    assert r.json()["monitorings"] == [1]
    assert r.json()["analyzed"] == [1]
    m = client.get(f"/projects/{pid}/monitorings").json()
    assert m[0]["monitoring_date"] == "2025-03-01"


def test_analysis_endpoint_returns_the_seven_sheets(client):
    pid = _project(client)
    _upload(client, pid, _excel([1]))
    r = client.get(f"/projects/{pid}/monitorings/1/analysis")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["id"] for s in body["sections"]] == [
        "composicion",
        "alturas",
        "copa",
        "supervivencia",
        "estado_fitosanitario",
        "edades",
        "dap",
        "comparacion",
    ]
    assert body["previous"] is None and body["monitoring"] == 1
    assert len(body["input_hash"]) == 64
    comp = body["sections"][0]["tables"][0]
    assert comp["footer"][0]["total"] == 2


def test_second_monitoring_compares_with_the_first(client):
    pid = _project(client)
    _upload(client, pid, _excel([1]), monitoring_date="2025-03-01", name="m1.xlsx")
    r = _upload(client, pid, _excel([2], sheet="Monitoreo_2"), monitoring_date="2025-09-01")
    assert r.status_code == 201, r.text
    assert r.json()["analyzed"] == [1, 2]
    body = client.get(f"/projects/{pid}/monitorings/2/analysis").json()
    assert body["previous"] == 1
    assert body["monitorings"] == [1, 2]


def test_upload_with_a_future_date_is_rejected_and_nothing_is_saved(client):
    pid = _project(client)
    futuro = (date.today() + timedelta(days=10)).isoformat()
    r = _upload(client, pid, _excel([1]), monitoring_date=futuro)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_MONITORING_DATE"
    assert client.get(f"/projects/{pid}/monitorings").json() == []


def test_patch_monitoring_date_and_notes(client):
    pid = _project(client)
    _upload(client, pid, _excel([1, 2]))
    r = client.patch(f"/projects/{pid}/monitorings/1", json={"monitoring_date": "2025-01-15"})
    assert r.status_code == 200, r.text
    assert r.json()["monitoring_date"] == "2025-01-15"
    assert r.json()["observations"] == 2
    r = client.patch(
        f"/projects/{pid}/monitorings/2", json={"monitoring_date": "2024-12-01", "notes": "x"}
    )
    assert r.status_code == 422
    assert "posterior" in r.json()["detail"]["message"]


def test_missing_monitoring_is_404(client):
    pid = _project(client)
    _upload(client, pid, _excel([1]))
    r = client.get(f"/projects/{pid}/monitorings/5/analysis")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "MONITORING_NOT_FOUND"
    assert client.patch(f"/projects/{pid}/monitorings/5", json={}).status_code == 404


def test_another_engineers_project_is_404_everywhere(client):
    pid = _project(client)
    _upload(client, pid, _excel([1]))
    other = bearer(ENGINEER_B)
    for method, url in [
        ("get", f"/projects/{pid}/monitorings/1/analysis"),
        ("get", f"/projects/{pid}/monitorings/1/report.xlsx"),
        ("patch", f"/projects/{pid}/monitorings/1"),
    ]:
        kwargs = {"json": {"notes": "x"}} if method == "patch" else {}
        r = getattr(client, method)(url, headers=other, **kwargs)
        assert r.status_code == 404, url
        assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_new_routes_require_a_session(anon_client):
    for url in ["/projects/1/monitorings/1/analysis", "/projects/1/monitorings/1/report.xlsx"]:
        assert anon_client.get(url).status_code == 401
    assert anon_client.patch("/projects/1/monitorings/1", json={}).status_code == 401


def test_report_download_is_an_xlsx_with_the_page_numbers(client):
    pid = _project(client)
    _upload(client, pid, _excel([1, 2]))
    r = client.get(f"/projects/{pid}/monitorings/2/report.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"] == XLSX
    assert 'filename="AgroSense_AGS-' in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert "Datos crudos" in wb.sheetnames and "Supervivencia" in wb.sheetnames

    analysis = client.get(f"/projects/{pid}/monitorings/2/analysis").json()
    alturas = next(s for s in analysis["sections"] if s["id"] == "alturas")
    tabla = alturas["tables"][0]
    ws = wb["Alturas"]
    celdas = [c.value for row in ws.iter_rows() for c in row]
    assert tabla["rows"][0]["cur"] in celdas


def test_invalid_date_format_is_rejected(client):
    pid = _project(client)
    r = _upload(client, pid, _excel([1]), monitoring_date="01/03/2025")
    assert r.status_code == 422


@pytest.mark.skipif(not DATASET.exists(), reason="dataset de referencia local ausente")
def test_real_annex_end_to_end(client):
    """El Anexo 1 completo: carga → analisis de M4 → reporte."""
    pid = _project(client, "Anexo 1")
    r = _upload(client, pid, DATASET.read_bytes(), monitoring_date="2024-11-15")
    assert r.status_code == 201, r.text
    assert r.json()["analyzed"] == [1, 2, 3, 4]
    body = client.get(f"/projects/{pid}/monitorings/4/analysis").json()
    assert body["monitoring_date"] == "2024-11-15"
    estado = next(s for s in body["sections"] if s["id"] == "estado_fitosanitario")
    glob = next(t for t in estado["tables"] if t["id"] == "estado-global")
    assert glob["footer"][0]["good"] == 675
    r = client.get(f"/projects/{pid}/monitorings/4/report.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb["Datos crudos"].max_row == 857

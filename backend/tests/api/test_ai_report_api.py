"""Borrador de informe con IA por la API (E9), con Ollama sustituido.

Ningun test sale a la red: se reemplaza `OllamaClient` en el modulo de
rutas, igual que `PlanetaryComputerIndexSource` en test_e10a_index_api.py.
"""
import io

import pytest
from openpyxl import Workbook

from agrosense.adapters.api.routes import ai_reports as rutas
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


class _FakeLLM:
    model_name = "fake-llm-api-test"
    response = (
        "Borrador generado por IA: revise las cifras antes de usarlo.\n\n"
        "Resumen de prueba."
    )
    error: AppError | None = None

    def generate(self, prompt, system):
        if self.error:
            raise self.error
        return self.response


@pytest.fixture(autouse=True)
def llm_falso(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(rutas, "OllamaClient", lambda: fake)
    return fake


def _excel(n=4) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    ws.append(HEADERS)
    for i in range(n):
        ws.append([
            "Guayabal", f"U{i // 2}", 1, "Rehabilitación vegetal", "Bosque de galería",
            f"G_{i}", "Senna viarum", "Fabaceae", X0 + 30 * i, Y0 + 30 * (i % 2),
            0.5, "Vivo", "Bueno",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def proyecto(client):
    pid = client.post("/projects", json={"name": "IA API"}).json()["id"]
    r = client.post(f"/projects/{pid}/campaigns", files={"file": ("m.xlsx", _excel(), XLSX)})
    assert r.status_code == 201, r.text
    return pid


def test_sin_sesion_no_hay_borrador(anon_client):
    assert anon_client.get("/projects/1/monitorings/1/ai-report").status_code == 401
    assert anon_client.post("/projects/1/monitorings/1/ai-report").status_code == 401


def test_sin_generar_todavia_es_404(client, proyecto):
    r = client.get(f"/projects/{proyecto}/monitorings/1/ai-report")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "AI_REPORT_NOT_FOUND"


def test_generar_guarda_y_devuelve_el_borrador(client, proyecto):
    r = client.post(f"/projects/{proyecto}/monitorings/1/ai-report")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["model_name"] == "fake-llm-api-test"
    assert "Resumen de prueba" in cuerpo["content"]
    assert cuerpo["stale"] is False
    assert cuerpo["unverified_numbers"] == []

    leido = client.get(f"/projects/{proyecto}/monitorings/1/ai-report")
    assert leido.status_code == 200
    assert leido.json()["content"] == cuerpo["content"]


def test_un_proyecto_ajeno_da_404(client, proyecto):
    ajeno = bearer(ENGINEER_B)
    assert (
        client.get(f"/projects/{proyecto}/monitorings/1/ai-report", headers=ajeno).status_code
        == 404
    )
    assert (
        client.post(f"/projects/{proyecto}/monitorings/1/ai-report", headers=ajeno).status_code
        == 404
    )


def test_el_proveedor_caido_es_503(client, proyecto, llm_falso):
    llm_falso.error = AppError("LLM_UNAVAILABLE", "Ollama no responde.")
    r = client.post(f"/projects/{proyecto}/monitorings/1/ai-report")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "LLM_UNAVAILABLE"


def test_los_numeros_inventados_quedan_marcados(client, proyecto, llm_falso):
    llm_falso.response = (
        "Borrador generado por IA: revise las cifras antes de usarlo.\n\n"
        "Sobrevivio el 250% de los arboles."
    )
    r = client.post(f"/projects/{proyecto}/monitorings/1/ai-report")
    assert r.status_code == 200
    assert "250%" in r.json()["unverified_numbers"]


# --- Ocultar la IA donde no hay Ollama (produccion en Render) -------------------


def test_features_reporta_la_ia_activa_por_defecto(client, monkeypatch):
    monkeypatch.delenv("AI_REPORTS_ENABLED", raising=False)
    r = client.get("/api/v1/features")
    assert r.status_code == 200
    assert r.json() == {"ai_reports": True}


def test_features_exige_sesion(anon_client):
    assert anon_client.get("/api/v1/features").status_code == 401


@pytest.mark.parametrize("valor", ["false", "0", "no", "FALSE"])
def test_con_la_ia_desactivada_features_lo_dice_y_los_endpoints_dan_404(
    client, proyecto, monkeypatch, valor
):
    monkeypatch.setenv("AI_REPORTS_ENABLED", valor)
    assert client.get("/api/v1/features").json() == {"ai_reports": False}
    for metodo in (client.get, client.post):
        r = metodo(f"/projects/{proyecto}/monitorings/1/ai-report")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "AI_REPORTS_DISABLED"

"""Riesgo de mortalidad por la API (E8), de punta a punta sobre SQLite."""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from agrosense.adapters.api.routes import mortality as rutas
from agrosense.application.errors import AppError
from agrosense.domain.stall_rules import is_at_risk
from tests.auth.keys import ENGINEER_B, bearer

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
X0, Y0 = 4735700.0, 2199400.0
HEADERS = [
    "LOCALIDAD", "Codigo de unidad muestreo", "ID Parcela", "Diseño floristico",
    "Cobertura vegetal asociada", "ID_MUEST", "Especie_M1", "Familia", "Coord_X", "Coord_Y",
    "Altura total (m)_M1", "Diámetro. Copa (m)_M1", "Sobrevivencia M1", "Estado Fitosanitario_M1",
    "Altura total (m)_M2", "Diámetro. Copa (m)_M2", "Sobrevivencia M2", "Estado Fitosanitario_M2",
]
CARD = {
    "model_version": "mortality-general-fake-1",
    "trained_on": ["Anexo 1"],
    "lopo": [{"held_out": "Anexo 1", "median_lift": 1.683}],
    "gate_passed": True,
}


class _FakeScorer:
    model_version = "mortality-general-fake-1+mortality-project-fake-1"
    artifact_sha256 = "f" * 64
    model_card = CARD

    def __init__(self):
        self.calls = 0

    def assess(self, trees, observations, t):
        self.calls += 1
        ids = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        scores = {tid: (i + 1) / (len(ids) + 1) for i, tid in enumerate(ids)}
        return SimpleNamespace(
            kind="general", scores=scores, decision={"reason": "sin_intervalos_cerrados"}
        )

    def fingerprint(self, trees, observations, t):
        return "h" * 64


@pytest.fixture()
def scorer(monkeypatch):
    fake = _FakeScorer()
    monkeypatch.setattr(rutas, "_scorer", lambda: fake)
    return fake


def _excel(n=6) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_2"
    ws.append(HEADERS)
    for i in range(n):
        ws.append([
            "Guayabal", f"U{i // 2}", 1, "Rehabilitación vegetal", "Bosque de galería",
            f"G_{i}", "Senna viarum", "Fabaceae", X0 + 30 * i, Y0 + 30 * (i % 2),
            0.5, 0.3, "Vivo", "Bueno",
            0.5 if i % 2 == 0 else 0.6, 0.3, "Vivo", "Bueno",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def proyecto(client):
    pid = client.post("/projects", json={"name": "Mortalidad API"}).json()["id"]
    r = client.post(f"/projects/{pid}/campaigns", files={"file": ("m.xlsx", _excel(), XLSX)})
    assert r.status_code == 201, r.text
    return pid


def _url(pid, n=2):
    return f"/projects/{pid}/monitorings/{n}/mortality-risk"


def _broken():
    raise AppError("MORTALITY_MODEL_UNAVAILABLE", "El modelo no está disponible.")


def test_requires_a_session(anon_client):
    assert anon_client.get(_url(1)).status_code == 401


def test_foreign_project_is_not_found_and_identical_to_a_missing_one(client, proyecto, scorer):
    ajeno = client.get(_url(proyecto), headers=bearer(ENGINEER_B))
    inexistente = client.get(_url(proyecto + 999), headers=bearer(ENGINEER_B))
    assert ajeno.status_code == 404
    assert ajeno.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert ajeno.json()["detail"]["code"] == inexistente.json()["detail"]["code"]
    assert ajeno.status_code == inexistente.status_code


def test_unknown_monitoring_is_not_found(client, proyecto, scorer):
    r = client.get(_url(proyecto, 9))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "MONITORING_NOT_FOUND"


def test_monitoring_number_is_validated(client, proyecto, scorer):
    assert client.get(_url(proyecto, 0)).status_code == 422


def test_returns_the_assessment(client, proyecto, scorer):
    r = client.get(_url(proyecto))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["monitoring"] == 2
    assert body["model_kind"] == "general"
    assert body["score_kind"] == "relative_risk"
    assert body["decision"] == {"reason": "sin_intervalos_cerrados"}
    assert body["model"] == CARD
    assert body["alert_budget_pct"] == 20.0
    assert body["summary"] == {
        "at_risk": 6,
        "flagged": 1,
        "stalled_last_interval": 3,
        "without_history": 0,
    }
    scores = [t["score"] for t in body["trees"]]
    assert scores == sorted(scores, reverse=True)
    first = body["trees"][0]
    assert first["flagged"] is True
    assert first["risk_percentile"] == 100.0
    assert first["height_m"] is not None
    assert body["trees"][-1]["risk_percentile"] == 0.0


def test_second_read_reuses_the_snapshot(client, proyecto, scorer):
    primero = client.get(_url(proyecto)).json()
    segundo = client.get(_url(proyecto)).json()
    assert scorer.calls == 1
    # SQLite devuelve la fecha sin zona (Postgres, con ella): se compara sin la Z
    assert primero["computed_at"].rstrip("Z") == segundo["computed_at"].rstrip("Z")


def test_only_flagged(client, proyecto, scorer):
    body = client.get(_url(proyecto), params={"only_flagged": "true"}).json()
    assert [t["flagged"] for t in body["trees"]] == [True]
    assert body["summary"]["at_risk"] == 6


def test_model_unavailable_is_a_clean_503(client, proyecto, monkeypatch):
    monkeypatch.setattr(rutas, "_scorer", _broken)
    r = client.get(_url(proyecto))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "MORTALITY_MODEL_UNAVAILABLE"


def test_a_non_owner_gets_404_even_if_the_model_is_down(client, proyecto, monkeypatch):
    monkeypatch.setattr(rutas, "_scorer", _broken)
    r = client.get(_url(proyecto), headers=bearer(ENGINEER_B))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_an_unknown_monitoring_is_404_even_if_the_model_is_down(client, proyecto, monkeypatch):
    monkeypatch.setattr(rutas, "_scorer", _broken)
    r = client.get(_url(proyecto, 9))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "MONITORING_NOT_FOUND"


def test_a_failing_model_loader_becomes_a_503(client, proyecto, monkeypatch):
    from agrosense.ml.mortality_model import MortalityModelError

    def _carga():
        raise MortalityModelError("sin artefacto")

    monkeypatch.setattr(rutas, "_cached_scorer", _carga)
    r = client.get(_url(proyecto))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "MORTALITY_MODEL_UNAVAILABLE"
    assert "sin artefacto" not in r.text


def test_serves_the_committed_model(client, proyecto):
    # Sin sustituir el scorer: el artefacto versionado del modelo general.
    r = client.get(_url(proyecto))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_kind"] in {"general", "project"}
    assert body["model"]["model_version"].startswith("mortality-general-")
    assert len(body["artifact_sha256"]) == 64

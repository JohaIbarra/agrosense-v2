"""Deteccion de estancados por la API (E7), de punta a punta sobre SQLite."""
from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from agrosense.adapters.api.routes import stall as rutas
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
    "model_version": "stall-fake-1",
    "artifact_sha256": "f" * 64,
    "dataset_sha256": "0" * 64,
    "trained_on": "anexo1.xlsx",
    "pr_auc": 0.47,
    "pr_auc_ci_low": 0.36,
    "pr_auc_ci_high": 0.58,
    "roc_auc": 0.73,
    "prevalence_pct": 21.9,
    "recall_at_budget_pct": 45.0,
    "precision_at_budget_pct": 50.0,
}


class _FakeScorer:
    model_version = "stall-fake-1"
    artifact_sha256 = "f" * 64
    model_card = CARD

    def __init__(self):
        self.calls = 0

    def predict(self, trees, observations, t):
        self.calls += 1
        ids = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        return {tid: (i + 1) / (len(ids) + 1) for i, tid in enumerate(ids)}

    def unknown_categories(self, trees, observations, t):
        ids = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        return {tid: [] for tid in ids}

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
    pid = client.post("/projects", json={"name": "Estancados API"}).json()["id"]
    r = client.post(f"/projects/{pid}/campaigns", files={"file": ("m.xlsx", _excel(), XLSX)})
    assert r.status_code == 201, r.text
    return pid


def _url(pid, n=2):
    return f"/projects/{pid}/monitorings/{n}/stall-assessment"


def test_requires_a_session(anon_client):
    assert anon_client.get(_url(1)).status_code == 401


def test_foreign_project_is_not_found(client, proyecto, scorer):
    r = client.get(_url(proyecto), headers=bearer(ENGINEER_B))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


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
    assert body["alert_budget_pct"] == 20.0
    assert body["model"]["model_version"] == "stall-fake-1"
    assert body["summary"] == {
        "at_risk": 6,
        "flagged": 1,
        "stalled_last_interval": 3,
        "persistent": 0,
        "without_history": 0,
        "unknown_species": 0,
        "unknown_category_trees": 0,
        "mostly_without_history": False,
    }
    probs = [t["probability"] for t in body["trees"]]
    assert probs == sorted(probs, reverse=True)
    assert body["trees"][0]["flagged"] is True


def test_second_read_reuses_the_snapshot(client, proyecto, scorer):
    client.get(_url(proyecto))
    client.get(_url(proyecto))
    assert scorer.calls == 1


def test_only_flagged(client, proyecto, scorer):
    body = client.get(_url(proyecto), params={"only_flagged": "true"}).json()
    assert [t["flagged"] for t in body["trees"]] == [True]
    assert body["summary"]["at_risk"] == 6


def test_model_unavailable_is_a_clean_503(client, proyecto, monkeypatch):
    def _roto():
        raise AppError("STALL_MODEL_UNAVAILABLE", "El modelo no está disponible.")

    monkeypatch.setattr(rutas, "_scorer", _roto)
    r = client.get(_url(proyecto))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "STALL_MODEL_UNAVAILABLE"


def test_a_non_owner_gets_404_even_if_the_model_is_down(client, proyecto, monkeypatch):
    # Fix wave (item 5): el scorer se resuelve DESPUES de comprobar dueño y
    # monitoreo, asi que un modelo caido no delata (con un 503) que el
    # proyecto existe cuando quien pregunta no es su dueño.
    def _roto():
        raise AppError("STALL_MODEL_UNAVAILABLE", "El modelo no está disponible.")

    monkeypatch.setattr(rutas, "_scorer", _roto)
    r = client.get(_url(proyecto), headers=bearer(ENGINEER_B))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_an_unknown_monitoring_is_404_even_if_the_model_is_down(client, proyecto, monkeypatch):
    def _roto():
        raise AppError("STALL_MODEL_UNAVAILABLE", "El modelo no está disponible.")

    monkeypatch.setattr(rutas, "_scorer", _roto)
    r = client.get(_url(proyecto, 9))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "MONITORING_NOT_FOUND"


def test_serves_the_committed_model(client, proyecto):
    # Sin sustituir el scorer: el artefacto versionado de la Task 8.
    r = client.get(_url(proyecto))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"]["model_version"].startswith("stall-logreg-")
    assert all(0.0 < t["probability"] < 1.0 for t in body["trees"])

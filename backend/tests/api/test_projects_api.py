"""Tests de integración de los endpoints de la API (Task 5).

TestClient + SQLite en memoria — sin Supabase.
Cada test parte de una DB vacía (fixture client es function-scoped).
"""
from __future__ import annotations

from pathlib import Path

import pytest

DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


# ── POST /projects ─────────────────────────────────────────────────────────

class TestCreateProjectEndpoint:
    def test_returns_201_and_project_shape(self, client):
        r = client.post("/projects", json={"name": "Restauración Guayabal"})
        assert r.status_code == 201
        data = r.json()
        assert data["id"] > 0
        assert data["name"] == "Restauración Guayabal"
        assert data["locality"] is None
        assert "created_at" in data
        assert data["campaigns_count"] == 0

    def test_locality_and_description_accepted(self, client):
        r = client.post("/projects", json={
            "name": "Con Localidad",
            "locality": "Bogotá",
            "description": "Piloto",
        })
        assert r.status_code == 201
        assert r.json()["locality"] == "Bogotá"

    def test_duplicate_name_returns_409(self, client):
        client.post("/projects", json={"name": "Dup"})
        r = client.post("/projects", json={"name": "Dup"})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "DUPLICATE_NAME"

    def test_empty_name_returns_422(self, client):
        r = client.post("/projects", json={"name": ""})
        assert r.status_code == 422

    def test_name_too_long_returns_422(self, client):
        r = client.post("/projects", json={"name": "x" * 201})
        assert r.status_code == 422

    def test_missing_name_returns_422(self, client):
        r = client.post("/projects", json={"locality": "X"})
        assert r.status_code == 422


# ── GET /projects/{id} ─────────────────────────────────────────────────────

class TestGetProjectEndpoint:
    def test_returns_existing_project(self, client):
        created = client.post("/projects", json={"name": "Get Test"}).json()
        r = client.get(f"/projects/{created['id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Get Test"

    def test_campaigns_count_reflects_uploads(self, client):
        """campaigns_count sube cuando se sube una campaña."""
        if not DATASET.exists():
            pytest.skip("dataset ausente")
        proj = client.post("/projects", json={"name": "Count Test"}).json()
        with DATASET.open("rb") as f:
            client.post(
                f"/projects/{proj['id']}/campaigns",
                files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
            )
        r = client.get(f"/projects/{proj['id']}")
        assert r.json()["campaigns_count"] == 1

    def test_nonexistent_returns_404(self, client):
        r = client.get("/projects/999999")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


# ── POST /projects/{id}/campaigns ─────────────────────────────────────────

class TestUploadCampaignEndpoint:
    def test_bad_bytes_returns_400(self, client):
        proj = client.post("/projects", json={"name": "Bad Upload"}).json()
        r = client.post(
            f"/projects/{proj['id']}/campaigns",
            files={"file": ("bad.xlsx", b"no es excel", "application/octet-stream")},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_FILE"

    def test_nonexistent_project_returns_404(self, client):
        r = client.post(
            "/projects/999999/campaigns",
            files={"file": ("f.xlsx", b"bad", "application/octet-stream")},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"

    def test_real_dataset_returns_201_with_stats(self, client):
        if not DATASET.exists():
            pytest.skip("dataset ausente")
        proj = client.post("/projects", json={"name": "Real Upload"}).json()
        with DATASET.open("rb") as f:
            r = client.post(
                f"/projects/{proj['id']}/campaigns",
                files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
            )
        assert r.status_code == 201
        data = r.json()
        assert data["valid"] is True
        assert data["trees"] == 856
        assert data["observations"] == 3146
        assert data["deaths"] == 340
        assert data["campaign_id"] is not None
        assert len(data["warnings"]) > 0

    def test_duplicate_file_returns_409(self, client):
        if not DATASET.exists():
            pytest.skip("dataset ausente")
        proj = client.post("/projects", json={"name": "Dup File"}).json()
        for _ in range(2):
            with DATASET.open("rb") as f:
                r = client.post(
                    f"/projects/{proj['id']}/campaigns",
                    files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
                )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "DUPLICATE_FILE"


# ── GET /projects/{id}/campaigns ──────────────────────────────────────────

class TestGetCampaignsEndpoint:
    def test_empty_list_before_upload(self, client):
        proj = client.post("/projects", json={"name": "Camps Empty"}).json()
        r = client.get(f"/projects/{proj['id']}/campaigns")
        assert r.status_code == 200
        assert r.json() == []

    def test_nonexistent_project_returns_404(self, client):
        r = client.get("/projects/999999/campaigns")
        assert r.status_code == 404

    def test_returns_campaign_after_upload(self, client):
        if not DATASET.exists():
            pytest.skip("dataset ausente")
        proj = client.post("/projects", json={"name": "Camps List"}).json()
        with DATASET.open("rb") as f:
            client.post(
                f"/projects/{proj['id']}/campaigns",
                files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
            )
        r = client.get(f"/projects/{proj['id']}/campaigns")
        assert r.status_code == 200
        camps = r.json()
        assert len(camps) == 1
        assert camps[0]["trees"] == 856
        assert camps[0]["filename"] == "anexo1.xlsx"


# ── GET /projects/{id}/trees ──────────────────────────────────────────────

class TestGetTreesEndpoint:
    def test_empty_list_before_upload(self, client):
        proj = client.post("/projects", json={"name": "Trees Empty"}).json()
        r = client.get(f"/projects/{proj['id']}/trees")
        assert r.status_code == 200
        assert r.json() == []

    def test_nonexistent_project_returns_404(self, client):
        r = client.get("/projects/999999/trees")
        assert r.status_code == 404

    def test_pagination_params_accepted(self, client):
        proj = client.post("/projects", json={"name": "Trees Paged"}).json()
        r = client.get(f"/projects/{proj['id']}/trees?limit=10&offset=0")
        assert r.status_code == 200

    def test_returns_trees_after_upload(self, client):
        if not DATASET.exists():
            pytest.skip("dataset ausente")
        proj = client.post("/projects", json={"name": "Trees List"}).json()
        with DATASET.open("rb") as f:
            client.post(
                f"/projects/{proj['id']}/campaigns",
                files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
            )
        r = client.get(f"/projects/{proj['id']}/trees?limit=10")
        assert r.status_code == 200
        trees = r.json()
        assert len(trees) == 10  # limit respected
        assert "tree_id" in trees[0]
        assert "species" in trees[0]


# ── GET /projects/{id}/trees/{tree_row_id}/observations ───────────────────

class TestGetObservationsEndpoint:
    def test_nonexistent_tree_returns_404(self, client):
        proj = client.post("/projects", json={"name": "Obs 404"}).json()
        r = client.get(f"/projects/{proj['id']}/trees/999999/observations")
        assert r.status_code == 404

    def test_returns_observations_after_upload(self, client):
        if not DATASET.exists():
            pytest.skip("dataset ausente")
        proj = client.post("/projects", json={"name": "Obs List"}).json()
        with DATASET.open("rb") as f:
            client.post(
                f"/projects/{proj['id']}/campaigns",
                files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
            )
        # Obtener primer árbol
        trees = client.get(f"/projects/{proj['id']}/trees?limit=1").json()
        tree_row_id = trees[0]["id"]

        r = client.get(f"/projects/{proj['id']}/trees/{tree_row_id}/observations")
        assert r.status_code == 200
        obs = r.json()
        assert len(obs) >= 1
        assert "campaign" in obs[0]
        assert "alive" in obs[0]

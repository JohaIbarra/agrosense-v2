"""ADR-015: con FRONTEND_DIST, la API sirve el SPA desde el mismo origen."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agrosense.adapters.api.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>agrosense spa</html>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    return TestClient(create_app())


def test_browser_navigation_to_a_spa_route_gets_index_html(client):
    r = client.get("/proyectos/7/monitoreos/3", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert "agrosense spa" in r.text


def test_root_serves_index(client):
    assert "agrosense spa" in client.get("/", headers={"Accept": "text/html"}).text


def test_static_assets_are_served(client):
    r = client.get("/assets/app.js")
    assert r.status_code == 200 and "console.log" in r.text


def test_api_routes_still_win(client):
    r = client.get("/projects", headers={"Accept": "text/html"})
    assert r.status_code == 401  # la API, no el SPA


def test_unknown_non_html_request_is_a_json_404_not_the_spa(client):
    r = client.get("/api/v1/no-existe", headers={"Accept": "application/json"})
    assert r.status_code == 404
    assert "agrosense spa" not in r.text


def test_path_traversal_does_not_escape_dist(client):
    r = client.get("/assets/../../etc/passwd")
    assert "root:" not in r.text


def test_without_frontend_dist_nothing_is_mounted(monkeypatch):
    monkeypatch.delenv("FRONTEND_DIST", raising=False)
    r = TestClient(create_app()).get("/proyectos", headers={"Accept": "text/html"})
    assert r.status_code == 404

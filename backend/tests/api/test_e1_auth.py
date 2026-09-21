"""E1: identidad y aislamiento entre ingenieros.

Criterio de salida del plan: sin token → 401; con el de otro ingeniero → 404;
con el propio → acceso. Los tokens los firma el "Auth" de prueba y el backend
los verifica de verdad (tests/auth/keys.py).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.auth.keys import ENGINEER_A, ENGINEER_B, bearer, make_token

DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"
B = bearer(ENGINEER_B)


def _create(client, name="Restauración Guayabal", headers=None, **extra):
    return client.post("/projects", json={"name": name, **extra}, headers=headers)


# ── Sin sesion: 401 en toda la API ─────────────────────────────────────────

@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/projects"),
        ("post", "/projects"),
        ("get", "/projects/1"),
        ("patch", "/projects/1"),
        ("get", "/projects/1/campaigns"),
        ("post", "/projects/1/campaigns"),
        ("get", "/projects/1/trees"),
        ("get", "/projects/1/monitorings"),
        ("get", "/projects/1/trees/1/observations"),
        ("get", "/api/v1/me"),
        ("put", "/api/v1/me"),
        ("get", "/api/v1/analytics/species"),
        ("get", "/api/v1/analytics/variance-decomposition"),
    ],
)
def test_every_route_requires_a_session(anon_client, method, path):
    r = getattr(anon_client, method)(path)
    assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
    assert r.json()["detail"]["code"] == "UNAUTHENTICATED"
    assert r.headers.get("www-authenticate") == "Bearer"


def test_invalid_token_is_401_with_the_same_message(anon_client):
    """No distinguir 'sin token' de 'token malo': eso solo ayuda a quien prueba."""
    malos = [
        {"Authorization": "Bearer basura"},
        {"Authorization": f"Bearer {make_token(expires_in=-5)}"},
        {"Authorization": f"Bearer {make_token(issuer='https://otro.supabase.co/auth/v1')}"},
        {"Authorization": make_token()},  # sin el prefijo Bearer
    ]
    mensajes = set()
    for h in malos:
        r = anon_client.get("/projects", headers=h)
        assert r.status_code == 401
        mensajes.add(r.json()["detail"]["message"])
    assert len(mensajes) == 1


# ── Perfil ─────────────────────────────────────────────────────────────────

def test_profile_is_created_on_first_request(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == ENGINEER_A
    assert body["email"] == "ingeniera@example.com"
    assert body["full_name"] is None


def test_profile_can_be_completed(client):
    r = client.put(
        "/api/v1/me",
        json={"full_name": "Ana Pérez", "professional_license": "CPIF-12345"},
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Ana Pérez"
    assert client.get("/api/v1/me").json()["professional_license"] == "CPIF-12345"


# ── Proyectos: propiedad y aislamiento ─────────────────────────────────────

def test_project_gets_an_internal_code(client):
    body = _create(client).json()
    assert body["project_code"].startswith("AGS-")
    assert body["project_code"].endswith(f"-{body['id']:04d}")
    assert body["status"] == "activo"
    assert body["coordinate_srid"] == 9377


def test_list_shows_only_my_projects(client):
    _create(client, "Mío")
    _create(client, "De otro", headers=B)
    nombres = [p["name"] for p in client.get("/projects").json()]
    assert nombres == ["Mío"]
    assert [p["name"] for p in client.get("/projects", headers=B).json()] == ["De otro"]


def test_another_engineers_project_is_404_everywhere(client):
    """Un proyecto ajeno responde igual que uno inexistente."""
    pid = _create(client, "Privado").json()["id"]
    for method, path, kw in [
        ("get", f"/projects/{pid}", {}),
        ("patch", f"/projects/{pid}", {"json": {"name": "Robado"}}),
        ("get", f"/projects/{pid}/campaigns", {}),
        ("get", f"/projects/{pid}/trees", {}),
        ("get", f"/projects/{pid}/monitorings", {}),
        ("get", f"/projects/{pid}/trees/1/observations", {}),
    ]:
        r = getattr(client, method)(path, headers=B, **kw)
        assert r.status_code == 404, f"{method.upper()} {path} -> {r.status_code}"
        assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    # y el propietario sigue viendolo intacto
    assert client.get(f"/projects/{pid}").json()["name"] == "Privado"


@pytest.mark.skipif(not DATASET.exists(), reason="dataset de referencia local ausente")
def test_cannot_upload_to_another_engineers_project(client):
    pid = _create(client, "Ajeno para cargar").json()["id"]
    with DATASET.open("rb") as f:
        r = client.post(
            f"/projects/{pid}/campaigns",
            files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
            headers=B,
        )
    assert r.status_code == 404
    assert client.get(f"/projects/{pid}/monitorings").json() == []


def test_same_name_is_allowed_for_different_engineers(client):
    assert _create(client, "Restauración Guayabal").status_code == 201
    assert _create(client, "Restauración Guayabal", headers=B).status_code == 201


def test_same_engineer_cannot_repeat_a_name(client):
    _create(client, "Único")
    r = _create(client, "Único")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "DUPLICATE_NAME"


# ── Campos del proyecto (D7) y reglas del dominio ──────────────────────────

def test_project_accepts_the_approved_fields(client):
    body = _create(
        client,
        "Completo",
        contract_code="UPME 04-2014",
        objective="Compensación por la línea Medellín - La Virginia",
        executing_org="Restauradora S.A.S.",
        contracting_entity="GEB",
        department="Antioquia",
        municipality="La Unión",
        intervention_type="rehabilitacion",
        area_ha=12.5,
        planted_individuals=856,
        planting_density=1100,
        establishment_date="2023-04-10",
        start_date="2023-01-01",
        end_date="2027-12-31",
        legal_framework="compensacion_ambiental",
        environmental_authority="CORNARE",
    ).json()
    assert body["contract_code"] == "UPME 04-2014"
    assert body["intervention_type"] == "rehabilitacion"
    assert body["planted_individuals"] == 856
    assert body["establishment_date"] == "2023-04-10"


@pytest.mark.parametrize(
    "campos",
    [
        {"intervention_type": "cultivo_de_papa"},
        {"legal_framework": "porque si"},
        {"area_ha": 0},
        {"planted_individuals": -3},
        {"start_date": "2025-01-01", "end_date": "2024-01-01"},
    ],
)
def test_domain_rules_reject_invalid_projects(client, campos):
    r = _create(client, "Inválido", **campos)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_PROJECT"


def test_patch_updates_only_what_is_sent(client):
    pid = _create(client, "Para editar", department="Antioquia").json()["id"]
    r = client.patch(f"/projects/{pid}", json={"municipality": "Sonsón"})
    assert r.status_code == 200
    body = r.json()
    assert body["municipality"] == "Sonsón"
    assert body["department"] == "Antioquia", "lo no enviado no se toca"


def test_patch_validates_against_what_is_already_stored(client):
    """Una fecha de fin anterior al inicio YA guardado se rechaza."""
    pid = _create(client, "Fechas", start_date="2024-06-01").json()["id"]
    r = client.patch(f"/projects/{pid}", json={"end_date": "2024-01-01"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_PROJECT"


def test_patch_can_close_a_project(client):
    pid = _create(client, "A cerrar").json()["id"]
    r = client.patch(f"/projects/{pid}", json={"status": "cerrado"})
    assert r.json()["status"] == "cerrado"


def test_patch_cannot_change_the_internal_code(client):
    """`project_code` no esta en el contrato de PATCH: se ignora, no se edita."""
    body = _create(client, "Código fijo").json()
    client.patch(f"/projects/{body['id']}", json={"project_code": "HACKED"})
    assert client.get(f"/projects/{body['id']}").json()["project_code"] == body["project_code"]


def test_patch_rename_cannot_collide_with_another_of_my_projects(client):
    _create(client, "Uno")
    pid = _create(client, "Dos").json()["id"]
    r = client.patch(f"/projects/{pid}", json={"name": "Uno"})
    assert r.status_code == 409


def test_catalogs_expose_the_domain_vocabularies(client):
    from agrosense.domain.project import INTERVENTION_TYPES, LEGAL_FRAMEWORKS

    body = client.get("/api/v1/catalogs").json()
    assert body["intervention_types"] == list(INTERVENTION_TYPES)
    assert body["legal_frameworks"] == list(LEGAL_FRAMEWORKS)
    assert body["project_statuses"] == ["activo", "cerrado"]
    assert body["default_srid"] == 9377


def test_catalogs_require_a_session(anon_client):
    assert anon_client.get("/api/v1/catalogs").status_code == 401

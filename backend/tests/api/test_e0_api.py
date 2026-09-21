"""E0 / T7: la API expone la parcela y los monitoreos, sin romper lo existente.

Se sube el Excel REAL por la API: es la prueba de punta a punta de que las
dimensiones que antes se descartaban llegan hasta la respuesta.
"""
from pathlib import Path

import pytest

DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"

needs_dataset = pytest.mark.skipif(
    not DATASET.exists(), reason="dataset de referencia local ausente"
)


def _project(client, name="E0 API") -> int:
    return client.post("/projects", json={"name": name}).json()["id"]


def _upload(client, pid: int):
    with DATASET.open("rb") as f:
        return client.post(
            f"/projects/{pid}/campaigns",
            files={"file": ("anexo1.xlsx", f, "application/octet-stream")},
        )


@needs_dataset
def test_upload_reports_the_monitorings_it_brought(client):
    r = _upload(client, _project(client))
    assert r.status_code == 201
    assert r.json()["monitorings"] == [1, 2, 3, 4]


@needs_dataset
def test_real_upload_raises_no_file_level_warning(client):
    """`Evento` dice «Cuarto monitoreo» y el archivo llega hasta M4: cuadra."""
    tipos = {w["type"] for w in _upload(client, _project(client)).json()["warnings"]}
    assert "event_mismatch" not in tipos
    assert "project_mismatch" not in tipos


@needs_dataset
def test_monitorings_endpoint_lists_the_four_monitorings(client):
    pid = _project(client)
    _upload(client, pid)
    r = client.get(f"/projects/{pid}/monitorings")
    assert r.status_code == 200
    body = r.json()
    assert [m["number"] for m in body] == [1, 2, 3, 4]
    assert all(m["observations"] > 600 for m in body)
    assert all(m["monitoring_date"] is None for m in body), "el Excel no trae fechas"
    # la cuadrilla del archivo se atribuye al monitoreo que declara (M4)
    assert body[-1]["field_crew"] == "Ruben D. Ibarra; Jhunior Sinisterra"
    assert body[0]["field_crew"] is None


@needs_dataset
def test_trees_expose_their_plot_attributes(client):
    pid = _project(client)
    _upload(client, pid)
    arboles = client.get(f"/projects/{pid}/trees", params={"limit": 500}).json()
    assert all(a["sampling_unit_code"] for a in arboles), "todos los arboles tienen unidad"
    assert all(a["floristic_design"] for a in arboles)
    assert all(a["associated_cover"] for a in arboles)
    assert {a["locality"] for a in arboles} <= {"Tres Jotas", "Guayabal", "San Antonio"}
    assert arboles[0]["sampling_unit_code"].startswith("GEB/MED-LV/NV/FR/")


@needs_dataset
def test_existing_tree_fields_keep_their_shape(client):
    """Cambio aditivo: los campos que ya existian siguen igual."""
    pid = _project(client)
    _upload(client, pid)
    arbol = client.get(f"/projects/{pid}/trees", params={"limit": 1}).json()[0]
    for campo in (
        "id", "tree_id", "species", "family", "common_name", "guild",
        "locality", "elevation_m",
    ):
        assert campo in arbol


@needs_dataset
def test_observations_keep_the_campaign_number(client):
    """`ObservationResponse.campaign` sigue siendo el numero de monitoreo."""
    pid = _project(client)
    _upload(client, pid)
    tree_id = client.get(f"/projects/{pid}/trees", params={"limit": 1}).json()[0]["id"]
    obs = client.get(f"/projects/{pid}/trees/{tree_id}/observations").json()
    numeros = [o["campaign"] for o in obs]
    assert numeros == sorted(numeros) and set(numeros) <= {1, 2, 3, 4}


def test_monitorings_of_a_missing_project_is_404(client):
    r = client.get("/projects/9999/monitorings")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_monitorings_of_an_empty_project_is_an_empty_list(client):
    r = client.get(f"/projects/{_project(client)}/monitorings")
    assert r.status_code == 200 and r.json() == []

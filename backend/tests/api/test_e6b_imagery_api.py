"""Capas de imagen del proyecto por la API (E6b).

El ingeniero registra la ortofoto de su predio como plantilla de teselas (la
que dan OpenAerialMap, un TiTiler o su plataforma de drones) y el mapa la
dibuja debajo de los árboles.
"""

from tests.auth.keys import ENGINEER_B, bearer

OAM = "https://tiles.openaerialmap.org/573a17d4cd0663bb003c32b6/0/575fcf142b67227a79b4fbfd/{z}/{x}/{y}.png"


def _project(client, name="E6b ortofoto") -> int:
    return client.post("/projects", json={"name": name}).json()["id"]


def _crear(client, pid, **campos):
    cuerpo = {"name": "Ortofoto 2024", "tile_template": OAM, **campos}
    return client.post(f"/projects/{pid}/imagery", json=cuerpo)


def test_sin_sesion_no_se_listan_ni_se_crean(anon_client):
    assert anon_client.get("/projects/1/imagery").status_code == 401
    assert anon_client.post("/projects/1/imagery", json={}).status_code == 401


def test_un_proyecto_recien_creado_no_tiene_capas(client):
    pid = _project(client)
    r = client.get(f"/projects/{pid}/imagery")
    assert r.status_code == 200 and r.json() == []


def test_registrar_una_ortofoto_y_verla_en_la_lista(client):
    pid = _project(client)
    r = _crear(
        client,
        pid,
        attribution="Imagen: Santiago Pastor (OpenAerialMap, CC-BY 4.0)",
        opacity=0.8,
        max_zoom=21,
    )
    assert r.status_code == 201, r.text
    capa = r.json()
    assert capa["name"] == "Ortofoto 2024"
    assert capa["tile_template"] == OAM
    assert capa["opacity"] == 0.8 and capa["max_zoom"] == 21
    assert capa["attribution"].startswith("Imagen: Santiago Pastor")

    lista = client.get(f"/projects/{pid}/imagery").json()
    assert [c["id"] for c in lista] == [capa["id"]]


def test_la_opacidad_por_defecto_es_opaca(client):
    pid = _project(client)
    assert _crear(client, pid).json()["opacity"] == 1.0


def test_una_direccion_sin_https_se_rechaza_con_mensaje_util(client):
    pid = _project(client)
    r = _crear(client, pid, tile_template="http://tiles.example.org/{z}/{x}/{y}.png")
    assert r.status_code == 422
    cuerpo = r.json()["detail"]
    assert cuerpo["code"] == "INVALID_IMAGERY_LAYER"
    assert "https" in cuerpo["message"]


def test_una_plantilla_sin_marcadores_se_rechaza(client):
    pid = _project(client)
    r = _crear(client, pid, tile_template="https://tiles.example.org/mapa.png")
    assert r.status_code == 422
    assert "{z}" in r.json()["detail"]["message"]


def test_dos_capas_del_mismo_proyecto_no_repiten_nombre(client):
    pid = _project(client)
    assert _crear(client, pid).status_code == 201
    r = _crear(client, pid)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "DUPLICATE_IMAGERY_LAYER"


def test_el_proyecto_de_otro_ingeniero_no_existe(client):
    pid = _project(client)
    ajeno = bearer(ENGINEER_B)
    assert client.get(f"/projects/{pid}/imagery", headers=ajeno).status_code == 404
    r = client.post(
        f"/projects/{pid}/imagery",
        json={"name": "Suya", "tile_template": OAM},
        headers=ajeno,
    )
    assert r.status_code == 404


def test_se_puede_quitar_una_capa(client):
    pid = _project(client)
    capa = _crear(client, pid).json()
    assert client.delete(f"/projects/{pid}/imagery/{capa['id']}").status_code == 204
    assert client.get(f"/projects/{pid}/imagery").json() == []


def test_quitar_una_capa_que_no_existe_es_404(client):
    pid = _project(client)
    r = client.delete(f"/projects/{pid}/imagery/999999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "IMAGERY_LAYER_NOT_FOUND"


def test_una_capa_de_otro_proyecto_no_se_borra_desde_este(client):
    """Las capas viven dentro de su proyecto: el id solo no da acceso."""
    mio = _project(client, name="E6b mío")
    otro = _project(client, name="E6b otro")
    capa = _crear(client, otro).json()
    assert client.delete(f"/projects/{mio}/imagery/{capa['id']}").status_code == 404
    assert len(client.get(f"/projects/{otro}/imagery").json()) == 1


def test_el_mapa_entrega_las_capas_del_proyecto(client):
    """El mapa se pide UNA vez: sus capas de imagen vienen dentro."""
    pid = _project(client)
    _crear(client, pid, attribution="OpenAerialMap, CC-BY 4.0")
    mapa = client.get(f"/projects/{pid}/map").json()
    assert [c["name"] for c in mapa["imagery"]] == ["Ortofoto 2024"]
    assert mapa["imagery"][0]["attribution"] == "OpenAerialMap, CC-BY 4.0"

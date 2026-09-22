"""Adaptador de Planetary Computer (E10a), SIN salir a la red.

Se sustituye `_post`, que es el único punto que habla HTTP. Lo que se prueba
es la traducción: qué se le pide al proveedor y cómo se lee su respuesta,
incluidos los casos en que no hay dato (que no son un error).
"""

from datetime import date

import pytest

from agrosense.adapters.satellite import planetary_computer as pc
from agrosense.application.errors import AppError

BBOX = (-75.392, 5.795, -75.380, 5.810)
POLIGONO = [[5.7996, -75.3876], [5.7996, -75.3840], [5.8060, -75.3840]]


@pytest.fixture()
def llamadas(monkeypatch):
    """Registra lo que se enviaría y devuelve respuestas de mentira."""
    registro: list[tuple[str, dict]] = []
    respuestas: list[dict] = []

    def _post(url, body, timeout=None):
        registro.append((url, body))
        return respuestas.pop(0)

    monkeypatch.setattr(pc, "_post", _post)
    return registro, respuestas


def _item(scene_id, fecha, nubes):
    return {"id": scene_id, "properties": {"datetime": fecha, "eo:cloud_cover": nubes}}


def test_la_busqueda_pide_la_coleccion_el_rango_y_el_limite_de_nubes(llamadas):
    registro, respuestas = llamadas
    respuestas.append({"features": [_item("S2A_1", "2024-12-18T15:26:59Z", 36.7)]})

    escenas = pc.PlanetaryComputerIndexSource().search_scenes(
        BBOX, date(2024, 10, 1), date(2024, 12, 31), 40.0, 10
    )

    url, cuerpo = registro[0]
    assert url == pc.STAC_URL
    assert cuerpo["collections"] == ["sentinel-2-l2a"]
    assert cuerpo["bbox"] == list(BBOX)
    assert cuerpo["datetime"].startswith("2024-10-01")
    assert cuerpo["query"]["eo:cloud_cover"]["lt"] == 40.0
    assert escenas[0].scene_id == "S2A_1"
    assert escenas[0].acquired_at == date(2024, 12, 18)
    assert escenas[0].cloud_cover == 36.7


def test_de_varias_escenas_del_mismo_dia_se_queda_una(llamadas):
    """Órbitas solapadas dan dos imágenes del mismo día: es una fecha, no dos."""
    _, respuestas = llamadas
    respuestas.append(
        {
            "features": [
                _item("S2A_1", "2024-12-18T15:26:59Z", 10.0),
                _item("S2A_2", "2024-12-18T15:27:30Z", 55.0),
                _item("S2A_3", "2024-11-08T15:26:59Z", 20.0),
            ]
        }
    )
    escenas = pc.PlanetaryComputerIndexSource().search_scenes(
        BBOX, date(2024, 10, 1), date(2024, 12, 31), 60.0, 10
    )
    assert [e.scene_id for e in escenas] == ["S2A_1", "S2A_3"]
    assert [e.acquired_at for e in escenas] == [date(2024, 12, 18), date(2024, 11, 8)]


def test_las_escenas_vienen_de_la_mas_reciente_hacia_atras(llamadas):
    _, respuestas = llamadas
    respuestas.append(
        {
            "features": [
                _item("viejo", "2024-01-05T15:00:00Z", 5.0),
                _item("nuevo", "2024-12-18T15:00:00Z", 5.0),
            ]
        }
    )
    escenas = pc.PlanetaryComputerIndexSource().search_scenes(
        BBOX, date(2024, 1, 1), date(2024, 12, 31), 60.0, 10
    )
    assert [e.scene_id for e in escenas] == ["nuevo", "viejo"]


def test_los_estadisticos_traducen_la_expresion_del_ndvi(llamadas):
    registro, respuestas = llamadas
    expr = "(B08-B04)/(B08+B04)"
    respuestas.append(
        {
            "properties": {
                "statistics": {
                    expr: {
                        "min": 0.2716, "max": 0.6192, "mean": 0.4858,
                        "median": 0.4907, "std": 0.0535, "count": 2952,
                    }
                }
            }
        }
    )
    stats = pc.PlanetaryComputerIndexSource().index_statistics("S2A_1", POLIGONO, "NDVI")

    url, cuerpo = registro[0]
    assert url.startswith(pc.DATA_URL) and "expression=" in url
    assert cuerpo["geometry"]["type"] == "Polygon"
    # GeoJSON va en (lon, lat) y el anillo se cierra
    anillo = cuerpo["geometry"]["coordinates"][0]
    assert anillo[0] == [-75.3876, 5.7996]
    assert anillo[0] == anillo[-1]
    assert stats.mean == pytest.approx(0.4858)
    assert stats.valid_pixels == 2952
    assert stats.std == pytest.approx(0.0535)


def test_sin_pixeles_validos_no_hay_dato_y_no_es_un_error(llamadas):
    """Nubes sobre el predio: el resultado es «no hay medición», no un fallo."""
    _, respuestas = llamadas
    respuestas.append(
        {"properties": {"statistics": {"(B08-B04)/(B08+B04)": {"count": 0, "mean": None}}}}
    )
    assert pc.PlanetaryComputerIndexSource().index_statistics("S2A_1", POLIGONO, "NDVI") is None


def test_una_escena_que_no_cubre_el_predio_tampoco_es_un_error(llamadas):
    _, respuestas = llamadas
    respuestas.append({"properties": {"statistics": {}}})
    assert pc.PlanetaryComputerIndexSource().index_statistics("S2A_1", POLIGONO, "NDVI") is None


def test_un_indice_que_este_proveedor_no_calcula_falla_claro(llamadas):
    with pytest.raises(AppError) as exc:
        pc.PlanetaryComputerIndexSource().index_statistics("S2A_1", POLIGONO, "EVI")
    assert exc.value.code == "SATELLITE_UNAVAILABLE"


def test_un_fallo_de_red_sale_como_error_de_operacion_no_como_excepcion(monkeypatch):
    """El ingeniero lee «vuelva a intentarlo», no un traceback de urllib."""
    import urllib.error

    intentos = []

    def _urlopen(request, timeout=None):
        intentos.append(request.full_url)
        raise urllib.error.URLError("getaddrinfo failed")

    monkeypatch.setattr(pc.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(pc.time, "sleep", lambda _: None)

    with pytest.raises(AppError) as exc:
        pc.PlanetaryComputerIndexSource().search_scenes(
            BBOX, date(2024, 1, 1), date(2024, 12, 31), 60.0, 5
        )
    assert exc.value.code == "SATELLITE_UNAVAILABLE"
    assert "intentarlo" in exc.value.message
    assert len(intentos) == pc._RETRIES, "debe reintentar antes de rendirse"


def test_un_rechazo_del_proveedor_no_se_reintenta(monkeypatch):
    """Un 400 es culpa de lo que pedimos: repetirlo solo gasta tiempo."""
    import urllib.error

    intentos = []

    def _urlopen(request, timeout=None):
        intentos.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(pc.urllib.request, "urlopen", _urlopen)

    with pytest.raises(AppError) as exc:
        pc.PlanetaryComputerIndexSource().search_scenes(
            BBOX, date(2024, 1, 1), date(2024, 12, 31), 60.0, 5
        )
    assert exc.value.code == "SATELLITE_UNAVAILABLE"
    assert len(intentos) == 1

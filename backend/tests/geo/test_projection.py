"""Proyeccion EPSG:9377 (MAGNA-SIRGAS / Origen-Nacional) -> WGS84.

Los puntos de control son los de `docs/verificacion-e0.md` §6: si esta
conversion se rompe, los arboles aparecen en otro pais y nadie lo nota hasta
verlo en pantalla. La tolerancia (0.0002° ~ 20 m) es la de las coordenadas
redondeadas de ese documento, no la del calculo.
"""
from __future__ import annotations

import pytest

from agrosense.adapters.geo.projection import UnsupportedSridError, to_wgs84

# Esquinas reales del dataset del Anexo (M1-M4, 856 arboles)
MIN_XY = (4735663.154532, 2199355.020624)
MAX_XY = (4736309.5593, 2200261.893213)


# Centroides de los tres predios del Anexo, en el sistema del proyecto. La
# tabla de `verificacion-e0.md` §6 salio de estos puntos: son la referencia.
CENTROIDES = {
    "Guayabal": ((4735971.859, 2199633.005), (5.8017, -75.3852)),
    "San Antonio": ((4735706.952, 2199585.832), (5.8013, -75.3876)),
    "Tres Jotas": ((4735995.790, 2200043.132), (5.8054, -75.3850)),
}


@pytest.mark.parametrize("predio", sorted(CENTROIDES))
def test_los_predios_caen_donde_dice_la_verificacion_de_e0(predio):
    xy, (lat_esperada, lon_esperada) = CENTROIDES[predio]
    (lat, lon), = to_wgs84([xy], 9377)
    # 0.00005° ~ 5 m: la tabla de E0 esta redondeada a cuatro decimales
    assert lat == pytest.approx(lat_esperada, abs=0.00005)
    assert lon == pytest.approx(lon_esperada, abs=0.00005)


def test_el_sitio_esta_en_colombia_no_en_el_golfo_de_guinea():
    """Guarda contra el error clasico: confundir el orden (x, y) con (lat, lon).

    Sin `always_xy=True` la transformacion devuelve las componentes al reves y
    los arboles aparecen en el Atlantico, cerca del (0, 0).
    """
    (lat, lon), = to_wgs84([MIN_XY], 9377)
    assert 4 < lat < 7 and -76 < lon < -75


def test_la_extension_del_predio_mide_lo_que_medimos_en_e0():
    """646 x 907 m: si la proyeccion cambia de escala, esto se dispara."""
    (lat0, lon0), (lat1, lon1) = to_wgs84([MIN_XY, MAX_XY], 9377)
    metros_por_grado_lat = 110_574
    metros_por_grado_lon = 111_320 * 0.9949  # cos(5.8°)
    ancho = abs(lon1 - lon0) * metros_por_grado_lon
    alto = abs(lat1 - lat0) * metros_por_grado_lat
    assert ancho == pytest.approx(646, abs=15)
    assert alto == pytest.approx(907, abs=15)


def test_devuelve_los_puntos_en_el_mismo_orden():
    a, b, c = to_wgs84([MIN_XY, MAX_XY, MIN_XY], 9377)
    assert a == c and a != b


def test_una_lista_vacia_no_toca_la_proyeccion():
    assert to_wgs84([], 9377) == []


def test_un_srid_que_no_conocemos_es_un_error_explicito():
    with pytest.raises(UnsupportedSridError) as exc:
        to_wgs84([MIN_XY], 999999)
    assert "999999" in str(exc.value)


def test_wgs84_de_entrada_se_devuelve_tal_cual():
    """Un proyecto ya en 4326 no se reproyecta: (lat, lon) = (y, x)."""
    assert to_wgs84([(-75.3852, 5.8017)], 4326) == [(5.8017, -75.3852)]

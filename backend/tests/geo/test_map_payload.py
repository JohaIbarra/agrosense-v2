"""Payload del mapa (E6) sobre datos sinteticos con coordenadas reales.

Las coordenadas salen del entorno del Anexo (EPSG:9377, cerca de los 4 735 700
E / 2 199 400 N) para que los grados resultantes sean los de verdad y no un
punto en el mar.
"""

from __future__ import annotations

import pytest

from agrosense.adapters.geo.map_payload import MAP_VERSION, build_map
from agrosense.domain.entities import Observation, StatusSemantic, Tree

X0, Y0 = 4735700.0, 2199400.0


def tree(
    tid, *, dx=0.0, dy=0.0, prop="Guayabal", plot="11",
    species="Cedrela montana", coords=True,
):
    return Tree(
        tree_id=tid,
        species=species,
        locality=prop,
        plot_id=plot,
        sampling_unit_code=f"{prop}/FR/{plot}",
        floristic_design="Rehabilitación vegetal",
        associated_cover="Bosque de galería",
        coord_x=X0 + dx if coords else None,
        coord_y=Y0 + dy if coords else None,
        elevation_m=2746.0 if coords else None,
    )


def obs(tid, m, h, *, alive=True, phyto="Bueno"):
    return Observation(
        tree_id=tid,
        campaign=m,
        height_m=h,
        crown_diameter_m=None,
        dap_cm=None,
        dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary=phyto if alive else None,
        alive=alive,
        colonization=None,
    )


# Parcela 11 (Guayabal): 5 arboles en cuadrado de 40 m; uno muere en M2.
# Parcela 12 (Guayabal): 2 arboles — por debajo del minimo de muestra.
# Parcela 21 (Tres Jotas): 1 arbol, a 500 m al norte.
TREES = [
    tree("G1", dx=0, dy=0),
    tree("G2", dx=40, dy=0),
    tree("G3", dx=40, dy=40),
    tree("G4", dx=0, dy=40),
    tree("G5", dx=20, dy=20),
    tree("H1", dx=100, dy=0, plot="12"),
    tree("H2", dx=140, dy=0, plot="12"),
    tree("T1", dx=0, dy=500, prop="Tres Jotas", plot="21"),
]
OBS = [
    *[obs(t, 1, 0.4) for t in ("G1", "G2", "G3", "G4", "G5", "H1", "H2", "T1")],
    obs("G1", 2, 0.7),
    obs("G2", 2, 0.8, phyto="Regular"),
    obs("G3", 2, 0.9, phyto="Malo"),
    obs("G4", 2, None, alive=False),
    obs("G5", 2, 0.6, phyto=None),
    obs("H1", 2, 0.5),
    obs("H2", 2, 0.5),
    obs("T1", 2, 1.2),
]


@pytest.fixture(scope="module")
def mapa():
    return build_map(TREES, OBS, 9377)


def test_lleva_su_version_y_los_monitoreos_que_existen(mapa):
    assert mapa["version"] == MAP_VERSION
    assert mapa["srid"] == 9377
    assert mapa["monitorings"] == [1, 2]


def test_un_punto_por_arbol_con_coordenada_en_grados(mapa):
    assert len(mapa["trees"]) == 8
    g1 = next(t for t in mapa["trees"] if t["id"] == "G1")
    # (4735700, 2199400) en EPSG:9377, verificado en test_projection.py
    assert g1["lat"] == pytest.approx(5.79958, abs=0.00002)
    assert g1["lon"] == pytest.approx(-75.38761, abs=0.00002)
    assert g1["property"] == "Guayabal" and g1["plot"] == "11"
    assert g1["species"] == "Cedrela montana"
    assert g1["elevation_m"] == 2746.0


def test_el_estado_de_cada_arbol_por_monitoreo(mapa):
    estados = {t["id"]: t["states"] for t in mapa["trees"]}
    assert estados["G1"] == {"1": "bueno", "2": "bueno"}
    assert estados["G2"]["2"] == "regular"
    assert estados["G3"]["2"] == "malo"
    assert estados["G4"]["2"] == "muerto"
    assert estados["G5"]["2"] == "sin_dato"


def test_la_altura_viaja_para_el_historial_del_arbol(mapa):
    alturas = next(t["heights"] for t in mapa["trees"] if t["id"] == "G1")
    assert alturas == {"1": 0.4, "2": 0.7}
    muerto = next(t["heights"] for t in mapa["trees"] if t["id"] == "G4")
    assert muerto == {"1": 0.4, "2": None}


def test_un_arbol_sin_observacion_en_un_monitoreo_no_inventa_estado():
    """Un arbol censado en M2 no existia en M1: su estado en M1 es ausencia."""
    arboles = [*TREES, tree("N1", dx=60, dy=60)]
    obs_ = [*OBS, obs("N1", 2, 0.3)]
    mapa = build_map(arboles, obs_, 9377)
    nuevo = next(t for t in mapa["trees"] if t["id"] == "N1")
    assert "1" not in nuevo["states"] and nuevo["states"]["2"] == "bueno"


def test_los_bounds_encierran_todos_los_puntos(mapa):
    b = mapa["bounds"]
    lats = [t["lat"] for t in mapa["trees"]]
    lons = [t["lon"] for t in mapa["trees"]]
    assert b["south"] == pytest.approx(min(lats)) and b["north"] == pytest.approx(max(lats))
    assert b["west"] == pytest.approx(min(lons)) and b["east"] == pytest.approx(max(lons))


def test_los_predios_vienen_ordenados_para_el_filtro(mapa):
    assert mapa["properties"] == ["Guayabal", "Tres Jotas"]


def test_cada_parcela_trae_su_centroide_y_su_contorno(mapa):
    p11 = next(p for p in mapa["plots"] if p["plot"] == "11")
    assert p11["property"] == "Guayabal" and p11["n"] == 5
    # el quinto arbol esta dentro del cuadrado: el contorno son 4 vertices
    assert len(p11["hull"]) == 4
    # centroide del cuadrado de 40 m: el punto medio, 20 m al noreste de G1
    assert p11["centroid"]["lat"] == pytest.approx(5.799766, abs=0.00002)


def test_una_parcela_de_dos_arboles_no_tiene_area_pero_si_contorno(mapa):
    p12 = next(p for p in mapa["plots"] if p["plot"] == "12")
    assert len(p12["hull"]) == 2, "dos puntos dibujan una linea, no un poligono"
    p21 = next(p for p in mapa["plots"] if p["plot"] == "21")
    assert len(p21["hull"]) == 1


def test_la_supervivencia_por_parcela_es_la_del_analisis(mapa):
    """Mismo numero que publica E3: no puede haber dos verdades."""
    p11 = next(p for p in mapa["plots"] if p["plot"] == "11")
    assert p11["metrics"]["1"]["survival"] == pytest.approx(100.0)
    assert p11["metrics"]["2"]["survival"] == pytest.approx(80.0)  # 4 de 5
    assert p11["metrics"]["2"]["n"] == 5
    assert p11["metrics"]["2"]["mean_height"] == pytest.approx(0.75)  # (0.7+0.8+0.9+0.6)/4


def test_una_parcela_con_menos_de_cinco_arboles_se_marca(mapa):
    p12 = next(p for p in mapa["plots"] if p["plot"] == "12")
    assert p12["low_sample"] is True
    p11 = next(p for p in mapa["plots"] if p["plot"] == "11")
    assert p11["low_sample"] is False


def test_un_arbol_sin_coordenada_se_cuenta_pero_no_se_inventa():
    arboles = [*TREES, tree("SIN", coords=False, plot="11")]
    mapa = build_map(arboles, [*OBS, obs("SIN", 1, 0.2)], 9377)
    assert mapa["without_coordinates"] == 1
    assert [t["id"] for t in mapa["trees"] if t["id"] == "SIN"] == []
    p11 = next(p for p in mapa["plots"] if p["plot"] == "11")
    assert p11["n"] == 5, "la parcela se dibuja con los arboles que si ubicamos"


def test_un_proyecto_sin_datos_devuelve_un_mapa_vacio_valido():
    mapa = build_map([], [], 9377)
    assert mapa["trees"] == [] and mapa["plots"] == [] and mapa["monitorings"] == []
    assert mapa["bounds"] is None
    assert mapa["without_coordinates"] == 0


def test_el_contorno_por_predio_sirve_para_pedir_el_indice():
    """E10a: el NDVI se mide sobre el polígono de lo plantado, no sobre una
    finca dibujada a mano."""
    from agrosense.adapters.geo.map_payload import property_outlines

    contornos = property_outlines(TREES, 9377)
    assert sorted(contornos) == ["Guayabal", "Tres Jotas"]
    guayabal = contornos["Guayabal"]
    assert guayabal["trees"] == 7  # 5 de la parcela 11 + 2 de la 12
    w, s, e, n = guayabal["bbox"]
    assert w < e and s < n
    assert len(guayabal["hull"]) >= 3
    assert all(len(p) == 2 for p in guayabal["hull"])


def test_sin_coordenadas_no_hay_contornos():
    from agrosense.adapters.geo.map_payload import property_outlines

    assert property_outlines([tree("X", coords=False)], 9377) == {}

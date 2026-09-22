"""Comparación entre monitoreos (E4): qué pasó en el intervalo Mk−1 → Mk.

Datos sintéticos, con cada cifra comprobable a mano. El intervalo mide un año
exacto para que el crecimiento anualizado sea el mismo número que el
crecimiento, salvo en el test que lo comprueba con medio año.
"""

from datetime import date

import pytest

from agrosense.adapters.analysis.engine import analyze_monitoring
from agrosense.domain.entities import Observation, StatusSemantic, Tree

FECHAS = {1: date(2024, 1, 1), 2: date(2025, 1, 1)}


def tree(tid, species="Especie uno", prop="Predio A", plot="U1"):
    return Tree(
        tree_id=tid,
        species=species,
        locality=prop,
        plot_id=plot,
        sampling_unit_code=f"{prop}/{plot}",
        floristic_design="ABB",
        associated_cover="BG",
    )


def obs(tid, m, h, alive=True, phyto="Bueno"):
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


# A1 crece 50 cm · A2 se estanca (3 cm) · A3 muere · A4 se contrae 10 cm
# B1 (otro predio, otra especie) crece 20 cm y empeora de Bueno a Malo
TREES = [
    tree("A1"),
    tree("A2"),
    tree("A3"),
    tree("A4"),
    tree("B1", species="Especie dos", prop="Predio B", plot="U2"),
]
OBS = [
    obs("A1", 1, 1.00), obs("A1", 2, 1.50),
    obs("A2", 1, 1.00), obs("A2", 2, 1.03),
    obs("A3", 1, 1.00), obs("A3", 2, None, alive=False),
    obs("A4", 1, 1.00), obs("A4", 2, 0.90, phyto="Regular"),
    obs("B1", 1, 2.00), obs("B1", 2, 2.20, phyto="Malo"),
]


def section(payload, sid):
    return next(s for s in payload["sections"] if s["id"] == sid)


def table(payload, tid):
    for s in payload["sections"]:
        for t in s["tables"]:
            if t["id"] == tid:
                return t
    existentes = [t["id"] for t in section(payload, "comparacion")["tables"]]
    raise AssertionError(f"no existe la tabla {tid}; hay {existentes}")


@pytest.fixture(scope="module")
def payload():
    return analyze_monitoring(TREES, OBS, 2, dates=FECHAS)


def test_el_analisis_trae_la_seccion_de_comparacion(payload):
    s = section(payload, "comparacion")
    assert s["title"] == "Comparación M1 → M2"
    assert s["tables"], "la comparación debe traer tablas"


def test_el_resumen_del_intervalo_cuenta_vivos_muertos_y_estancados(payload):
    t = table(payload, "comparacion-resumen")
    fila = next(r for r in t["rows"] if r["property"] == "Predio A")
    assert fila["alive_prev"] == 4
    assert fila["deaths"] == 1
    assert fila["mortality"] == pytest.approx(25.0)
    # medidos en ambos: A1, A2, A4 (A3 murió)
    assert fila["measured"] == 3
    assert fila["stagnant"] == 2, "A2 (+3 cm) y A4 (−10 cm) no crecieron"
    assert fila["contractions"] == 1, "solo A4 bajó más de 5 cm"
    # (0.50 + 0.03 − 0.10) / 3
    assert fila["growth"] == pytest.approx(0.1433, abs=0.0001)


def test_el_pie_del_resumen_es_el_proyecto_entero(payload):
    t = table(payload, "comparacion-resumen")
    total = t["footer"][0]
    assert total["property"] == "Proyecto"
    assert total["alive_prev"] == 5 and total["deaths"] == 1
    assert total["mortality"] == pytest.approx(20.0)
    assert total["measured"] == 4


def test_el_crecimiento_anualizado_usa_las_fechas(payload):
    """Un año de calendario: anualizado ≈ crecimiento.

    2024 es bisiesto, así que el intervalo mide 366 días y el anualizado sale
    un 0,2 % por debajo. Que la diferencia exista es la prueba de que el
    denominador son días reales y no un «año» redondeado.
    """
    fila = next(
        r for r in table(payload, "comparacion-resumen")["rows"] if r["property"] == "Predio A"
    )
    assert fila["growth_year"] == pytest.approx(fila["growth"], rel=0.005)
    assert fila["growth_year"] < fila["growth"]


def test_medio_ano_duplica_el_crecimiento_anualizado():
    medio = {1: date(2024, 1, 1), 2: date(2024, 7, 1)}
    p = analyze_monitoring(TREES, OBS, 2, dates=medio)
    fila = next(r for r in table(p, "comparacion-resumen")["rows"] if r["property"] == "Predio A")
    assert fila["growth_year"] == pytest.approx(2 * fila["growth"], abs=0.002)


def test_sin_fechas_no_se_inventa_el_anualizado():
    p = analyze_monitoring(TREES, OBS, 2)
    t = table(p, "comparacion-resumen")
    assert "growth_year" not in {c["key"] for c in t["columns"]}
    assert any("fecha" in n.lower() for n in t["notes"]), "debe explicar por qué falta"


def test_por_especie_separa_lo_que_le_pasa_a_cada_una(payload):
    t = table(payload, "comparacion-especie-predio-a")
    assert t["property"] == "Predio A"
    fila = next(r for r in t["rows"] if r["species"] == "Especie uno")
    assert fila["alive_prev"] == 4 and fila["deaths"] == 1
    assert fila["stagnant"] == 2


def test_por_parcela_para_ver_donde_esta_el_problema(payload):
    t = table(payload, "comparacion-parcela")
    parcelas = {r["plot"]: r for r in t["rows"]}
    assert parcelas["Predio A/U1"]["deaths"] == 1
    assert parcelas["Predio B/U2"]["deaths"] == 0
    assert parcelas["Predio B/U2"]["growth"] == pytest.approx(0.20)


def test_la_transicion_fitosanitaria_dice_quien_empeoro(payload):
    t = table(payload, "comparacion-estado")
    fila = next(r for r in t["rows"] if r["from"] == "Bueno")
    assert fila["to_bueno"] == 2  # A1 y A2
    assert fila["to_regular"] == 1  # A4
    assert fila["to_malo"] == 1  # B1
    assert fila["to_muerto"] == 1  # A3
    assert fila["to_sin_dato"] == 0
    assert fila["total"] == 5


def test_el_primer_monitoreo_no_tiene_con_que_comparar():
    p = analyze_monitoring(TREES, OBS, 1, dates=FECHAS)
    s = section(p, "comparacion")
    assert s["tables"] == []
    assert any("primer monitoreo" in n.lower() for n in s["notes"])


def test_el_resumen_general_incluye_el_intervalo(payload):
    claves = {i["key"] for i in payload["summary"]}
    assert "interval_mortality" in claves and "interval_growth" in claves


def test_las_graficas_apuntan_a_tablas_que_existen(payload):
    s = section(payload, "comparacion")
    ids = {t["id"] for t in s["tables"]}
    assert s["charts"], "la comparación debe traer gráficas"
    for chart in s["charts"]:
        assert chart["table"] in ids

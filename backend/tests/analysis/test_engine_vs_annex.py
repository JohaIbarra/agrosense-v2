"""El motor reproduce las hojas que el ingeniero hizo a mano en el Anexo 1.

Criterio de salida de E3 (docs/superpowers/plans/2026-09-22-e2e3-…): las cifras
de AgroSense COINCIDEN con las de las hojas Composicion, Alturas, Diametro de
copa, Supervivencia, Estado fito, Edades y DAP del Anexo 1, calculadas solo
desde la hoja de datos crudos `Monitoreo_4`.

Los valores esperados se copiaron de las hojas (celda citada en cada caso).
Donde la hoja se contradice a si misma, se anota y no se usa como referencia.
"""

from pathlib import Path

import pandas as pd
import pytest

from agrosense.adapters.analysis.engine import analyze_monitoring
from agrosense.adapters.ingester.ingest import ingest_wide

REFERENCE_PATH = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"

pytestmark = pytest.mark.skipif(
    not REFERENCE_PATH.exists(),
    reason="dataset de referencia local ausente (data/raw/anexo1.xlsx)",
)

ABB = "Ampliación de borde de bosque"
EEN = "Enriquecimiento con especies nativas en estados sucesionales intermedias y avanzadas"
RV = "Rehabilitación vegetal"
ETX = "Enriquecimiento tipo X en Mosaico de pastos con Espacios naturales"
BG = "Bosque de galería"
BF = "Bosque fragmentado"
MPEN = "Mosaico de pastos con espacios naturales"
VGT = "Vegetación secundaria o en transición"


@pytest.fixture(scope="module")
def m4():
    data = ingest_wide(pd.read_excel(REFERENCE_PATH, sheet_name="Monitoreo_4"))
    return analyze_monitoring(data.trees, data.observations, 4)


def table(payload, tid):
    for s in payload["sections"]:
        for t in s["tables"]:
            if t["id"] == tid:
                return t
    raise AssertionError(f"tabla {tid} no existe")


def row(t, key, value):
    return next(r for r in t["rows"] if r[key] == value)


def key(t, label, group=None):
    return next(c["key"] for c in t["columns"] if c["label"] == label and c.get("group") == group)


approx = pytest.approx


# ── Composicion ──────────────────────────────────────────────────────────────


def test_composicion_guayabal_por_diseno(m4):
    # Hoja «Composición», bloque «GUAYABAL - COMPOSICIÓN POR DISEÑO FLORÍSTICO -M4» (R3:X27)
    t = table(m4, "composicion-guayabal-design")
    abb, een, rv = key(t, ABB), key(t, EEN), key(t, RV)
    cedrela = row(t, "species", "Cedrela montana")
    assert (cedrela[abb], cedrela[een], cedrela[rv], cedrela["total"]) == (8, 2, 4, 14)
    montanoa = row(t, "species", "Montanoa quadrangularis")
    assert (montanoa[abb], montanoa[rv], montanoa["total"]) == (28, 21, 49)
    total = t["footer"][0]
    assert (total[abb], total[een], total[rv], total["total"]) == (171, 10, 99, 280)


def test_composicion_guayabal_por_cobertura(m4):
    # «GUAYABAL - COMPOSICIÓN POR CV» (AA3:AH27). El titulo de la hoja dice M3,
    # pero sus totales (280) son los vivos de M4: se compara contra M4.
    t = table(m4, "composicion-guayabal-cover")
    total = t["footer"][0]
    assert (total[key(t, BG)], total[key(t, BF)], total[key(t, MPEN)], total[key(t, VGT)]) == (
        120,
        51,
        99,
        10,
    )
    cedrela = row(t, "species", "Cedrela montana")
    assert (
        cedrela[key(t, BG)],
        cedrela[key(t, BF)],
        cedrela[key(t, MPEN)],
        cedrela[key(t, VGT)],
    ) == (
        3,
        5,
        4,
        2,
    )


def test_composicion_tres_jotas(m4):
    # «Tres Jotas - Composición por DF» (AL3:AR31) y «por CV» (AU3:AZ31)
    t = table(m4, "composicion-tres-jotas-design")
    total = t["footer"][0]
    assert (total[key(t, ABB)], total[key(t, ETX)], total[key(t, RV)], total["total"]) == (
        176,
        57,
        141,
        374,
    )
    dodonaea = row(t, "species", "Dodonaea viscosa")
    assert (dodonaea[key(t, ABB)], dodonaea[key(t, ETX)], dodonaea[key(t, RV)]) == (23, 6, 21)
    t = table(m4, "composicion-tres-jotas-cover")
    brunellia = row(t, "species", "Brunellia subsessilis")
    assert (brunellia[key(t, BG)], brunellia[key(t, MPEN)], brunellia["total"]) == (5, 8, 13)


def test_composicion_san_antonio(m4):
    # Tabla dinamica BD3:BE17 («Cuenta de Especie_M1», San Antonio = 64)
    t = table(m4, "composicion-san-antonio-design")
    assert t["footer"][0]["total"] == 64
    assert row(t, "species", "Tecoma stans")["total"] == 14
    assert row(t, "species", "Inga punctata")["total"] == 10


# ── Alturas ──────────────────────────────────────────────────────────────────


def test_alturas_tres_jotas_por_cobertura(m4):
    # Tabla dinamica A3:D33 «Promedio de Altura total (m)_M4»
    t = table(m4, "alturas-proyecto-cover")
    tj = row(t, "property", "Tres Jotas")
    assert tj[key(t, BG)] == approx(0.7345, abs=1e-4)
    assert tj[key(t, MPEN)] == approx(0.682449, abs=1e-5)
    assert tj["total"] == approx(0.706944, abs=1e-5)


def test_alturas_tres_jotas_especie_por_diseno(m4):
    # «Alturas promedio por Diseño - Tres Jotas M4» (AH3:AO33)
    t = table(m4, "alturas-tres-jotas-design")
    b = row(t, "species", "Brunellia subsessilis")
    assert b[key(t, "M3", ABB)] == approx(0.7917, abs=1e-4)
    assert b[key(t, "M4", ABB)] == approx(1.362, abs=1e-4)
    assert b[key(t, "M3", ETX)] == approx(0.33, abs=1e-4)
    assert b[key(t, "M4", ETX)] == approx(0.5067, abs=1e-4)
    assert b[key(t, "M3", RV)] == approx(0.562, abs=1e-4)
    assert b[key(t, "M4", RV)] == approx(0.82, abs=1e-4)
    assert b["cp"] == approx(0.335, abs=1e-3)


def test_alturas_tres_jotas_especie_por_cobertura(m4):
    # «Alturas promedio por cobertura - Tres Jotas M4» (AR3:AW33)
    t = table(m4, "alturas-tres-jotas-cover")
    b = row(t, "species", "Brunellia subsessilis")
    assert b[key(t, "M3", MPEN)] == approx(0.4589, abs=1e-4)
    assert b[key(t, "M4", MPEN)] == approx(0.7025, abs=1e-4)
    assert b["cp"] == approx(0.407, abs=1e-3)


def test_alturas_guayabal_por_diseno_y_cp(m4):
    # «Guayabal m4» (K3:S27)
    t = table(m4, "alturas-guayabal-design")
    cav = row(t, "species", "Cavendishia bracteata")
    assert cav[key(t, "M4", ABB)] == approx(0.6689, abs=1e-4)
    # En este bloque la columna M3 de la hoja esta escrita a mano con dos
    # decimales (0,52; 0,33; 0,39…): el valor exacto es 0,5244. Se compara a la
    # precision de la hoja, y el CP hereda ese redondeo.
    assert cav[key(t, "M3", ABB)] == approx(0.52, abs=0.005)
    assert cav["cp"] == approx(0.1489, abs=0.005)
    # Cedrela: la hoja da CP 0,053 porque escribe 0,23 en EEN-M4, pero los dos
    # arboles vivos de EEN en M4 miden 0,20 y 0,20 (filas 709 y 716 de
    # Monitoreo_4): error de transcripcion de la hoja. Se verifican las celdas.
    ced = row(t, "species", "Cedrela montana")
    assert ced[key(t, "M4", EEN)] == approx(0.20)
    assert ced[key(t, "M3", EEN)] == approx(0.2333, abs=1e-4)
    assert ced[key(t, "M4", RV)] == approx(0.795, abs=1e-4)
    assert row(t, "species", "Verbesina arborea")["cp"] == approx(0.519, abs=1e-3)


def test_alturas_guayabal_por_cobertura(m4):
    # «Alturas promedio por COBERTURA - Guayabal M4» (V3:AE27)
    t = table(m4, "alturas-guayabal-cover")
    cav = row(t, "species", "Cavendishia bracteata")
    assert cav[key(t, "M4", BF)] == approx(0.8067, abs=1e-4)
    assert cav[key(t, "M3", BF)] == approx(0.6183, abs=1e-4)
    assert cav["cp"] == approx(0.1225, abs=1e-4)


def test_alturas_san_antonio_por_especie(m4):
    # «Alturas promedio - Predio San Antonio» (BE4:BH18) y tabla BA3:BB19
    t = table(m4, "alturas-san-antonio-especie")
    cav = row(t, "species", "Cavendishia bracteata")
    assert cav["prev"] == approx(0.502, abs=1e-3)
    assert cav["cur"] == approx(0.605, abs=1e-3)
    assert row(t, "species", "Senna viarum")["cur"] == approx(0.974, abs=1e-3)
    assert t["footer"][0]["cur"] == approx(0.60078125)


# ── Diametro de copa ─────────────────────────────────────────────────────────


def test_copa_guayabal_por_diseno(m4):
    # «DC - Guayabal M3 -DISEÑO FLORISTICO» (J2:Q26)
    t = table(m4, "copa-guayabal-design")
    ced = row(t, "species", "Cedrela montana")
    assert ced[key(t, "M4", ABB)] == approx(0.3619, abs=1e-4)
    assert ced[key(t, "M3", ABB)] == approx(0.335, abs=1e-4)
    assert ced[key(t, "M4", RV)] == approx(0.6075, abs=1e-4)
    assert ced[key(t, "M3", RV)] == approx(0.5125, abs=1e-4)
    assert ced["cp"] == approx(-0.0233, abs=1e-4)
    assert row(t, "species", "Cavendishia bracteata")["cp"] == approx(0.0556, abs=1e-4)


def test_copa_tres_jotas_por_diseno(m4):
    # «DC - Tres Jotas - DF - M4» (AF2:AM32)
    t = table(m4, "copa-tres-jotas-design")
    b = row(t, "species", "Brunellia subsessilis")
    assert b[key(t, "M3", ABB)] == approx(1.125, abs=1e-4)
    assert b[key(t, "M4", ABB)] == approx(1.444, abs=1e-4)
    assert b["cp"] == approx(0.2857, abs=1e-4)


def test_copa_san_antonio(m4):
    # Tabla dinamica AX3:AY18 «Promedio de Diámetro. Copa (m)_M4» y BA3:BD16
    t = table(m4, "copa-san-antonio-especie")
    assert t["footer"][0]["cur"] == approx(0.3681, abs=1e-4)
    cav = row(t, "species", "Cavendishia bracteata")
    assert (cav["prev"], cav["cur"]) == (approx(0.3275, abs=1e-4), approx(0.385, abs=1e-4))
    # La fila TOTAL de la hoja (0,2978 / 0,3291) es la media de las medias por
    # especie, distinta de su propia dinamica (0,3681): no se usa como referencia.


# ── Supervivencia ────────────────────────────────────────────────────────────


def test_supervivencia_guayabal(m4):
    # «GUAYABAL - M4» (I3:O49): %Sup./especie, %Sup./arreglo y % predio
    t = table(m4, "supervivencia-guayabal-especie")
    cav = next(
        r for r in t["rows"] if r["design"] == ABB and r["species"] == "Cavendishia bracteata"
    )
    assert (cav["alive"], cav["dead"], cav["pct"]) == (9, 1, approx(90.0))
    mol = next(
        r for r in t["rows"] if r["design"] == ABB and r["species"] == "Mollinedia tomentosa"
    )
    assert mol["pct"] == approx(0.0)
    t = table(m4, "supervivencia-guayabal-design")
    abb = row(t, "value", ABB)
    assert abb["pct"] == approx(82.61, abs=0.01)
    assert abb["pct_prev"] == approx(88.88, abs=0.01)  # Q6 «Sobrevivemcia_M1» M3
    assert row(t, "value", EEN)["pct"] == approx(40.0)
    assert row(t, "value", RV)["pct"] == approx(84.62, abs=0.01)
    assert t["footer"][0]["pct"] == approx(80.23, abs=0.01)


def test_supervivencia_guayabal_por_cobertura(m4):
    # «Analisis por cobertura - predio Guayabal» (W5:Z7)
    t = table(m4, "supervivencia-guayabal-cover")
    bg, bf = row(t, "value", BG), row(t, "value", BF)
    assert (bg["pct_prev"], bg["pct"]) == (approx(95.65, abs=0.01), approx(86.96, abs=0.01))
    assert (bf["pct_prev"], bf["pct"]) == (approx(75.36, abs=0.01), approx(73.91, abs=0.01))


# ── Estado fitosanitario ─────────────────────────────────────────────────────


def test_estado_fito_guayabal(m4):
    # «PREDIO GUAYABAL» (I1:S…): % Especie, % D.F. y % Predio
    t = table(m4, "estado-guayabal-especie")
    cav = next(
        r for r in t["rows"] if r["design"] == ABB and r["species"] == "Cavendishia bracteata"
    )
    assert (cav["good"], cav["fair"], cav["poor"]) == (7, 2, 0)
    assert cav["pct_good"] == approx(77.78, abs=0.01)
    t = table(m4, "estado-guayabal-design")
    abb = row(t, "value", ABB)
    assert (abb["pct_good"], abb["pct_poor"], abb["pct_fair"]) == (
        approx(95.32, abs=0.01),
        approx(1.17, abs=0.01),
        approx(3.51, abs=0.01),
    )
    assert t["footer"][0]["pct_good"] == approx(95.0, abs=0.01)
    t = table(m4, "estado-guayabal-cover")
    bg = row(t, "value", BG)
    assert (bg["pct_good"], bg["pct_poor"], bg["pct_fair"]) == (
        approx(95.0, abs=0.01),
        approx(1.67, abs=0.01),
        approx(3.33, abs=0.01),
    )


def test_estado_global(m4):
    # «ESTADO GLOBAL» (CC3:CE7): Bueno 675, Malo 8, Regular 35, total 718
    total = table(m4, "estado-global")["footer"][0]
    assert (total["good"], total["poor"], total["fair"], total["total"]) == (675, 8, 35, 718)
    assert total["pct_good"] == approx(94.01, abs=0.01)


# ── Edades ───────────────────────────────────────────────────────────────────


def test_edades_guayabal_por_diseno(m4):
    # «Guayabal M4» (R9:AD15): categoria x diseno, M3 y M4
    t = table(m4, "edades-guayabal-design")
    abb = row(t, "value", ABB)
    pl_p, pl_c = key(t, "M3", "Plántula"), key(t, "M4", "Plántula")
    j1_p, j1_c = key(t, "M3", "Juvenil I"), key(t, "M4", "Juvenil I")
    j2_p, j2_c = key(t, "M3", "Juvenil II"), key(t, "M4", "Juvenil II")
    assert (abb[pl_p], abb[pl_c], abb[j1_p], abb[j1_c], abb[j2_p], abb[j2_c]) == (
        104,
        60,
        80,
        110,
        0,
        1,
    )
    rv = row(t, "value", RV)
    assert (rv[pl_p], rv[pl_c], rv[j1_p], rv[j1_c], rv[j2_c]) == (24, 13, 77, 84, 2)
    total = t["footer"][0]
    assert (total["total_prev"], total["total"]) == (298, 280)


def test_edades_san_antonio(m4):
    # Tabla dinamica J21:N24 «Cuenta de Categoria M4»: 33 juveniles I, 31 plantulas
    t = table(m4, "edades-san-antonio-design")
    total = t["footer"][0]
    assert total[key(t, "M4", "Juvenil I")] == 33
    assert total[key(t, "M4", "Plántula")] == 31


# ── DAP ──────────────────────────────────────────────────────────────────────


def test_dap_guayabal(m4):
    # «Guayabal por DF» (I1:P25) y dinamica A1:F25 «Promedio de DAP (CM) M3»
    t = table(m4, "dap-guayabal-design")
    mon = row(t, "species", "Montanoa quadrangularis")
    assert mon[key(t, "M3", ABB)] == approx(2.44, abs=1e-4)
    assert mon[key(t, "M4", ABB)] == approx(2.9488, abs=1e-4)
    assert mon[key(t, "M3", RV)] == approx(2.38, abs=1e-4)
    assert mon[key(t, "M4", RV)] == approx(3.2468, abs=1e-4)
    verb = row(t, "species", "Verbesina arborea")
    assert verb[key(t, "M4", RV)] == approx(2.8648, abs=1e-4)
    media = t["footer"][0]
    assert media[key(t, "M3", ABB)] == approx(2.2286, abs=1e-4)
    assert media[key(t, "M3", RV)] == approx(2.1154, abs=1e-4)
    t = table(m4, "dap-guayabal-especie")
    assert t["footer"][0]["prev"] == approx(2.155, abs=1e-3)

"""Motor del analisis exploratorio (E3) sobre datos sinteticos: cada numero
se puede comprobar a mano."""

import json

import pytest

from agrosense.adapters.analysis.engine import ANALYSIS_VERSION, analyze_monitoring, input_hash
from agrosense.domain.entities import Observation, StatusSemantic, Tree


def tree(tid, species, design="ABB", cover="BG", prop="Predio A", family="Fam", guild="Inicial"):
    return Tree(
        tree_id=tid,
        species=species,
        family=family,
        guild=guild,
        locality=prop,
        floristic_design=design,
        associated_cover=cover,
        sampling_unit_code=f"U-{prop}",
    )


def obs(tid, m, h, alive=True, crown=None, dap=None, phyto="Bueno"):
    return Observation(
        tree_id=tid,
        campaign=m,
        height_m=h,
        crown_diameter_m=crown,
        dap_cm=dap,
        dap_status=StatusSemantic.MEDIDO if dap else StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary=phyto if alive else None,
        alive=alive,
        colonization=None,
    )


TREES = [
    tree("A1", "Especie uno", design="ABB", cover="BG"),
    tree("A2", "Especie uno", design="RV", cover="BG"),
    tree("A3", "Especie dos", design="ABB", cover="MP"),
    tree("A4", "Especie dos", design="RV", cover="MP"),
    tree("B1", "Especie uno", design="ABB", cover="BG", prop="Predio B"),
]
OBS = [
    obs("A1", 1, 0.2, crown=0.1),
    obs("A1", 2, 0.4, crown=0.2, dap=1.5),
    obs("A2", 1, 0.3, crown=0.1),
    obs("A2", 2, 0.6, crown=0.3, phyto="Regular"),
    obs("A3", 1, 0.5),
    obs("A3", 2, None, alive=False),
    obs("A4", 1, 1.0),
    obs("A4", 2, 3.5, phyto="Malo"),
    obs("B1", 1, 0.4),
    obs("B1", 2, 0.5),
]


def section(payload, sid):
    return next(s for s in payload["sections"] if s["id"] == sid)


def table(payload, tid):
    for s in payload["sections"]:
        for t in s["tables"]:
            if t["id"] == tid:
                return t
    raise AssertionError(f"tabla {tid} no existe")


def row(t, key, value):
    return next(r for r in t["rows"] if r[key] == value)


def col_key(t, label, group=None):
    return next(c["key"] for c in t["columns"] if c["label"] == label and c.get("group") == group)


@pytest.fixture(scope="module")
def m2():
    return analyze_monitoring(TREES, OBS, 2)


def test_payload_is_json_and_versioned(m2):
    json.dumps(m2)  # sin NaN ni tipos de numpy
    assert m2["analysis_version"] == ANALYSIS_VERSION
    assert m2["monitoring"] == 2 and m2["previous"] == 1
    assert [s["id"] for s in m2["sections"]] == [
        "composicion",
        "alturas",
        "copa",
        "supervivencia",
        "estado_fitosanitario",
        "edades",
        "dap",
        "comparacion",
    ]


def test_every_chart_references_an_existing_table_and_columns(m2):
    for s in m2["sections"]:
        ids = {t["id"]: t for t in s["tables"]}
        for c in s["charts"]:
            assert c["table"] in ids, c["id"]
            keys = {col["key"] for col in ids[c["table"]]["columns"]}
            assert c["x"] in keys and set(c["series"]) <= keys, c["id"]


def test_composition_counts_only_living_trees(m2):
    t = table(m2, "composicion-predio-a-design")
    abb, rv = col_key(t, "ABB"), col_key(t, "RV")
    uno = row(t, "species", "Especie uno")
    assert (uno[abb], uno[rv], uno["total"]) == (1, 1, 2)
    dos = row(t, "species", "Especie dos")  # A3 murio en M2
    assert (dos[abb], dos[rv], dos["total"]) == (0, 1, 1)
    assert t["footer"][0]["total"] == 3


def test_heights_mean_per_monitoring_and_growth(m2):
    t = table(m2, "alturas-predio-a-especie")
    uno = row(t, "species", "Especie uno")
    assert uno["prev"] == pytest.approx(0.25)
    assert uno["cur"] == pytest.approx(0.5)
    assert uno["growth"] == pytest.approx(0.25)
    dos = row(t, "species", "Especie dos")
    # M1 incluye a A3, que luego muere: la media de cada monitoreo es de SUS vivos
    assert dos["prev"] == pytest.approx(0.75)
    assert dos["cur"] == pytest.approx(3.5)


def test_heights_by_design_cp_is_mean_of_cell_growths(m2):
    t = table(m2, "alturas-predio-a-design")
    uno = row(t, "species", "Especie uno")
    abb_p, abb_c = col_key(t, "M1", "ABB"), col_key(t, "M2", "ABB")
    assert (uno[abb_p], uno[abb_c]) == (pytest.approx(0.2), pytest.approx(0.4))
    # crecimientos de celda: ABB 0.2, RV 0.3 -> CP 0.25
    assert uno["cp"] == pytest.approx(0.25)


def test_survival_by_design(m2):
    t = table(m2, "supervivencia-predio-a-design")
    abb = row(t, "value", "ABB")
    assert (abb["alive"], abb["dead"], abb["total"]) == (1, 1, 2)
    assert abb["pct"] == pytest.approx(50.0)
    assert abb["pct_prev"] == pytest.approx(100.0)
    assert abb["_flags"] == ["low_sample"]  # 2 arboles: porcentaje marcado
    assert t["footer"][0]["pct"] == pytest.approx(75.0)


def test_survival_evolution_by_property(m2):
    t = table(m2, "supervivencia-proyecto")
    a = row(t, "property", "Predio A")
    assert a["m1"] == pytest.approx(100.0) and a["m2"] == pytest.approx(75.0)


def test_phytosanitary_counts_living_only(m2):
    t = table(m2, "estado-global")
    a = row(t, "property", "Predio A")
    assert (a["good"], a["fair"], a["poor"], a["total"]) == (1, 1, 1, 3)
    assert a["pct_good"] == pytest.approx(100 / 3)


def test_development_classes(m2):
    t = table(m2, "edades-proyecto")
    assert row(t, "category", "Muertos")["m2"] == 1
    # A1 0.4 y B1 0.5 plantula; A2 0.6 juvenil I; A4 3.5 juvenil II
    assert row(t, "category", "Plántula")["m2"] == 2
    assert row(t, "category", "Juvenil I")["m2"] == 1
    assert row(t, "category", "Juvenil II")["m2"] == 1


def test_dap_only_measured(m2):
    t = table(m2, "dap-predio-a-especie")
    uno = row(t, "species", "Especie uno")
    assert uno["cur"] == pytest.approx(1.5) and uno["n"] == 1


def test_first_monitoring_has_no_previous_columns():
    m1 = analyze_monitoring(TREES, OBS, 1)
    assert m1["previous"] is None
    t = table(m1, "alturas-predio-a-especie")
    assert {c["key"] for c in t["columns"]} >= {"species", "cur"}
    assert "prev" not in {c["key"] for c in t["columns"]}
    assert section(m1, "dap")["notes"]


def test_unknown_monitoring_raises():
    with pytest.raises(ValueError):
        analyze_monitoring(TREES, OBS, 7)


def test_input_hash_changes_with_data():
    h1 = input_hash(TREES, OBS)
    assert h1 == input_hash(list(reversed(TREES)), list(reversed(OBS)))
    assert h1 != input_hash(TREES, OBS[:-1])

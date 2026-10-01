"""Features de mortalidad (E8, plan D2/D4): relativas a la ola y sin fuga."""
from __future__ import annotations

from agrosense.ml.mortality_features import (
    GENERAL_FEATURES,
    PROJECT_CATEGORICAL,
    PROJECT_NUMERIC,
    build_mortality_wave,
    mortality_fingerprint,
)
from tests.ml.builders import obs, tree

TREES = [tree("A"), tree("B", species="Inga punctata"), tree("C"), tree("D")]


def _obs(c_next_alive=False):
    return [
        obs("A", 1, 0.30), obs("A", 2, 0.30),
        obs("B", 1, 0.50), obs("B", 2, 0.70),
        obs("C", 1, 0.40), obs("C", 2, 0.50),
        obs("D", 1, 0.20), obs("D", 2, None, alive=False),  # muerto en t=2
        obs("A", 3, None, alive=False), obs("B", 3, 0.8),
        obs("C", 3, 0.6 if c_next_alive else None, alive=c_next_alive),
    ]


def test_h_pct_is_the_height_percentile_within_the_wave():
    rows = {r.tree_id: r for r in build_mortality_wave(TREES, _obs(), 2, labeled=False)}
    assert set(rows) == {"A", "B", "C"}  # D no esta en riesgo en t=2
    assert rows["A"].features["h_pct"] == 1 / 3
    assert rows["C"].features["h_pct"] == 2 / 3
    assert rows["B"].features["h_pct"] == 1.0


def test_labels_follow_the_domain_rule():
    rows = {r.tree_id: r.label for r in build_mortality_wave(TREES, _obs(), 2, labeled=True)}
    assert rows == {"A": True, "B": False, "C": True}


def test_h_pct_is_computed_on_the_whole_population_at_risk_not_only_labeled():
    # Sin dato de C en t+1, C sale de la etiqueta pero sigue contando para el percentil:
    # entrenamiento y servicio calculan h_pct sobre la misma poblacion.
    o = [x for x in _obs() if not (x.tree_id == "C" and x.campaign == 3)]
    labeled = {r.tree_id: r for r in build_mortality_wave(TREES, o, 2, labeled=True)}
    serve = {r.tree_id: r for r in build_mortality_wave(TREES, o, 2, labeled=False)}
    assert "C" not in labeled
    assert labeled["A"].features == serve["A"].features


def test_features_do_not_look_at_the_future():
    a = build_mortality_wave(TREES, _obs(c_next_alive=False), 2, labeled=False)
    b = build_mortality_wave(TREES, _obs(c_next_alive=True), 2, labeled=False)
    assert [r.features for r in a] == [r.features for r in b]
    fp = mortality_fingerprint
    assert fp(TREES, _obs(False), 2) == fp(TREES, _obs(True), 2)


def test_history_features_and_categories():
    rows = {r.tree_id: r for r in build_mortality_wave(TREES, _obs(), 2, labeled=False)}
    assert rows["A"].features["estanco_lag"] == 1.0
    assert rows["B"].features["dh_lag"] == 0.7 - 0.5
    assert rows["B"].features["species"] == "inga punctata"
    assert set(GENERAL_FEATURES) <= set(rows["A"].features)
    assert set(PROJECT_NUMERIC + PROJECT_CATEGORICAL) <= set(rows["A"].features)

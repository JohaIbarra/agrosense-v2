"""Featurizacion del modelo de estancamiento: relativa a la ola y sin fugas."""
from __future__ import annotations

import re

import pytest

from agrosense.ml.stall_features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    build_wave,
    fingerprint,
)
from tests.ml.builders import obs, tree


def _dataset():
    trees = [
        tree("A", plot="U1"),
        tree("B", plot="U2", species="Cedrela montana"),
        tree("C", plot="U1"),
    ]
    observations = [
        obs("A", 1, 0.40, crown=0.20),
        obs("A", 2, 0.40, crown=0.25, phyto="Regular"),
        obs("A", 3, 0.40, crown=0.30),
        obs("B", 1, 0.50),
        obs("B", 2, 0.60),
        obs("B", 3, 0.70),
        obs("C", 2, 0.30),  # C entra en M2 (sin historia)...
        obs("C", 3, 0.30, alive=False),  # ...y muere en M3
    ]
    return trees, observations


def test_feature_names_are_wave_relative():
    # Protocolo §10, "test de smoke anti-leakage": nada de altura_M3.
    for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        assert not re.search(r"_m\d+$", name.lower()), name


def test_labeled_wave_keeps_trees_alive_and_measured_in_t_and_t_plus_1():
    trees, observations = _dataset()
    rows = build_wave(trees, observations, 2, labeled=True)
    assert [r.tree_id for r in rows] == ["A", "B"]
    assert [r.label for r in rows] == [True, False]
    assert all(r.wave == 2 for r in rows)


def test_unlabeled_wave_keeps_every_tree_alive_and_measured_in_t():
    trees, observations = _dataset()
    rows = build_wave(trees, observations, 2, labeled=False)
    assert [r.tree_id for r in rows] == ["A", "B", "C"]
    assert all(r.label is None for r in rows)


def test_lag_features():
    trees, observations = _dataset()
    rows = {r.tree_id: r.features for r in build_wave(trees, observations, 2, labeled=True)}
    a = rows["A"]
    assert a["h_t"] == 0.40
    assert a["h_prev"] == 0.40
    assert a["dh_lag"] == 0.0
    assert a["estanco_lag"] == 1.0
    assert a["dcopa_lag"] == pytest.approx(0.05)
    assert a["fito_empeoro"] == 1.0
    # Fix wave 1a: las categoricas viajan normalizadas (NFC/strip/casefold).
    assert a["fito_t"] == "regular"
    assert a["esbeltez_t"] == pytest.approx(0.40 / 0.25)
    assert (a["species"], a["locality"], a["monitoring_unit"]) == (
        "senna viarum",
        "guayabal",
        "parcela",
    )
    b = rows["B"]
    assert b["estanco_lag"] == 0.0
    assert b["dh_lag"] == pytest.approx(0.10)


def test_tree_without_history_has_missing_lags():
    trees, observations = _dataset()
    rows = {r.tree_id: r.features for r in build_wave(trees, observations, 2, labeled=False)}
    c = rows["C"]
    for name in ("dh_lag", "dcopa_lag", "estanco_lag", "h_prev", "fito_empeoro"):
        assert c[name] is None, name


def test_features_never_read_the_future():
    trees, observations = _dataset()
    futuro = [
        o.model_copy(update={"height_m": 9.0, "crown_diameter_m": 9.9, "phytosanitary": "Malo"})
        if o.campaign == 3 and o.alive
        else o
        for o in observations
    ]
    antes = [r.features for r in build_wave(trees, observations, 2, labeled=True)]
    despues = [r.features for r in build_wave(trees, futuro, 2, labeled=True)]
    assert antes == despues


def test_zero_crown_gives_missing_slenderness():
    rows = build_wave([tree("A")], [obs("A", 1, 0.4, crown=0.0)], 1, labeled=False)
    assert rows[0].features["esbeltez_t"] is None


def test_categorical_values_are_normalized_for_train_serve_parity():
    # Fix wave 1a: distintas grafias del mismo valor (espacios, mayusculas,
    # NFC/NFD) deben producir la MISMA categoria; si no, un valor escrito
    # distinto en el archivo servido queda como "no visto" aunque sea el
    # mismo valor que entreno el modelo.
    import unicodedata

    nfc = "Bogotá"
    nfd = unicodedata.normalize("NFD", nfc)  # misma cadena, otra forma Unicode
    t1 = tree("A", species="Senna viarum", locality=nfc, unit="Parcela")
    t2 = tree("B", species="  Senna Viarum", locality=f"  {nfc.upper()} ", unit="PARCELA")
    t3 = tree("C", species="Senna viarum", locality=nfd, unit="Parcela")
    rows = {
        r.tree_id: r.features
        for r in build_wave(
            [t1, t2, t3],
            [obs("A", 1, 0.4), obs("B", 1, 0.4), obs("C", 1, 0.4)],
            1,
            labeled=False,
        )
    }
    assert rows["A"]["species"] == rows["B"]["species"]
    assert rows["A"]["locality"] == rows["B"]["locality"] == rows["C"]["locality"]
    assert rows["A"]["monitoring_unit"] == rows["B"]["monitoring_unit"]


def test_plot_is_the_grouping_key_not_a_feature():
    trees, observations = _dataset()
    row = build_wave(trees, observations, 2, labeled=True)[0]
    assert row.plot == "U1"
    assert "plot" not in row.features
    assert "sampling_unit_code" not in row.features


def test_fingerprint_ignores_later_monitorings_only():
    trees, observations = _dataset()
    con_m4 = observations + [obs("B", 4, 0.9)]
    assert fingerprint(trees, observations, 3) == fingerprint(trees, con_m4, 3)
    corregido = [
        o.model_copy(update={"height_m": 0.41}) if (o.tree_id, o.campaign) == ("A", 2) else o
        for o in observations
    ]
    assert fingerprint(trees, observations, 3) != fingerprint(trees, corregido, 3)

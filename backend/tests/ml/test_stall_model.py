"""Modelo servible: artefacto JSON validado y scoring en Python puro."""
from __future__ import annotations

import hashlib
import json

import pytest

from agrosense.ml.preprocessing import fit_preprocessor
from agrosense.ml.stall_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, build_wave
from agrosense.ml.stall_model import StallModelError, load_stall_model, sigmoid
from tests.ml.builders import artifact_dict, synthetic_panel

CARD_KEYS = {
    "model_version",
    "artifact_sha256",
    "dataset_sha256",
    "trained_on",
    "pr_auc",
    "pr_auc_ci_low",
    "pr_auc_ci_high",
    "roc_auc",
    "prevalence_pct",
    "recall_at_budget_pct",
    "precision_at_budget_pct",
}


def _artifact():
    trees, observations = synthetic_panel()
    rows = build_wave(trees, observations, 2, labeled=False)
    params = fit_preprocessor([r.features for r in rows], NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    coefficients = [0.0] * len(params.feature_names)
    coefficients[params.feature_names.index("estanco_lag")] = 2.0
    return trees, observations, artifact_dict(params, coefficients, -1.0)


def _write(tmp_path, data) -> object:
    path = tmp_path / "stall.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_sigmoid_is_stable_at_the_extremes():
    assert sigmoid(1000.0) == 1.0
    assert sigmoid(-1000.0) == 0.0
    assert sigmoid(0.0) == 0.5


def test_load_roundtrip(tmp_path):
    _, _, data = _artifact()
    path = _write(tmp_path, data)
    model = load_stall_model(path)
    assert model.model_version == "stall-test-1"
    assert model.artifact_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert model.known_species == frozenset({"Lenta lenta", "Rapida rapida"})
    assert set(model.model_card) == CARD_KEYS
    assert model.model_card["pr_auc_ci_low"] == 0.36


def test_predict_scores_every_tree_alive_and_measured_in_t(tmp_path):
    trees, observations, data = _artifact()
    model = load_stall_model(_write(tmp_path, data))
    probs = model.predict(trees, observations, 3)
    assert set(probs) == {r.tree_id for r in build_wave(trees, observations, 3, labeled=False)}
    assert all(0.0 < p < 1.0 for p in probs.values())
    rows = {r.tree_id: r for r in build_wave(trees, observations, 3, labeled=False)}
    stalled = [probs[t] for t, r in rows.items() if r.features["estanco_lag"] == 1.0]
    grew = [probs[t] for t, r in rows.items() if r.features["estanco_lag"] == 0.0]
    assert min(stalled) > max(grew)  # coeficiente positivo en estanco_lag


def test_missing_artifact_is_a_model_error(tmp_path):
    with pytest.raises(StallModelError):
        load_stall_model(tmp_path / "no-existe.json")


def test_invalid_json_is_a_model_error(tmp_path):
    path = tmp_path / "roto.json"
    path.write_text("{no es json", encoding="utf-8")
    with pytest.raises(StallModelError):
        load_stall_model(path)


@pytest.mark.parametrize("key", ["features_version", "preprocessing_version", "format"])
def test_artifact_from_another_version_is_rejected(tmp_path, key):
    _, _, data = _artifact()
    data[key] = "otra"
    with pytest.raises(StallModelError):
        load_stall_model(_write(tmp_path, data))


def test_coefficients_must_match_the_features(tmp_path):
    _, _, data = _artifact()
    data["model"]["coefficients"] = data["model"]["coefficients"][:-1]
    with pytest.raises(StallModelError):
        load_stall_model(_write(tmp_path, data))


def test_incomplete_artifact_is_a_model_error(tmp_path):
    _, _, data = _artifact()
    del data["evaluation"]
    with pytest.raises(StallModelError):
        load_stall_model(_write(tmp_path, data))

"""Entrenamiento y ML eval gate del modelo de estancamiento (E7)."""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from agrosense.ml.preprocessing import fit_preprocessor, transform  # noqa: E402
from agrosense.ml.stall_features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    build_wave,
)
from agrosense.ml.stall_model import load_stall_model, logistic_scores  # noqa: E402
from agrosense.ml.train_stall import (  # noqa: E402
    StallTrainConfig,
    diff_artifacts,
    evaluate,
    fit_logistic,
    fit_stall_model,
    gate,
    permuted_globally,
    permuted_within_plot,
    render_report,
    report_diff,
    train_and_evaluate,
)
from tests.ml.builders import synthetic_panel  # noqa: E402

FAST = StallTrainConfig(n_bootstrap=50, n_permutations=3)
PROVENANCE = {
    "dataset_file": "sintetico",
    "dataset_sha256": "0" * 64,
    "sheet": "-",
    "mapping_version": "-",
    "git_commit": "abc",
    "git_dirty": False,
    "python": "3.12",
    "sklearn": "1.5.2",
    "numpy": "1.26.4",
}
REFERENCE_PATH = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


def test_preprocessing_is_fitted_on_training_rows_only():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    model = fit_stall_model(train, FAST)
    assert model.params.medians["h_t"] == statistics.median(r.features["h_t"] for r in train)


def test_serving_scores_equal_sklearn_probabilities():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    feats = [r.features for r in train]
    params = fit_preprocessor(feats, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    X = transform(params, feats)
    clf = fit_logistic(X, [int(bool(r.label)) for r in train], FAST)
    ours = logistic_scores(params, tuple(clf.coef_[0]), float(clf.intercept_[0]), feats)
    np.testing.assert_allclose(ours, clf.predict_proba(np.asarray(X))[:, 1], atol=1e-12)


def test_permutation_keeps_the_positives_of_each_plot():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    permuted = permuted_within_plot(train, np.random.default_rng(0))

    def per_plot(labels):
        c: Counter = Counter()
        for row, label in zip(train, labels, strict=True):
            c[row.plot] += label
        return c

    assert per_plot(permuted) == per_plot([int(bool(r.label)) for r in train])
    assert permuted != [int(bool(r.label)) for r in train]


def test_evaluate_reports_every_regime():
    trees, observations = synthetic_panel()
    ev = evaluate(trees, observations, FAST)
    assert set(ev) == {"temporal", "baselines", "permutation_control", "group_kfold"}
    t = ev["temporal"]
    assert t["n_train"] == len(build_wave(trees, observations, 2, labeled=True))
    assert t["n_test"] == len(build_wave(trees, observations, 3, labeled=True))
    assert 0.0 <= t["pr_auc"] <= 1.0
    assert t["pr_auc_ci"][0] <= t["pr_auc_ci"][1]
    # Fix round 1 (M2): el IC informa cuantos remuestreos fueron validos.
    assert t["pr_auc_ci_n_boot"] == FAST.n_bootstrap
    assert 0 < t["pr_auc_ci_n_valid"] <= t["pr_auc_ci_n_boot"]
    assert set(ev["baselines"]) == {"prevalence", "persistence", "species_rate"}
    assert ev["group_kfold"]["folds"] == 5


def test_species_rate_baseline_reports_a_plot_bootstrap_ci():
    # Fix round 1 (I3): la linea base tambien lleva IC, con el mismo
    # procedimiento (parcela, seed) que el modelo.
    trees, observations = synthetic_panel()
    ev = evaluate(trees, observations, FAST)
    species = ev["baselines"]["species_rate"]
    lo, hi = species["pr_auc_ci"]
    assert lo <= species["pr_auc"] <= hi


def _ev(pr, perm_global, perm_within=0.33, persistence=0.35, prevalence=0.22):
    return {
        "temporal": {"pr_auc": pr},
        "baselines": {
            "prevalence": {"pr_auc": prevalence},
            "persistence": {"pr_auc": persistence},
        },
        "permutation_control": {
            "global": {"pr_auc_mean": perm_global},
            "within_plot": {"pr_auc_mean": perm_within},
        },
    }


def test_gate_accepts_the_protocol_result():
    assert gate(_ev(0.469, 0.238), StallTrainConfig())["passed"] is True


def test_gate_rejects_a_weak_model():
    result = gate(_ev(0.30, 0.24), StallTrainConfig())
    assert result["passed"] is False
    assert result["checks"]["pr_auc_at_least_min"] is False


def test_gate_rejects_a_leaky_pipeline():
    # Si el control SIN senal puntua alto, el pipeline filtra la etiqueta.
    result = gate(_ev(0.60, 0.45), StallTrainConfig())
    assert result["checks"]["permutation_control_near_prevalence"] is False
    assert result["passed"] is False


def test_gate_rejects_a_model_that_only_learns_plot_rates():
    result = gate(_ev(0.40, 0.23, perm_within=0.42), StallTrainConfig())
    assert result["checks"]["beats_within_plot_permutation"] is False
    assert result["passed"] is False


def test_global_permutation_keeps_the_number_of_positives():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    permuted = permuted_globally(train, np.random.default_rng(0))
    assert sum(permuted) == sum(int(bool(r.label)) for r in train)


def test_training_is_reproducible():
    trees, observations = synthetic_panel()
    a = train_and_evaluate(trees, observations, FAST, PROVENANCE)
    b = train_and_evaluate(trees, observations, FAST, PROVENANCE)
    assert diff_artifacts(a, b) == []


def test_artifact_records_provenance_and_loads_as_the_serving_model(tmp_path):
    trees, observations = synthetic_panel()
    artifact = train_and_evaluate(trees, observations, FAST, PROVENANCE)
    for key in ("model_version", "features_version", "preprocessing_version", "created_at"):
        assert artifact[key]
    assert artifact["training"]["config"]["seed"] == 42
    assert artifact["training"]["waves"] == [2, 3]
    assert artifact["provenance"]["dataset_sha256"] == "0" * 64
    path = tmp_path / "a.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    model = load_stall_model(path)
    probs = model.predict(trees, observations, 4)
    assert probs and all(0.0 < p < 1.0 for p in probs.values())
    assert "Evaluación del modelo de estancamiento" in render_report(artifact)


def test_diff_artifacts_ignores_only_volatile_fields():
    base = {"created_at": "a", "provenance": {"git_commit": "x", "d": "1"}, "m": {"c": [0.1]}}
    other = {
        "created_at": "b",
        "provenance": {"git_commit": "y", "d": "1"},
        "m": {"c": (0.1 + 1e-12,)},
    }
    assert diff_artifacts(base, other) == []
    other["m"]["c"] = (0.2,)
    assert diff_artifacts(base, other) == ["m/c/0"]
    other["provenance"]["d"] = "2"
    assert "provenance/d" in diff_artifacts(base, other)


def test_report_states_the_reinterpreted_leakage_criterion_and_scope_caveats():
    """Fix round 1 (I1, I2, M4, M5): el informe no puede sonar mas limpio que
    el proceso real."""
    trees, observations = synthetic_panel()
    artifact = train_and_evaluate(trees, observations, FAST, PROVENANCE)
    report = render_report(artifact)
    # I1: el criterio de fuga se redefinio despues de ver el resultado, con
    # el numero concreto del control dentro de parcela, y queda
    # pre-registrado desde .2 en adelante.
    assert "NO habría pasado el gate" in report
    assert "PRE-REGISTRADA" in report
    assert "stall-logreg-2026-09-27.2" in report
    # I2: alcance del entrenamiento y que M2/M3 servidos son in-sample.
    assert "in-sample" in report
    assert "transferencia espacial" in report
    # M4: el GroupKFold agrupado mezcla olas; es diagnostico.
    assert "mezcla" in report.lower() or "mezclan" in report.lower()
    # M5: procedencia de C=0.5.
    assert "C=0.5" in report or "C (regularización" in report


def test_report_diff_ignores_only_timestamp_and_git_lines():
    trees, observations = synthetic_panel()
    a = render_report(train_and_evaluate(trees, observations, FAST, PROVENANCE))
    # Misma config y datos: dos corridas solo difieren en 'Entrenado' (timestamp).
    b = render_report(train_and_evaluate(trees, observations, FAST, PROVENANCE))
    assert report_diff(a, b) == []
    other_provenance = dict(PROVENANCE, git_commit="otro-commit", git_dirty=True)
    c = render_report(train_and_evaluate(trees, observations, FAST, other_provenance))
    assert report_diff(a, c) == []


def test_report_diff_catches_a_real_metric_change():
    trees, observations = synthetic_panel()
    base = render_report(train_and_evaluate(trees, observations, FAST, PROVENANCE))
    stale = base.replace("PR-AUC agregado", "PR-AUC AGREGADO DISTINTO")
    assert report_diff(base, stale) != []


@pytest.mark.skipif(
    not REFERENCE_PATH.exists(),
    reason="dataset de referencia local ausente (data/raw/anexo1.xlsx)",
)
def test_reference_dataset_passes_the_gate():
    from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

    data = ExcelCampaignSource().read(REFERENCE_PATH.read_bytes(), REFERENCE_PATH.name)
    config = StallTrainConfig(n_bootstrap=200, n_permutations=5)
    ev = evaluate(data.trees, data.observations, config)
    t = ev["temporal"]
    assert (t["n_train"], t["positives_train"]) == (618, 153)
    assert (t["n_test"], t["positives_test"]) == (717, 157)
    assert t["pr_auc"] >= 0.36
    assert ev["permutation_control"]["global"]["pr_auc_mean"] <= 0.31
    assert t["pr_auc"] > ev["permutation_control"]["within_plot"]["pr_auc_mean"]
    assert gate(ev, config)["passed"] is True

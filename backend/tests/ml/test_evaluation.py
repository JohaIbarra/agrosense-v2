"""Metricas del ML eval gate (Protocolo §5)."""
from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from agrosense.ml.evaluation import (  # noqa: E402
    grouped_bootstrap_ci,
    grouped_bootstrap_summary,
    pr_auc,
    recall_precision_at_budget,
    roc_auc,
    species_rate_scores,
)


def test_constant_scores_give_the_prevalence():
    y = [1, 0, 0, 0, 1, 0, 0, 0, 0, 0]
    assert pr_auc(y, [0.5] * 10) == pytest.approx(0.2)
    assert roc_auc(y, [0.5] * 10) == pytest.approx(0.5)


def test_perfect_ranking():
    y = [1, 1, 0, 0]
    assert pr_auc(y, [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)


def test_recall_and_precision_use_the_alert_budget():
    ids = [f"T{i}" for i in range(10)]
    y = [1, 1, 0, 0, 0, 0, 0, 0, 0, 1]
    scores = [0.9, 0.8, 0.7, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05]
    recall, precision = recall_precision_at_budget(ids, y, scores, 0.2)  # k = 2
    assert recall == pytest.approx(2 / 3)
    assert precision == pytest.approx(1.0)


def test_bootstrap_resamples_plots_not_rows():
    y = [1, 0, 1, 0, 0, 1, 0, 0]
    scores = [0.9, 0.2, 0.7, 0.3, 0.1, 0.8, 0.4, 0.2]
    # Una sola parcela: todo remuestreo es identico -> IC degenerado.
    lo, hi = grouped_bootstrap_ci(y, scores, ["U1"] * 8, n_boot=30, seed=1)
    assert lo == pytest.approx(hi)


def test_bootstrap_is_deterministic_and_brackets_the_estimate():
    y = [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0]
    scores = [0.8, 0.3, 0.2, 0.6, 0.4, 0.1, 0.7, 0.5, 0.2, 0.9, 0.3, 0.4]
    plots = ["U1", "U1", "U1", "U2", "U2", "U2", "U3", "U3", "U3", "U4", "U4", "U4"]
    a = grouped_bootstrap_ci(y, scores, plots, n_boot=200, seed=42)
    b = grouped_bootstrap_ci(y, scores, plots, n_boot=200, seed=42)
    assert a == b
    assert a[0] <= pr_auc(y, scores) <= a[1]


def test_species_rate_is_fitted_on_train_and_falls_back_to_prevalence():
    scores = species_rate_scores(["A", "A", "B", "B"], [1, 1, 0, 1], ["A", "B", "Nueva", None])
    assert scores == [1.0, 0.5, 0.75, 0.75]


def test_bootstrap_summary_matches_the_ci_helper():
    y = [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0]
    scores = [0.8, 0.3, 0.2, 0.6, 0.4, 0.1, 0.7, 0.5, 0.2, 0.9, 0.3, 0.4]
    plots = ["U1", "U1", "U1", "U2", "U2", "U2", "U3", "U3", "U3", "U4", "U4", "U4"]
    summary = grouped_bootstrap_summary(y, scores, plots, n_boot=200, seed=42)
    assert summary["ci"] == grouped_bootstrap_ci(y, scores, plots, n_boot=200, seed=42)
    assert summary["n_boot"] == 200
    assert 0 < summary["n_valid"] <= 200


def test_bootstrap_summary_reports_valid_resamples_are_fewer_when_classes_cluster_by_plot():
    # Parcela A toda positiva, parcela B toda negativa: la mitad de los
    # remuestreos (AA o BB) no tiene ambas clases y se descarta (M2).
    y = [1, 1, 0, 0]
    scores = [0.9, 0.8, 0.3, 0.2]
    plots = ["A", "A", "B", "B"]
    summary = grouped_bootstrap_summary(y, scores, plots, n_boot=50, seed=7)
    assert summary["n_boot"] == 50
    assert summary["n_valid"] < 50

"""Logistica L2 en Python puro (E8, ADR-014): paridad con scikit-learn."""
from __future__ import annotations

import random

import pytest

from agrosense.ml.logistic import fit_logistic_l2, predict_scores

sklearn = pytest.importorskip("sklearn.linear_model")


def _data(n=400, seed=7):
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n):
        a, b = rng.gauss(0, 1), rng.gauss(0, 1)
        onehot = [0.0, 0.0, 0.0]
        onehot[rng.randrange(3)] = 1.0
        z = -1.0 + 1.5 * a - 0.7 * b + 0.8 * onehot[0]
        X.append([a, b, *onehot])
        y.append(int(rng.random() < 1 / (1 + 2.718281828 ** -z)))
    return X, y


@pytest.mark.parametrize("C", [0.5, 1.0, 10.0])
def test_matches_sklearn_coefficients(C):
    X, y = _data()
    ours = fit_logistic_l2(X, y, C=C)
    ref = sklearn.LogisticRegression(C=C, max_iter=5000, tol=1e-10).fit(X, y)
    assert ours.intercept == pytest.approx(float(ref.intercept_[0]), abs=1e-4)
    assert ours.coef == pytest.approx([float(c) for c in ref.coef_[0]], abs=1e-4)


def test_scores_are_probabilities_in_order():
    X, y = _data()
    m = fit_logistic_l2(X, y, C=1.0)
    s = predict_scores(m, X)
    assert all(0.0 < p < 1.0 for p in s)
    ref = sklearn.LogisticRegression(C=1.0, max_iter=5000, tol=1e-10).fit(X, y)
    assert s == pytest.approx(ref.predict_proba(X)[:, 1].tolist(), abs=1e-4)


def test_single_class_is_rejected():
    with pytest.raises(ValueError):
        fit_logistic_l2([[1.0], [2.0]], [0, 0], C=1.0)


def test_is_fast_enough_for_a_request():
    import time

    rng = random.Random(1)
    X = [[rng.gauss(0, 1) for _ in range(4)] + [1.0 if j == i % 30 else 0.0 for j in range(30)]
         for i in range(3000)]
    y = [int(rng.random() < 0.15) for _ in X]
    t0 = time.perf_counter()
    fit_logistic_l2(X, y, C=0.5)
    assert time.perf_counter() - t0 < 5.0

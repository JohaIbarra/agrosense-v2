"""Regresion logistica L2 en Python puro (E8, ADR-014).

El modelo PROPIO de mortalidad se entrena dentro de una peticion de la API,
y scikit-learn no entra a produccion (ADR-013 §6). Minimiza el mismo
objetivo que `LogisticRegression(C=C)` de scikit-learn (intercepto sin
penalizar):

    0.5 * ||w||^2 + C * sum_i logloss(y_i, sigmoid(b + w . x_i))

con Newton-IRLS y busqueda de paso. Las filas se recorren en forma dispersa
(las columnas one-hot son casi todas cero), asi que el costo por iteracion
es ~n * nnz^2 + d^3 con d < 50: milisegundos para cientos de arboles. Un
test de paridad lo compara contra scikit-learn.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LogisticFit:
    intercept: float
    coef: list[float]
    iterations: int


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _sparse(X: Sequence[Sequence[float]]) -> list[list[tuple[int, float]]]:
    # Columna 0 = intercepto
    return [[(0, 1.0)] + [(j + 1, v) for j, v in enumerate(row) if v != 0.0] for row in X]


def _objective(theta: list[float], rows, y: Sequence[int], C: float) -> float:
    loss = 0.0
    for r, yi in zip(rows, y, strict=True):
        z = sum(theta[j] * v for j, v in r)
        # log(1 + e^z) - y z, estable
        loss += (max(z, 0.0) + math.log1p(math.exp(-abs(z)))) - yi * z
    return 0.5 * sum(t * t for t in theta[1:]) + C * loss


def _solve(A: list[list[float]], b: list[float]) -> list[float]:
    """Gauss con pivoteo parcial (A es simetrica definida positiva)."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(M[i][k]))
        M[k], M[p] = M[p], M[k]
        piv = M[k][k]
        for i in range(k + 1, n):
            f = M[i][k] / piv
            if f:
                Mi, Mk = M[i], M[k]
                for j in range(k, n + 1):
                    Mi[j] -= f * Mk[j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def fit_logistic_l2(
    X: Sequence[Sequence[float]],
    y: Sequence[int],
    C: float,
    *,
    max_iter: int = 100,
    tol: float = 1e-10,
) -> LogisticFit:
    if len(set(y)) < 2:
        raise ValueError("Se necesitan ambas clases para ajustar la logistica.")
    d = len(X[0]) + 1
    rows = _sparse(X)
    theta = [0.0] * d
    current = _objective(theta, rows, y, C)
    for it in range(1, max_iter + 1):
        grad = [0.0] + theta[1:]  # gradiente de la penalizacion
        H = [[0.0] * d for _ in range(d)]
        for j in range(1, d):
            H[j][j] = 1.0
        for r, yi in zip(rows, y, strict=True):
            p = sigmoid(sum(theta[j] * v for j, v in r))
            g, w = C * (p - yi), C * p * (1.0 - p)
            for j, v in r:
                grad[j] += g * v
                Hj = H[j]
                for k, u in r:
                    Hj[k] += w * v * u
        step = _solve(H, grad)
        t = 1.0
        while True:
            cand = [a - t * s for a, s in zip(theta, step, strict=True)]
            value = _objective(cand, rows, y, C)
            if value <= current or t < 1e-8:
                break
            t *= 0.5
        theta, previous, current = cand, current, value
        if max(abs(t * s) for s in step) < tol or abs(previous - current) < tol * max(1.0, current):
            return LogisticFit(theta[0], theta[1:], it)
    return LogisticFit(theta[0], theta[1:], max_iter)


def predict_scores(model: LogisticFit, X: Sequence[Sequence[float]]) -> list[float]:
    return [
        sigmoid(model.intercept + sum(c * v for c, v in zip(model.coef, row, strict=True)))
        for row in X
    ]

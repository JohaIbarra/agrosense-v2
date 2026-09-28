"""Metricas del ML eval gate del modelo de estancamiento (E7).

SOLO entrenamiento/evaluacion offline: importa numpy y scikit-learn, que no
son dependencias de produccion (ADR-013). La API nunca importa este modulo.

PR-AUC es la metrica principal (Protocolo §5): la clase positiva es
minoritaria (~22 %) y la exactitud seria enganosa.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from agrosense.domain.stall_rules import select_alerts


def pr_auc(y: Sequence[int], scores: Sequence[float]) -> float:
    return float(average_precision_score(np.asarray(y, dtype=int), np.asarray(scores, dtype=float)))


def roc_auc(y: Sequence[int], scores: Sequence[float]) -> float:
    return float(roc_auc_score(np.asarray(y, dtype=int), np.asarray(scores, dtype=float)))


def recall_precision_at_budget(
    tree_ids: Sequence[str], y: Sequence[int], scores: Sequence[float], budget: float
) -> tuple[float, float]:
    """Si se revisa en campo el `budget` de arboles con mayor score.

    Usa `select_alerts`, la MISMA regla con la que la API marca arboles.
    """
    flagged = select_alerts(dict(zip(tree_ids, scores, strict=True)), budget)
    positives = sum(y)
    hits = sum(1 for tid, yi in zip(tree_ids, y, strict=True) if yi and tid in flagged)
    recall = hits / positives if positives else 0.0
    precision = hits / len(flagged) if flagged else 0.0
    return recall, precision


def grouped_bootstrap_ci(
    y: Sequence[int],
    scores: Sequence[float],
    plot_codes: Sequence[str],
    *,
    n_boot: int,
    seed: int,
    level: float = 0.95,
) -> tuple[float, float]:
    """IC del PR-AUC remuestreando PARCELAS con reemplazo, no filas.

    Las filas de una parcela no son independientes (suelo, pendiente,
    cuadrilla): remuestrear filas daria un IC falsamente estrecho.
    """
    y_arr = np.asarray(y, dtype=int)
    s_arr = np.asarray(scores, dtype=float)
    plots = sorted(set(plot_codes))
    codes = np.asarray(plot_codes, dtype=object)
    index = {p: np.flatnonzero(codes == p) for p in plots}
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(n_boot):
        chosen = rng.integers(0, len(plots), size=len(plots))
        idx = np.concatenate([index[plots[i]] for i in chosen])
        if y_arr[idx].min() == y_arr[idx].max():
            continue
        values.append(float(average_precision_score(y_arr[idx], s_arr[idx])))
    if not values:
        raise ValueError("ningun remuestreo tuvo ambas clases: no hay IC")
    alpha = (1.0 - level) / 2.0
    lo, hi = np.quantile(values, [alpha, 1.0 - alpha])
    return float(lo), float(hi)


def species_rate_scores(
    train_species: Sequence[str | None],
    train_y: Sequence[int],
    test_species: Sequence[str | None],
) -> list[float]:
    """Linea base "tasa media por especie" (Protocolo §5), ajustada SOLO en train."""
    totals: dict[str | None, list[int]] = defaultdict(lambda: [0, 0])
    for species, label in zip(train_species, train_y, strict=True):
        totals[species][0] += int(label)
        totals[species][1] += 1
    prevalence = sum(train_y) / len(train_y)
    return [
        totals[s][0] / totals[s][1] if s is not None and s in totals else prevalence
        for s in test_species
    ]

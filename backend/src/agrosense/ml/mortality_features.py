"""Features de mortalidad (E8, ADR-014): relativas a la ola, compartidas por
entrenamiento (offline y en la peticion) e inferencia.

- `h_pct`: percentil de altura dentro de la poblacion en riesgo de la ola t
  (rango promedio en empates, como `pandas.rank(pct=True)`). Es la unica
  variable del modelo GENERAL: transfiere entre proyectos (exp_e) porque no
  depende de la edad de la plantacion ni de la escala de medicion.
- Modelo PROPIO: ademas `estanco_lag`, `dh_lag` (de E7) y `species`,
  `fito_t`, `locality`, que solo tienen sentido dentro de un proyecto.

El percentil se calcula sobre TODA la poblacion en riesgo en t, tenga o no
etiqueta: asi entrenamiento y servicio ven exactamente la misma feature.
Las features de t solo leen observaciones <= t.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence

from agrosense.domain.entities import Observation, Tree
from agrosense.domain.mortality_rules import died_in_interval
from agrosense.domain.rules import plot_key
from agrosense.domain.stall_rules import is_at_risk
from agrosense.ml.stall_features import WaveRow, _features, _history, fingerprint

MORTALITY_FEATURES_VERSION = "2026-09-30-e8.1"
GENERAL_FEATURES: tuple[str, ...] = ("h_pct",)
PROJECT_NUMERIC: tuple[str, ...] = ("h_pct", "estanco_lag", "dh_lag")
PROJECT_CATEGORICAL: tuple[str, ...] = ("species", "fito_t", "locality")


def _percentiles(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg / len(values)
        i = j + 1
    return ranks


def build_mortality_wave(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    t: int,
    *,
    labeled: bool,
) -> list[WaveRow]:
    """Filas de la ola t ordenadas por tree_id; con `labeled`, solo las que tienen etiqueta."""
    history = _history(observations, max_campaign=t)
    following = {o.tree_id: o for o in observations if o.campaign == t + 1} if labeled else {}
    at_risk = [
        tr for tr in sorted(trees, key=lambda tr: tr.tree_id)
        if is_at_risk(history.get(tr.tree_id, {}).get(t))
    ]
    heights = [history[tr.tree_id][t].height_m or 0.0 for tr in at_risk]
    rows: list[WaveRow] = []
    for tr, pct in zip(at_risk, _percentiles(heights), strict=True):
        own = history[tr.tree_id]
        label: bool | None = None
        if labeled:
            label = died_in_interval(own.get(t), following.get(tr.tree_id))
            if label is None:
                continue
        base = _features(tr, own, t)
        features = {k: base[k] for k in PROJECT_NUMERIC + PROJECT_CATEGORICAL if k in base}
        features["h_pct"] = pct
        rows.append(WaveRow(tree_id=tr.tree_id, plot=plot_key(tr), wave=t,
                            features=features, label=label))
    return rows


def mortality_fingerprint(
    trees: Sequence[Tree], observations: Sequence[Observation], t: int
) -> str:
    """Huella de los datos <= t (los del modelo propio incluidos) y de esta featurizacion."""
    base = fingerprint(trees, observations, t)
    return hashlib.sha256(f"{MORTALITY_FEATURES_VERSION}:{base}".encode()).hexdigest()

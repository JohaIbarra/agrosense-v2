"""Featurizacion del modelo de estancamiento (E7), COMPARTIDA por
entrenamiento e inferencia (AGENTS.md: "Training and inference must share
preprocessing logic"; leccion de v1).

Relativa a la ola: `h_t`, `dh_lag`, `estanco_lag`... nunca `altura_M3`, asi el
mismo modelo sirve para M5 sin reentrenar (Protocolo §3).

Anti-fuga por construccion (Protocolo §4.1 y §4.3): las features de la ola t
se calculan con `history`, que SOLO contiene observaciones con
`campaign <= t`. La etiqueta, que necesita t+1, la calcula aparte la regla de
dominio `stall_label` y nunca entra en `features`. Solo rezagos: ningun
agregado de la historia completa del arbol.

La parcela (`plot_key`) viaja en `WaveRow.plot` como unidad de agrupamiento
de la validacion; NO es feature (ADR-013 §2).

Python puro: esta ruta corre en cada peticion de la API (ADR-013).
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from agrosense.domain.analysis_rules import normalize_phytosanitary
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.rules import plot_key
from agrosense.domain.stall_rules import (
    is_at_risk,
    phytosanitary_worsened,
    stall_label,
    stalled_previous_interval,
)

# Cambiar CUALQUIER definicion de abajo = nueva version; el cargador del
# modelo rechaza un artefacto entrenado con otra (ADR-013 §5).
# e7.2 (fix wave, item 1a): las categoricas se normalizan (NFC + strip +
# casefold) para que entrenamiento y servicio nunca diverjan por una grafia
# distinta del mismo valor (espacios, mayusculas, forma Unicode).
FEATURES_VERSION = "2026-09-27-e7.2"

NUMERIC_FEATURES: tuple[str, ...] = (
    "h_t",
    "copa_t",
    "dh_lag",
    "dcopa_lag",
    "estanco_lag",
    "h_prev",
    "esbeltez_t",
    "fito_empeoro",
)
CATEGORICAL_FEATURES: tuple[str, ...] = ("locality", "species", "monitoring_unit", "fito_t")

FeatureValue = float | str | None


@dataclass(frozen=True)
class WaveRow:
    """Un arbol en el instante de prediccion t (una observacion arbol+ola)."""

    tree_id: str
    plot: str | None
    wave: int
    features: dict[str, FeatureValue]
    label: bool | None


def _history(
    observations: Sequence[Observation], max_campaign: int
) -> dict[str, dict[int, Observation]]:
    by_tree: dict[str, dict[int, Observation]] = defaultdict(dict)
    for o in observations:
        if o.campaign <= max_campaign:
            by_tree[o.tree_id][o.campaign] = o
    return by_tree


def _as_float(value: bool | None) -> float | None:
    return None if value is None else float(value)


def _normalize_category(value: str | None) -> str | None:
    """Forma canonica de un valor categorico (fix wave, item 1a).

    NFC + `strip` + `casefold`, para que "Guayabal", " GUAYABAL " y la misma
    palabra en otra forma Unicode (NFD) sean la MISMA categoria en
    entrenamiento y en servicio. Sin esto, un archivo servido que escribe el
    mismo valor con otra grafia lo trata como "no visto" (one-hot en ceros)
    en vez de reconocerlo.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value)).strip().casefold()
    return text or None


def _features(tree: Tree, history: Mapping[int, Observation], t: int) -> dict[str, FeatureValue]:
    cur = history[t]
    assert cur.height_m is not None
    h_t = cur.height_m
    copa_t = cur.crown_diameter_m

    dh_lag = dcopa_lag = h_prev = fito_empeoro = None
    prev = history.get(t - 1)
    if prev is not None and is_at_risk(prev):
        assert prev.height_m is not None
        h_prev = prev.height_m
        dh_lag = h_t - prev.height_m
        if copa_t is not None and prev.crown_diameter_m is not None:
            dcopa_lag = copa_t - prev.crown_diameter_m
        fito_empeoro = _as_float(phytosanitary_worsened(prev.phytosanitary, cur.phytosanitary))

    return {
        "h_t": h_t,
        "copa_t": copa_t,
        "dh_lag": dh_lag,
        "dcopa_lag": dcopa_lag,
        "estanco_lag": _as_float(stalled_previous_interval(history, t)),
        "h_prev": h_prev,
        "esbeltez_t": h_t / copa_t if copa_t else None,
        "fito_empeoro": fito_empeoro,
        "locality": _normalize_category(tree.locality),
        "species": _normalize_category(tree.species),
        "monitoring_unit": _normalize_category(tree.monitoring_unit),
        "fito_t": _normalize_category(normalize_phytosanitary(cur.phytosanitary)),
    }


def build_wave(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    t: int,
    *,
    labeled: bool,
) -> list[WaveRow]:
    """Filas de la ola t, ordenadas por tree_id.

    `labeled=True` (entrenamiento/evaluacion): solo arboles con etiqueta
    definida, es decir vivos y medidos en t y t+1.
    `labeled=False` (inferencia): todo arbol vivo y medido en t; el futuro no
    se conoce y no se mira.
    """
    history = _history(observations, max_campaign=t)
    following = (
        {o.tree_id: o for o in observations if o.campaign == t + 1} if labeled else {}
    )
    rows: list[WaveRow] = []
    for tree in sorted(trees, key=lambda tr: tr.tree_id):
        own = history.get(tree.tree_id, {})
        if not is_at_risk(own.get(t)):
            continue
        label: bool | None = None
        if labeled:
            label = stall_label(own.get(t), following.get(tree.tree_id))
            if label is None:
                continue
        rows.append(
            WaveRow(
                tree_id=tree.tree_id,
                plot=plot_key(tree),
                wave=t,
                features=_features(tree, own, t),
                label=label,
            )
        )
    return rows


def fingerprint(trees: Sequence[Tree], observations: Sequence[Observation], t: int) -> str:
    """Huella de TODO lo que puede cambiar la prediccion de la ola t.

    Solo observaciones `<= t`: cargar M5 no invalida la evaluacion de M4.
    """
    payload = {
        "features_version": FEATURES_VERSION,
        "t": t,
        "trees": sorted(
            (
                [tr.tree_id, tr.species, tr.locality, tr.monitoring_unit, plot_key(tr)]
                for tr in trees
            ),
            key=lambda row: cast("str", row[0]),
        ),
        "observations": sorted(
            (
                [o.tree_id, o.campaign, o.height_m, o.crown_diameter_m, o.phytosanitary, o.alive]
                for o in observations
                if o.campaign <= t
            ),
            key=lambda row: (row[0], row[1]),
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

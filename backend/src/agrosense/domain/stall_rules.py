"""Definiciones del estancamiento de crecimiento (E7, UC-AN4).

Fuente: docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md §2 y §6.

    Estancado(i, t) = 1  si  altura(i, t) == altura(i, t+1)
                       y arbol vivo en ambos

La etiqueta NO usa una expectativa por especie o sitio (fuga por expectativa,
Protocolo §4.2). Mide "crecimiento no detectable por el protocolo de campo",
no "crecimiento nulo": con alturas redondeadas a 5 cm, parte de los ceros son
arboles que crecieron 1-3 cm.

Por que no es `STAGNATION_THRESHOLD_M` (rules.py, <= 5 cm): ese umbral es la
definicion DESCRIPTIVA de la comparacion entre monitoreos (E4). El modelo se
valido con la igualdad (153 estancados en M2->M3, 157 en M3->M4) y sus
metricas solo valen para esa etiqueta (ADR-013).

Puro: sin I/O ni framework. Lo consumen el modelo (ml/), el caso de uso de
deteccion y, en E8, el modelo de mortalidad: `stalled_previous_interval` es
la feature `estancó_intervalo_previo`.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from agrosense.domain.analysis_rules import PHYTOSANITARY_STATES, normalize_phytosanitary
from agrosense.domain.entities import Observation

# Protocolo §6: se revisa en campo una FRACCION fija de arboles (los de mayor
# probabilidad), no los que superan 0.5.
ALERT_BUDGET = 0.20

# Convencion del proyecto (ADR-013, D9 del plan de E7), confirmada con el
# ingeniero el 2026-09-27: "persistente" = 2 o mas intervalos seguidos sin
# crecer. Un intervalo ya es `stalled_previous_interval`; dos seguidos es el
# minimo que merece "persistente".
PERSISTENT_STALL_INTERVALS = 2

# Fix wave (item 4): version de las reglas de NEGOCIO observadas que arma
# UC-AN4 (`ALERT_BUDGET`, `PERSISTENT_STALL_INTERVALS`, la definicion de
# `stall_label`/`height_unchanged`). Es DISTINTA de `FEATURES_VERSION` y
# `PREPROCESSING_VERSION` (ml/): esas versionan el MODELO; esta versiona la
# regla observada que se calcula ademas de la probabilidad y que el
# snapshot de `stall_assessments` tambien tiene que invalidar si cambia,
# aunque el modelo servido siga siendo el mismo. Cambiar cualquiera de las
# tres = nueva version.
RULES_VERSION = "2026-09-27-e7.1"


def _mm(height_m: float) -> int:
    return round(height_m * 1000)


def height_unchanged(prev_m: float, curr_m: float) -> bool:
    """La altura no cambio, comparada en milimetros.

    En milimetros y no en centimetros: el dataset trae alturas con medio
    centimetro (FR_1_31: 0.24 -> 0.245) y redondear a cm las fusionaria. En
    milimetros tampoco se confunde el ruido de coma flotante con crecimiento.
    """
    return _mm(prev_m) == _mm(curr_m)


def is_at_risk(observation: Observation | None) -> bool:
    """Vivo y con altura medida: puede estancarse (o no) hasta el proximo monitoreo."""
    return (
        observation is not None
        and observation.alive is True
        and observation.height_m is not None
    )


def stall_label(prev: Observation | None, curr: Observation | None) -> bool | None:
    """Etiqueta del intervalo (prev, curr]; None fuera de la poblacion en riesgo.

    Poblacion en riesgo (Protocolo §2): vivo y medido en AMBOS extremos. Los
    que mueren se excluyen: mortalidad es otro proceso (E8).
    """
    if prev is None or curr is None or not (is_at_risk(prev) and is_at_risk(curr)):
        return None
    assert prev.height_m is not None and curr.height_m is not None
    return height_unchanged(prev.height_m, curr.height_m)


def stalled_previous_interval(by_campaign: Mapping[int, Observation], t: int) -> bool | None:
    """`estancó_intervalo_previo`: no crecio en (t-1, t]. Solo lee t-1 y t."""
    return stall_label(by_campaign.get(t - 1), by_campaign.get(t))


def stall_streak(by_campaign: Mapping[int, Observation], t: int) -> int:
    """Intervalos seguidos sin crecer que terminan en t."""
    streak = 0
    k = t
    while stall_label(by_campaign.get(k - 1), by_campaign.get(k)) is True:
        streak += 1
        k -= 1
    return streak


def is_persistent_stall(streak: int) -> bool:
    return streak >= PERSISTENT_STALL_INTERVALS


def phytosanitary_worsened(prev_raw: str | None, curr_raw: str | None) -> bool | None:
    """El estado fitosanitario empeoro (Bueno < Regular < Malo). None si falta alguno."""
    prev = normalize_phytosanitary(prev_raw)
    curr = normalize_phytosanitary(curr_raw)
    if prev is None or curr is None:
        return None
    return PHYTOSANITARY_STATES.index(curr) > PHYTOSANITARY_STATES.index(prev)


def alert_count(n_at_risk: int, budget: float = ALERT_BUDGET) -> int:
    """Cuantos arboles se marcan para revision: floor(n * budget), minimo 1."""
    if not 0.0 < budget <= 1.0:
        raise ValueError(f"el presupuesto de alertas debe estar en (0, 1], recibido {budget}")
    if n_at_risk <= 0:
        return 0
    return max(1, math.floor(n_at_risk * budget + 1e-9))


def select_alerts(scores: Mapping[str, float], budget: float = ALERT_BUDGET) -> frozenset[str]:
    """Los `alert_count` arboles de mayor score; empate -> tree_id ascendente (estable)."""
    k = alert_count(len(scores), budget)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return frozenset(tree_id for tree_id, _ in ranked[:k])

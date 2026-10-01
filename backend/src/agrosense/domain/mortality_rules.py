"""Definicion de la mortalidad entre monitoreos (E8, ADR-014).

    Murio(i, t) = 1  si  vivo y con altura en t  y  muerto en t+1

Poblacion en riesgo: la misma que el estancamiento (`is_at_risk`): vivo y
con altura medida en t. Sobrevivir no exige altura medida en t+1; si el
estado de t+1 se desconoce (sin registro o sin dato de supervivencia), el
arbol queda fuera de la etiqueta en vez de contarse como vivo.

El presupuesto de alertas es el de E7 (`stall_rules.select_alerts`): una
sola regla de alertas en el producto.
"""
from __future__ import annotations

from agrosense.domain.entities import Observation
from agrosense.domain.stall_rules import is_at_risk

# Cambia si cambia la etiqueta o la poblacion en riesgo: invalida snapshots.
MORTALITY_RULES_VERSION = "2026-09-30-e8.1"


def died_in_interval(prev: Observation | None, curr: Observation | None) -> bool | None:
    """Etiqueta del intervalo (prev, curr]; None fuera de la poblacion en riesgo."""
    if not is_at_risk(prev) or curr is None or curr.alive is None:
        return None
    return curr.alive is False

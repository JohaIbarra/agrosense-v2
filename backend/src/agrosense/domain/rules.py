"""Invariantes de dominio sobre SERIES de observaciones (docs/02-domain.md seccion 2).

Pure: sin I/O, sin framework. Recibe Observations ya validadas por
construccion (entities.py) y valida la coherencia TEMPORAL entre campanas.
"""
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.errors import (
    DeathViolationError,
    NonContiguousCensusError,
    SuspiciousContractionWarning,
)

STAGNATION_THRESHOLD_M = 0.05
MAX_CONTRACTION_M = 0.01


def growth_between(prev: Observation, curr: Observation) -> float:
    """Crecimiento entre campanas consecutivas censadas (invariante 3)."""
    if prev.height_m is None or curr.height_m is None:
        raise ValueError("growth_between requiere alturas censadas en ambas campanas")
    return curr.height_m - prev.height_m


def validate_tree_observations(
    tree: Tree, observations: list[Observation]
) -> list[SuspiciousContractionWarning]:
    """Valida la serie temporal de un arbol.

    Lanza DomainError (aborta la ingesta) si viola invariante dura:
    muerte que revive/crece, censo con huecos.
    Devuelve warnings de contraccion sospechosa (NO abortan).
    """
    if not observations:
        return []

    obs_sorted = sorted(observations, key=lambda o: o.campaign)
    campaigns = [o.campaign for o in obs_sorted]

    if campaigns != list(range(campaigns[0], campaigns[-1] + 1)):
        raise NonContiguousCensusError(tree.tree_id, campaigns)

    warnings: list[SuspiciousContractionWarning] = []
    dead_seen = False
    prev: Observation | None = None

    for obs in obs_sorted:
        if dead_seen:
            if obs.alive:
                raise DeathViolationError(tree.tree_id, obs.campaign, "revive")
            if (
                prev is not None
                and prev.height_m is not None
                and obs.height_m is not None
                and abs(obs.height_m - prev.height_m) > 1e-9
            ):
                raise DeathViolationError(tree.tree_id, obs.campaign, "crece tras morir")
        else:
            if (
                prev is not None
                and prev.height_m is not None
                and obs.height_m is not None
            ):
                contraction = prev.height_m - obs.height_m
                if contraction > MAX_CONTRACTION_M + 1e-9:
                    warnings.append(
                        SuspiciousContractionWarning(tree.tree_id, obs.campaign, contraction)
                    )
            if obs.alive is False:
                dead_seen = True
        prev = obs

    return warnings

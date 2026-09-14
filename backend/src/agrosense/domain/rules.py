"""Invariantes de dominio sobre SERIES de observaciones (docs/02-domain.md seccion 2).

Pure: sin I/O, sin framework. Recibe Observations ya validadas por
construccion (entities.py) y valida la coherencia TEMPORAL entre campanas.
"""
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.errors import (
    CensusGapWarning,
    DeathViolationError,
    SuspiciousContractionWarning,
    SuspiciousRevivalWarning,
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
) -> list[SuspiciousContractionWarning | SuspiciousRevivalWarning | CensusGapWarning]:
    """Valida la serie temporal de un arbol.

    Lanza DomainError (aborta la ingesta) SOLO si viola invariante dura:
    un arbol muerto que CRECE tras morir.
    Devuelve warnings (NO abortan): contraccion sospechosa, 'revives'
    (probable replanteo), huecos de censo (logistica de campo).
    """
    if not observations:
        return []

    obs_sorted = sorted(observations, key=lambda o: o.campaign)
    campaigns = [o.campaign for o in obs_sorted]

    warnings: list[
        SuspiciousContractionWarning | SuspiciousRevivalWarning | CensusGapWarning
    ] = []

    if campaigns != list(range(campaigns[0], campaigns[-1] + 1)):
        warnings.append(CensusGapWarning(tree.tree_id, campaigns))

    dead_seen = False
    prev: Observation | None = None

    for obs in obs_sorted:
        if dead_seen:
            grew = (
                prev is not None
                and prev.height_m is not None
                and obs.height_m is not None
                and obs.height_m - prev.height_m > 1e-9
            )
            if obs.alive:
                # 'revive' = replanteo (6/856 reales)
                warnings.append(SuspiciousRevivalWarning(tree.tree_id, obs.campaign))
                dead_seen = False
            elif grew:
                if _revives_later(obs, obs_sorted):
                    # muerto->muerto creciendo y luego vivo: replanteo mal
                    # registrado (FR_1_45, 1/856)
                    warnings.append(SuspiciousRevivalWarning(tree.tree_id, obs.campaign))
                    dead_seen = False
                else:
                    # muerto hasta el final con altura creciendo: invalido
                    raise DeathViolationError(
                        tree.tree_id, obs.campaign, "crece tras morir"
                    )
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


def _revives_later(
    obs: Observation, obs_sorted: list[Observation]
) -> bool:
    """Hay alguna campana posterior con el arbol vivo? (patron replanteo)."""
    for later in obs_sorted:
        if later.campaign > obs.campaign and later.alive:
            return True
    return False

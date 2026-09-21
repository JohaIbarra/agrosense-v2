"""Invariantes de dominio sobre SERIES de observaciones (docs/02-domain.md seccion 2).

Pure: sin I/O, sin framework. Recibe Observations ya validadas por
construccion (entities.py) y valida la coherencia TEMPORAL entre campanas.
"""
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.errors import (
    CensusGapWarning,
    DeathViolationError,
    LargeContractionNoted,
    SpeciesMismatchError,
    SuspiciousRevivalWarning,
    TreeIdentityMismatchError,
)

STAGNATION_THRESHOLD_M = 0.05

# Altura por debajo de la cual una bajada NO se anota siquiera (5 cm).
#
# Una contraccion de altura no es un error de medicion: puede reflejar dano
# fisico, poda, ramoneo o error de referencia. NO corregir el dato original.
#
# El umbral subio de 1 cm a 5 cm el 2026-09-21. Con 1 cm, el unico intervalo
# sin corregir del dataset de referencia (M1->M2) habria generado nota en 12
# de sus 13 contracciones reales (1-20 cm), y ese volumen de avisos es
# exactamente lo que empuja a la cuadrilla a "arreglar" la altura hasta
# dejarla monotona — que es lo que ya paso en M2->M3 y M3->M4 (0 %
# de contracciones, biologicamente inverosimil). 5 cm deja pasar el ruido
# normal de cinta y solo anota la bajada que de verdad vale una visita.
MAX_CONTRACTION_M = 0.05


def growth_between(prev: Observation, curr: Observation) -> float:
    """Crecimiento entre campanas consecutivas censadas (invariante 3)."""
    if prev.height_m is None or curr.height_m is None:
        raise ValueError("growth_between requiere alturas censadas en ambas campanas")
    return curr.height_m - prev.height_m


def validate_tree_observations(
    tree: Tree, observations: list[Observation]
) -> list[LargeContractionNoted | SuspiciousRevivalWarning | CensusGapWarning]:
    """Valida la serie temporal de un arbol.

    Lanza DomainError (aborta la ingesta) SOLO si viola invariante dura:
    un arbol muerto que CRECE tras morir.
    Devuelve avisos (NO abortan): contraccion grande ANOTADA (no es error:
    ver LargeContractionNoted — el dato original no se corrige), 'revives'
    (probable replanteo), huecos de censo (logistica de campo).
    """
    if not observations:
        return []

    obs_sorted = sorted(observations, key=lambda o: o.campaign)
    campaigns = [o.campaign for o in obs_sorted]

    warnings: list[
        LargeContractionNoted | SuspiciousRevivalWarning | CensusGapWarning
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
                        LargeContractionNoted(tree.tree_id, obs.campaign, contraction)
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


# Atributos que FIJAN la identidad del arbol (docs/02-domain.md §2.4).
# El resto (familia, nombre comun, gremio, localidad, elevacion) son
# descriptivos: se corrigen con el archivo mas reciente.
IDENTITY_FIELDS = ("plot_id", "coord_x", "coord_y")


def validate_tree_identity(stored, incoming: Tree) -> None:
    """Compara un arbol ya persistido con el que trae una carga nueva.

    `stored` solo necesita exponer los atributos por nombre, asi que sirve
    tanto una entidad de dominio como una fila del ORM: el dominio no
    aprende nada de la persistencia.

    Raises:
        SpeciesMismatchError: si cambia la especie.
        TreeIdentityMismatchError: si cambia parcela o coordenadas.
    """
    if stored.species != incoming.species:
        raise SpeciesMismatchError(
            tree_id=incoming.tree_id, found=incoming.species, expected=stored.species
        )

    for field in IDENTITY_FIELDS:
        antes = getattr(stored, field)
        ahora = getattr(incoming, field)
        if antes != ahora:
            raise TreeIdentityMismatchError(incoming.tree_id, field, antes, ahora)


def plot_key(tree) -> str | None:
    """Identidad de la parcela de un arbol dentro de su proyecto (E0).

    1. `Codigo de unidad muestreo` cuando el archivo lo trae: es el
       identificador de campo de la unidad, y la unidad por la que se agrupa
       la validacion cruzada.
    2. Si no, `predio/ID Parcela`: el numero de parcela solo es unico dentro
       de su predio, asi que el predio forma parte de la clave.
    3. Sin ninguno de los dos, el arbol no tiene parcela conocida.

    Limitacion declarada: si un proyecto mezcla archivos con y sin codigo de
    unidad, la misma parcela fisica recibe dos claves distintas. El formato de
    campo real siempre trae el codigo.
    """
    if tree.sampling_unit_code:
        return tree.sampling_unit_code
    if tree.plot_id:
        return f"{tree.locality}/{tree.plot_id}" if tree.locality else tree.plot_id
    return None

"""UC-AN3: contrastar las especies plantadas de un proyecto con el Referente
cientifico (E5).

Cruza `trees.species` (por proyecto) contra la version activa de
`reference_species_effects`. Reutiliza `build_risk`/`log_odds_ci`/
`interpret` de `read_analytics.py`: la interpretacion de un OR es la MISMA
regla de negocio aqui que en el ranking del referente, y AGENTS.md prohibe
duplicarla.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from agrosense.application.dtos import RiskDTO, SpeciesContrastDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.read_analytics import (
    MODEL_MORTALITY,
    MODEL_STALL,
    build_risk,
    log_odds_ci,
)

_SIN_REFERENCIA = (
    "Sin referencia: esta especie no esta entre las del dataset cientifico. "
    "Todavia no se puede comparar."
)


class ProjectOwnershipReader(Protocol):
    def get_owned(self, project_id: int, owner_id: str) -> object | None: ...


class ProjectSpeciesReader(Protocol):
    def list_species(self, project_id: int) -> list[tuple[str, int]]: ...


class ReferenceEffectRow(Protocol):
    """Lo unico que el caso de uso lee de una fila de efectos por especie."""

    species_name: str
    effect_stall: float | None
    se_stall: float | None
    or_stall: float | None
    or_stall_lo: float | None
    or_stall_hi: float | None
    sig_stall: bool | None
    effect_mort: float | None
    se_mort: float | None
    or_mort: float | None
    or_mort_lo: float | None
    or_mort_hi: float | None
    sig_mort: bool | None
    gremio: str | None


class ReferenceSpeciesReader(Protocol):
    def active_model(self) -> object | None: ...

    # Sequence (covariante): el adaptador devuelve list[<fila ORM>] y list es invariante
    def list_species(self) -> Sequence[ReferenceEffectRow]: ...


def _narrative(species: str, n_trees: int, stall: RiskDTO, mortality: RiskDTO) -> str:
    arboles = "arbol" if n_trees == 1 else "arboles"
    return (
        f"Planto {n_trees} {arboles} de {species}. "
        f"Estancamiento: {stall.interpretation} "
        f"Mortalidad: {mortality.interpretation}"
    )


def contrast_project_species(
    project_id: int,
    owner_id: str,
    project_repo: ProjectOwnershipReader,
    species_repo: ProjectSpeciesReader,
    reference_repo: ReferenceSpeciesReader,
) -> list[SpeciesContrastDTO]:
    """Contrasta las especies plantadas de `project_id` con el referente activo.

    Orden de las validaciones (deliberado): primero la propiedad del
    proyecto, despues si hay una version publicada del referente. Un proyecto
    ajeno debe dar 404 PROJECT_NOT_FOUND sin revelar nada del estado del
    referente.

    Raises:
        AppError("PROJECT_NOT_FOUND"): `project_id` no es del `owner_id`.
        AppError("REFERENCE_NOT_LOADED"): no hay ninguna version publicada
            del referente (`scripts/load_analytics.py` no se ha corrido).
    """
    if project_repo.get_owned(project_id, owner_id) is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")

    if reference_repo.active_model() is None:
        raise AppError(
            "REFERENCE_NOT_LOADED",
            "El referente no esta publicado. Ejecute scripts/load_analytics.py.",
        )

    # Se resuelve la version activa UNA vez: una fila por especie, no una
    # consulta por especie plantada (evita N+1 contra el referente).
    effects = {row.species_name: row for row in reference_repo.list_species()}

    out: list[SpeciesContrastDTO] = []
    for species, n_trees in species_repo.list_species(project_id):
        row = effects.get(species)
        if row is None:
            out.append(
                SpeciesContrastDTO(
                    species=species,
                    n_trees_in_project=n_trees,
                    has_reference=False,
                    gremio=None,
                    stall_risk=None,
                    mortality_risk=None,
                    narrative=_SIN_REFERENCIA,
                )
            )
            continue

        lo_s, hi_s = log_odds_ci(row.effect_stall, row.se_stall)
        stall = build_risk(
            row.or_stall, row.or_stall_lo, row.or_stall_hi, lo_s, hi_s,
            row.sig_stall, MODEL_STALL,
        )
        lo_m, hi_m = log_odds_ci(row.effect_mort, row.se_mort)
        mortality = build_risk(
            row.or_mort, row.or_mort_lo, row.or_mort_hi, lo_m, hi_m,
            row.sig_mort, MODEL_MORTALITY,
        )
        out.append(
            SpeciesContrastDTO(
                species=species,
                n_trees_in_project=n_trees,
                has_reference=True,
                gremio=row.gremio,
                stall_risk=stall,
                mortality_risk=mortality,
                narrative=_narrative(species, n_trees, stall, mortality),
            )
        )
    return out

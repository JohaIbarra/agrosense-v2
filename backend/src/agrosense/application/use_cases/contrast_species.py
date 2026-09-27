"""UC-AN3: contrastar las especies plantadas de un proyecto con el Referente
cientifico (E5).

Cruza `trees.species` (por proyecto) contra la version activa de
`reference_species_effects`. Reutiliza `build_risk`/`log_odds_ci`/
`interpret` de `read_analytics.py`: la interpretacion de un OR es la MISMA
regla de negocio aqui que en el ranking del referente, y AGENTS.md prohibe
duplicarla.
"""
from __future__ import annotations

from typing import Protocol

from agrosense.application.dtos import RiskDTO, SpeciesContrastDTO
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


class ProjectSpeciesReader(Protocol):
    def list_species(self, project_id: int) -> list[tuple[str, int]]: ...


class ReferenceSpeciesReader(Protocol):
    def get_species(self, name: str) -> object | None: ...


def _narrative(species: str, n_trees: int, stall: RiskDTO, mortality: RiskDTO) -> str:
    arboles = "arbol" if n_trees == 1 else "arboles"
    return (
        f"Planto {n_trees} {arboles} de {species}. "
        f"Estancamiento: {stall.interpretation} "
        f"Mortalidad: {mortality.interpretation}"
    )


def contrast_project_species(
    project_id: int,
    project_repo: ProjectSpeciesReader,
    reference_repo: ReferenceSpeciesReader,
) -> list[SpeciesContrastDTO]:
    out: list[SpeciesContrastDTO] = []
    for species, n_trees in project_repo.list_species(project_id):
        row = reference_repo.get_species(species)
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

"""UC-AN3: contraste de las especies plantadas con el Referente cientifico (E5).

Contrato (exige sesion; proyecto ajeno -> 404):
    GET /projects/{project_id}/reference-contrast -> 200 list[SpeciesContrastResponse]
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import RiskResponse, SpeciesContrastResponse
from agrosense.adapters.db.repository import (
    ProjectRepository,
    ProjectSpeciesRepository,
    ReferenceRepository,
)
from agrosense.application.dtos import RiskDTO, SpeciesContrastDTO
from agrosense.application.use_cases.contrast_species import contrast_project_species

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def _to_risk(risk: RiskDTO | None) -> RiskResponse | None:
    if risk is None:
        return None
    return RiskResponse(
        odds_ratio=risk.odds_ratio,
        or_ci95=risk.or_ci95,
        ci95_log_odds=risk.ci95_log_odds,
        significant=risk.significant,
        interpretation=risk.interpretation,
    )


def _to_response(dto: SpeciesContrastDTO) -> SpeciesContrastResponse:
    return SpeciesContrastResponse(
        species=dto.species,
        n_trees_in_project=dto.n_trees_in_project,
        has_reference=dto.has_reference,
        gremio=dto.gremio,
        stall_risk=_to_risk(dto.stall_risk),
        mortality_risk=_to_risk(dto.mortality_risk),
        narrative=dto.narrative,
    )


@router.get(
    "/projects/{project_id}/reference-contrast",
    response_model=list[SpeciesContrastResponse],
)
def get_reference_contrast_endpoint(
    project_id: int, session: SessionDep, engineer: CurrentEngineer
) -> list[SpeciesContrastResponse]:
    try:
        dtos = contrast_project_species(
            project_id,
            engineer.id,
            ProjectRepository(session),
            ProjectSpeciesRepository(session),
            ReferenceRepository(session),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return [_to_response(d) for d in dtos]

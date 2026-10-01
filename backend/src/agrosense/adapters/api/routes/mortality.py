"""Endpoint de riesgo de mortalidad de un monitoreo (E8, UC-AN5).

Regla ADR-003: parsear -> caso de uso -> mapear respuesta. Cero logica de
negocio aqui. Contrato: docs/superpowers/plans/2026-09-30-e8-mortalidad.md,
seccion "Contrato del endpoint (S9)".

    GET /projects/{project_id}/monitorings/{number}/mortality-risk?only_flagged=
        -> 200 MortalityRiskResponse
        -> 404 PROJECT_NOT_FOUND | MONITORING_NOT_FOUND
        -> 503 MORTALITY_MODEL_UNAVAILABLE

`def` y no `async def` (leccion de v1): el caso de uso consulta la base y
puntua en CPU; FastAPI lo manda al threadpool. El modelo propio es Python
puro con cientos de filas (ADR-014 §2): no hace falta cola.

El modelo general se carga UNA vez por proceso (`lru_cache`); un artefacto
nuevo exige reiniciar el servidor. Si la carga falla no se cachea: el
siguiente intento vuelve a leer el archivo. El modelo propio NO se cachea:
depende de los datos del proyecto y su resultado queda en el snapshot.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    MortalityDecisionResponse,
    MortalityModelCardResponse,
    MortalityRiskResponse,
    MortalitySummaryResponse,
    MortalityTreeResponse,
)
from agrosense.adapters.db.repository import (
    MortalityAssessmentRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
)
from agrosense.application.dtos import MortalityAssessmentDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.mortality_risk import get_mortality_assessment
from agrosense.ml.mortality_model import MortalityModelError, load_general_mortality_model
from agrosense.ml.mortality_project import MortalityScorer

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
NumberPath = Annotated[int, Path(ge=1, le=1000, description="Numero de monitoreo (M1 = 1).")]


@lru_cache(maxsize=1)
def _cached_scorer() -> MortalityScorer:
    return MortalityScorer(load_general_mortality_model())


def _scorer() -> MortalityScorer:
    try:
        return _cached_scorer()
    except MortalityModelError as exc:
        logger.warning("Modelo de mortalidad no disponible", exc_info=exc)
        raise AppError(
            "MORTALITY_MODEL_UNAVAILABLE",
            "El modelo de riesgo de mortalidad no está disponible en este servidor.",
        ) from exc


def _to_response(dto: MortalityAssessmentDTO) -> MortalityRiskResponse:
    return MortalityRiskResponse(
        project_id=dto.project_id,
        monitoring=dto.monitoring,
        model_kind=dto.model_kind,  # type: ignore[arg-type]
        score_kind=dto.score_kind,  # type: ignore[arg-type]
        model_version=dto.model_version,
        artifact_sha256=dto.artifact_sha256,
        input_hash=dto.input_hash,
        computed_at=dto.computed_at,
        decision=MortalityDecisionResponse(**dto.decision),
        model=MortalityModelCardResponse(**dto.model_card),
        alert_budget_pct=dto.alert_budget_pct,
        summary=MortalitySummaryResponse(**dto.summary),
        trees=[MortalityTreeResponse(**t) for t in dto.trees],
    )


@router.get(
    "/projects/{project_id}/monitorings/{number}/mortality-risk",
    response_model=MortalityRiskResponse,
    # `decision` solo trae las cifras de la razon que aplica (contrato).
    response_model_exclude_unset=True,
)
def get_mortality_risk_endpoint(
    project_id: int,
    number: NumberPath,
    session: SessionDep,
    engineer: CurrentEngineer,
    only_flagged: Annotated[
        bool, Query(description="Solo los arboles del presupuesto de alertas.")
    ] = False,
) -> MortalityRiskResponse:
    try:
        dto = get_mortality_assessment(
            project_id,
            number,
            engineer.id,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            MortalityAssessmentRepository(session),
            _scorer,  # se pasa la funcion, no se invoca aqui: el caso de uso la
            # resuelve DESPUES de comprobar dueño y monitoreo.
            only_flagged=only_flagged,
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_response(dto)

"""Endpoint de deteccion de estancados de un monitoreo (E7, UC-AN4).

Regla ADR-003: parsear -> caso de uso -> mapear respuesta. Cero logica de
negocio aqui. Contrato: docs/superpowers/plans/2026-09-27-e7-estancados.md,
Task 11.

    GET /projects/{project_id}/monitorings/{number}/stall-assessment?only_flagged=
        -> 200 StallAssessmentResponse
        -> 404 PROJECT_NOT_FOUND | MONITORING_NOT_FOUND
        -> 503 STALL_MODEL_UNAVAILABLE

`def` y no `async def` (leccion de v1): el caso de uso consulta la base y
puntua en CPU; FastAPI lo manda al threadpool. Puntuar ~800 arboles es
barato, no hace falta cola (ADR-013 §7).

El modelo se carga UNA vez por proceso (`lru_cache`); un artefacto nuevo
exige reiniciar el servidor. Si la carga falla no se cachea: el siguiente
intento vuelve a leer el archivo.
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
    StallAssessmentResponse,
    StallModelCardResponse,
    StallSummaryResponse,
    StallTreeResponse,
)
from agrosense.adapters.db.repository import (
    ProjectAnalysisRepository,
    ProjectRepository,
    StallAssessmentRepository,
)
from agrosense.application.dtos import StallAssessmentDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.stall_detection import get_stall_assessment
from agrosense.ml.stall_model import StallModel, StallModelError, load_stall_model

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
NumberPath = Annotated[int, Path(ge=1, le=1000, description="Numero de monitoreo (M1 = 1).")]


@lru_cache(maxsize=1)
def _cached_model() -> StallModel:
    return load_stall_model()


def _scorer() -> StallModel:
    try:
        return _cached_model()
    except StallModelError as exc:
        logger.warning("Modelo de estancamiento no disponible", exc_info=exc)
        raise AppError(
            "STALL_MODEL_UNAVAILABLE",
            "El modelo de detección de estancados no está disponible en este servidor.",
        ) from exc


def _to_response(dto: StallAssessmentDTO) -> StallAssessmentResponse:
    return StallAssessmentResponse(
        project_id=dto.project_id,
        monitoring=dto.monitoring,
        input_hash=dto.input_hash,
        computed_at=dto.computed_at,
        alert_budget_pct=dto.alert_budget_pct,
        persistent_min_intervals=dto.persistent_min_intervals,
        model=StallModelCardResponse(**dto.model_card),
        summary=StallSummaryResponse(**dto.summary),
        trees=[StallTreeResponse(**t) for t in dto.trees],
    )


@router.get(
    "/projects/{project_id}/monitorings/{number}/stall-assessment",
    response_model=StallAssessmentResponse,
)
def get_stall_assessment_endpoint(
    project_id: int,
    number: NumberPath,
    session: SessionDep,
    engineer: CurrentEngineer,
    only_flagged: Annotated[
        bool, Query(description="Solo los arboles del presupuesto de alertas.")
    ] = False,
) -> StallAssessmentResponse:
    try:
        dto = get_stall_assessment(
            project_id,
            number,
            engineer.id,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            StallAssessmentRepository(session),
            _scorer(),
            only_flagged=only_flagged,
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_response(dto)

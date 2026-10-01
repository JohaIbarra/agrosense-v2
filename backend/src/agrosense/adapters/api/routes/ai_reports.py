"""Endpoints del borrador de informe con IA de un monitoreo (E9, UC-IA1/2/3).

Regla ADR-003: parsear -> caso de uso -> mapear respuesta. Cero logica de
negocio aqui.

Contratos (exigen sesion; proyecto ajeno -> 404):
    GET  /projects/{project_id}/monitorings/{number}/ai-report
         -> 200 AIReportResponse | 404 AI_REPORT_NOT_FOUND | 404 PROJECT/MONITORING_NOT_FOUND
    POST /projects/{project_id}/monitorings/{number}/ai-report
         -> 200 AIReportResponse (genera o regenera) | 503 LLM_UNAVAILABLE

Los endpoints son `def` (no `async`): la generacion con Ollama es una
peticion HTTP bloqueante de hasta 180 s, y FastAPI solo la manda al
threadpool si el endpoint es sincrono (leccion de v1, AGENTS.md). Sin cola
de trabajos todavia (ADR-010 pendiente): con un ingeniero generando un
borrador a la vez, bloquear un worker del threadpool no agota el pool; se
revisa si algun dia hay generacion concurrente.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from agrosense.adapters.analysis.engine import ExploratoryAnalysisEngine
from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import AIReportResponse
from agrosense.adapters.db.repository import (
    AIReportRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
)
from agrosense.adapters.llm.ollama import OllamaClient, ai_reports_enabled
from agrosense.application.dtos import AIReportDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.ai_report import generate_ai_report, get_ai_report

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
NumberPath = Annotated[int, Path(ge=1, le=1000, description="Numero de monitoreo (M1 = 1).")]


def _require_enabled() -> None:
    if not ai_reports_enabled():
        raise AppError(
            "AI_REPORTS_DISABLED",
            "El borrador de informe con IA no esta disponible en este servidor.",
        )


def _to_response(dto: AIReportDTO) -> AIReportResponse:
    return AIReportResponse(
        project_id=dto.project_id,
        monitoring=dto.monitoring,
        model_name=dto.model_name,
        prompt_version=dto.prompt_version,
        content=dto.content,
        unverified_numbers=dto.unverified_numbers,
        created_at=dto.created_at,
        stale=dto.stale,
    )


@router.get(
    "/projects/{project_id}/monitorings/{number}/ai-report",
    response_model=AIReportResponse,
)
def get_ai_report_endpoint(
    project_id: int,
    number: NumberPath,
    session: SessionDep,
    engineer: CurrentEngineer,
) -> AIReportResponse:
    try:
        _require_enabled()
        dto = get_ai_report(
            project_id,
            number,
            engineer.id,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            AIReportRepository(session),
            ExploratoryAnalysisEngine(),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_response(dto)


@router.post(
    "/projects/{project_id}/monitorings/{number}/ai-report",
    response_model=AIReportResponse,
)
def generate_ai_report_endpoint(
    project_id: int,
    number: NumberPath,
    session: SessionDep,
    engineer: CurrentEngineer,
) -> AIReportResponse:
    try:
        _require_enabled()
        dto = generate_ai_report(
            project_id,
            number,
            engineer.id,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            AIReportRepository(session),
            ExploratoryAnalysisEngine(),
            OllamaClient(),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_response(dto)
